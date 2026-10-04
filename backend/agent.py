"""LangGraph research agent — the core agentic loop.

Production-hardened for Groq API rate limits via:
- GroqRateLimiter (token bucket + exponential backoff + caching)
- Reduced per-iteration token usage (tighter truncation, fewer queries)
- Inter-node delays to spread load across time
- Combined analyze-gating to cut LLM round-trips
"""

import json
import asyncio
from typing import TypedDict, Annotated, Any
from dotenv import load_dotenv

from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

import logging

logger = logging.getLogger(__name__)

from citations import append_citation_warning, verify_citations
from llm_provider import create_chat_model, get_provider_name
from tools import tavily_search, scrape_page
from prompts import SEARCH_PLANNER_PROMPT, CONTENT_ANALYZER_PROMPT, REPORT_WRITER_PROMPT
from rate_limiter import GroqRateLimiter

load_dotenv()

# ---------------------------------------------------------------------------
# Initialize configured LLM provider, wrapped in rate limiter
# ---------------------------------------------------------------------------
_raw_llm = create_chat_model()

# Production rate limiter — tuned for Groq Free Tier (30 RPM, 6000 TPM).
# If you upgrade to Developer Tier, increase rpm/tpm accordingly.
if get_provider_name() == "groq":
    llm = GroqRateLimiter(
        llm=_raw_llm,
        rpm=28,              # closer to 30 RPM limit — bucket handles pacing
        tpm=5500,            # closer to 6000 TPM — bucket handles pacing
        max_concurrent=2,    # allow 2 parallel LLM calls for speed
        max_retries=4,
        base_delay=1.5,
        enable_cache=True,
    )
else:
    llm = _raw_llm

# Minimum delay between consecutive LLM-calling nodes (seconds).
# Keep minimal — the token-bucket rate limiter already paces requests.
INTER_NODE_DELAY = 0.3


# --- Agent State ---
class ResearchState(TypedDict):
    """State that flows through the research agent graph."""
    topic: str
    max_iterations: int
    iteration: int
    search_queries: list[str]
    all_queries_used: list[str]
    search_results: list[dict]
    scraped_content: list[dict]
    all_gathered_content: str
    all_sources: list[dict]
    analysis: dict
    report: str
    citation_verification: dict
    status_updates: list[dict]
    visual_planner: bool


# --- Node Functions ---

async def plan_searches(state: ResearchState) -> dict:
    """Use LLM to plan what to search for next."""
    iteration = state.get("iteration", 0) + 1
    existing_findings = state.get("all_gathered_content", "None yet.")
    previous_queries = state.get("all_queries_used", [])
    
    # OPTIMIZATION: Fewer queries = fewer Tavily calls + less scraped content
    # to feed into subsequent LLM calls, reducing both RPM and TPM.
    num_queries = 2 if iteration == 1 else 1
    
    # OPTIMIZATION: Truncate findings more aggressively in the planning prompt.
    # The planner only needs a high-level summary, not full content.
    truncated_findings = existing_findings[:1500] if len(existing_findings) > 1500 else existing_findings
    
    prompt = SEARCH_PLANNER_PROMPT.format(
        topic=state["topic"],
        existing_findings=truncated_findings,
        previous_queries=json.dumps(previous_queries),
        num_queries=num_queries,
    )
    
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    
    # Parse the JSON array of queries
    try:
        content = response.content.strip()
        # Handle markdown code blocks
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        queries = json.loads(content)
        if not isinstance(queries, list):
            queries = [state["topic"]]
    except (json.JSONDecodeError, IndexError):
        queries = [state["topic"], f"{state['topic']} latest developments"]
    
    status = {
        "step": "planning",
        "detail": f"Planned {len(queries)} searches for iteration {iteration}",
        "progress": (iteration - 1) / state["max_iterations"] * 0.1,
        "iteration": iteration,
    }
    
    return {
        "iteration": iteration,
        "search_queries": queries,
        "all_queries_used": previous_queries + queries,
        "status_updates": state.get("status_updates", []) + [status],
    }


async def execute_searches(state: ResearchState) -> dict:
    """Execute all planned searches using Tavily — with inter-query delay."""
    queries = state.get("search_queries", [])
    all_results = []
    
    for i, query in enumerate(queries):
        # OPTIMIZATION: Fewer results per query = less content = less TPM
        results = await tavily_search(query, max_results=3)
        for r in results:
            r["query"] = query
        all_results.extend(results)
        
        # Small delay between Tavily calls to be a good citizen
        if i < len(queries) - 1:
            await asyncio.sleep(0.5)
    
    # Deduplicate by URL
    seen_urls = set()
    unique_results = []
    for r in all_results:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique_results.append(r)
    
    status = {
        "step": "searching",
        "detail": f"Found {len(unique_results)} unique results from {len(queries)} queries",
        "progress": (state["iteration"] - 1) / state["max_iterations"] * 0.3,
        "iteration": state["iteration"],
    }
    
    return {
        "search_results": unique_results,
        "status_updates": state.get("status_updates", []) + [status],
    }


async def read_pages(state: ResearchState) -> dict:
    """Scrape top search results for full content."""
    results = state.get("search_results", [])
    
    # OPTIMIZATION: Only scrape top 3 results (down from 4) to reduce content volume
    urls_to_scrape = [r["url"] for r in results[:3]]
    
    # Scrape pages concurrently
    tasks = [scrape_page(url) for url in urls_to_scrape]
    scraped = await asyncio.gather(*tasks)
    
    # Filter successful scrapes
    successful = [s for s in scraped if s.get("success")]
    
    # Build cumulative content
    existing_content = state.get("all_gathered_content", "")
    existing_sources = state.get("all_sources", [])
    
    new_content_parts = []
    new_sources = []
    
    for s in successful:
        if s["content"]:
            source_num = len(existing_sources) + len(new_sources) + 1
            new_content_parts.append(
                f"[Source {source_num}] ({s['title']})\n{s['content']}"
            )
            new_sources.append({
                "title": s["title"],
                "url": s["url"],
                "snippet": s["content"][:200],
            })
    
    # Also add Tavily snippets for pages we didn't scrape
    for r in results[3:]:
        if r.get("content"):
            source_num = len(existing_sources) + len(new_sources) + 1
            new_content_parts.append(
                f"[Source {source_num}] ({r.get('title', 'Unknown')})\n{r['content']}"
            )
            new_sources.append({
                "title": r.get("title", ""),
                "url": r["url"],
                "snippet": r["content"][:200],
            })
    
    updated_content = existing_content + "\n\n---\n\n" + "\n\n".join(new_content_parts)
    
    status = {
        "step": "reading",
        "detail": f"Read {len(successful)} pages, {len(new_sources)} total new sources",
        "progress": (state["iteration"] - 1) / state["max_iterations"] * 0.5,
        "iteration": state["iteration"],
    }
    
    return {
        "scraped_content": scraped,
        "all_gathered_content": updated_content,
        "all_sources": existing_sources + new_sources,
        "status_updates": state.get("status_updates", []) + [status],
    }


async def analyze(state: ResearchState) -> dict:
    """Analyze gathered content and decide whether to loop or write report."""
    
    # OPTIMIZATION: Truncate content fed to the analyzer to cap TPM usage
    gathered = state.get("all_gathered_content", "")
    truncated = gathered[:3000] if len(gathered) > 3000 else gathered
    
    prompt = CONTENT_ANALYZER_PROMPT.format(
        topic=state["topic"],
        gathered_content=truncated,
        num_sources=len(state.get("all_sources", [])),
        current_iteration=state["iteration"],
        max_iterations=state["max_iterations"],
    )
    
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    
    # Parse analysis JSON
    try:
        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        analysis = json.loads(content)
    except (json.JSONDecodeError, IndexError):
        # If parsing fails, continue if under max iterations
        analysis = {
            "sufficient": state["iteration"] >= state["max_iterations"],
            "reasoning": "Could not parse analysis, using default logic",
            "missing_aspects": [],
            "covered_aspects": [],
        }
    
    # Force sufficient on last iteration
    if state["iteration"] >= state["max_iterations"]:
        analysis["sufficient"] = True
    
    status = {
        "step": "analyzing",
        "detail": f"{'Sufficient info gathered' if analysis.get('sufficient') else 'Need more research — ' + analysis.get('reasoning', '')}",
        "progress": state["iteration"] / state["max_iterations"] * 0.7,
        "iteration": state["iteration"],
    }
    
    # Brief pause to avoid bursting — rate limiter handles the rest
    await asyncio.sleep(INTER_NODE_DELAY)
    
    return {
        "analysis": analysis,
        "status_updates": state.get("status_updates", []) + [status],
    }


async def write_report(state: ResearchState) -> dict:
    """Synthesize all findings into a structured markdown report."""
    sources_list = "\n".join([
        f"[Source {i+1}] {s['title']} — {s['url']}"
        for i, s in enumerate(state.get("all_sources", []))
    ])
    
    # OPTIMIZATION: Limit prompt size to leave token budget for output (max_tokens=4096)
    # ~8000 chars ≈ ~2000-2600 tokens input, leaving ~1500-2000 tokens for output
    gathered_content = state.get("all_gathered_content", "")
    if len(gathered_content) > 8000:
        gathered_content = gathered_content[:8000] + "\n... [Remaining content truncated to save tokens]"
    visual_directive = (
        "\n\nVISUAL DIAGRAMS REQUIREMENT:\n"
        "You MUST include 1-2 Mermaid.js diagrams to visually illustrate key concepts from your research.\n"
        "Rules for diagrams:\n"
        "- Wrap each diagram in a fenced code block with the language `mermaid`\n"
        "- Use ONLY these supported diagram types: flowchart (TD or LR), sequenceDiagram, mindmap, timeline, pie, graph\n"
        "- Keep diagrams simple: maximum 8-12 nodes for flowcharts, 6 entries for pie/timeline\n"
        "- Use double-quoted labels for node text containing special characters: A[\"Node (info)\"]\n"
        "- Do NOT use HTML tags, <br>, or special unicode in node labels\n"
        "- Place diagrams after the relevant section they illustrate\n"
        "- Add a brief caption line before each diagram explaining what it shows\n"
        "Example flowchart:\n"
        "```mermaid\n"
        "flowchart TD\n"
        "    A[\"Research Topic\"] --> B[\"Key Finding 1\"]\n"
        "    A --> C[\"Key Finding 2\"]\n"
        "    B --> D[\"Conclusion\"]\n"
        "    C --> D\n"
        "```\n"
        if state.get("visual_planner") else ""
    )
        
    prompt = REPORT_WRITER_PROMPT.format(
        topic=state["topic"],
        visual_directive=visual_directive,
        gathered_content=gathered_content,
        sources_list=sources_list,
    )
    
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    report = response.content.strip()
    
    # --- Truncation detection & recovery ---
    # Check if the report looks incomplete (ends mid-sentence, no conclusion section)
    looks_truncated = (
        (report and report[-1] not in ".!?\n`*])")
        or len(report) < 200
    )
    has_conclusion = any(
        marker in report.lower()
        for marker in ["## conclusion", "## summary", "## sources", "## references"]
    )
    
    if looks_truncated and not has_conclusion:
        logger.warning("  [Report Writer] Detected truncated report — requesting completion...")
        # Retry with a shorter prompt asking only for conclusion + sources
        completion_prompt = (
            f"The following report on '{state['topic']}' was cut off before completion. "
            f"Write ONLY the missing ending sections (Conclusion and Sources list). "
            f"Keep it concise (under 300 words).\n\n"
            f"REPORT SO FAR:\n{report[-2000:]}\n\n"
            f"SOURCES:\n{sources_list}\n\n"
            f"Continue the report from where it left off. Start writing immediately."
        )
        try:
            completion = await llm.ainvoke([HumanMessage(content=completion_prompt)])
            report = report + "\n\n" + completion.content.strip()
        except Exception as e:
            logger.error(f"  [Report Writer] Completion retry failed: {e}")
            # Append a minimal ending so the report doesn't look broken
            report += (
                "\n\n---\n\n## Sources\n\n"
                + "\n".join(
                    f"{i+1}. [{s['title']}]({s['url']})"
                    for i, s in enumerate(state.get("all_sources", []))
                )
            )
    
    citation_verification = verify_citations(report, state.get("all_sources", []))
    report = append_citation_warning(report, citation_verification)

    status = {
        "step": "writing",
        "detail": (
            "Report generated and citations verified"
            if citation_verification.get("valid")
            else "Report generated with citation warnings"
        ),
        "progress": 1.0,
        "iteration": state["iteration"],
    }
    
    return {
        "report": report,
        "citation_verification": citation_verification,
        "status_updates": state.get("status_updates", []) + [status],
    }


# --- Conditional Edge ---

def should_continue(state: ResearchState) -> str:
    """Decide whether to loop back for more research or write the report."""
    analysis = state.get("analysis", {})
    if analysis.get("sufficient", False):
        return "write_report"
    return "plan_searches"


# --- Build the Graph ---

def build_research_graph():
    """Construct and compile the LangGraph research agent."""
    workflow = StateGraph(ResearchState)
    
    # Add nodes
    workflow.add_node("plan_searches", plan_searches)
    workflow.add_node("execute_searches", execute_searches)
    workflow.add_node("read_pages", read_pages)
    workflow.add_node("analyze", analyze)
    workflow.add_node("write_report", write_report)
    
    # Define edges
    workflow.set_entry_point("plan_searches")
    workflow.add_edge("plan_searches", "execute_searches")
    workflow.add_edge("execute_searches", "read_pages")
    workflow.add_edge("read_pages", "analyze")
    
    # Conditional edge: loop or write report
    workflow.add_conditional_edges(
        "analyze",
        should_continue,
        {
            "plan_searches": "plan_searches",
            "write_report": "write_report",
        }
    )
    
    workflow.add_edge("write_report", END)
    
    # Compile the graph
    graph = workflow.compile()
    return graph


# Singleton graph instance
research_graph = build_research_graph()


async def run_research(topic: str, depth: int = 2, visual_planner: bool = False) -> dict:
    """
    Execute the full research agent pipeline.
    
    Args:
        topic: Research topic string
        depth: Maximum iterations (1-5)
        visual_planner: Instruct the agent to generate Mermaid.js diagrams
    
    Returns:
        Dict with 'report', 'sources', 'queries_used', 'iterations_completed'
    """
    initial_state: ResearchState = {
        "topic": topic,
        "max_iterations": depth,
        "iteration": 0,
        "search_queries": [],
        "all_queries_used": [],
        "search_results": [],
        "scraped_content": [],
        "all_gathered_content": "",
        "all_sources": [],
        "analysis": {},
        "report": "",
        "citation_verification": {},
        "status_updates": [],
        "visual_planner": visual_planner,
    }
    
    # Run the graph
    result = await research_graph.ainvoke(initial_state)
    
    return {
        "report": result.get("report", ""),
        "sources": result.get("all_sources", []),
        "queries_used": result.get("all_queries_used", []),
        "iterations_completed": result.get("iteration", 0),
        "citation_verification": result.get("citation_verification", {}),
        "status_updates": result.get("status_updates", []),
    }


async def run_research_streaming(topic: str, depth: int = 2, visual_planner: bool = False):
    """
    Execute research with streaming status updates via async generator.
    
    Yields StatusEvent-like dicts as the agent progresses through nodes.
    """
    initial_state: ResearchState = {
        "topic": topic,
        "max_iterations": depth,
        "iteration": 0,
        "search_queries": [],
        "all_queries_used": [],
        "search_results": [],
        "scraped_content": [],
        "all_gathered_content": "",
        "all_sources": [],
        "analysis": {},
        "report": "",
        "citation_verification": {},
        "status_updates": [],
        "visual_planner": visual_planner,
    }
    
    last_status_count = 0
    latest_state = dict(initial_state)
    
    async for event in research_graph.astream(initial_state):
        # Each event is a dict keyed by node name
        for node_name, node_output in event.items():
            latest_state.update(node_output)
            status_updates = node_output.get("status_updates", [])
            # Yield any new status updates
            for update in status_updates[last_status_count:]:
                yield {"type": "status", "data": update}
            last_status_count = len(status_updates)
            
            # If this is the write_report node, yield the final result
            if node_name == "write_report" and "report" in node_output:
                yield {
                    "type": "result",
                    "data": {
                        "report": node_output.get("report", ""),
                        "sources": latest_state.get("all_sources", []),
                        "queries_used": latest_state.get("all_queries_used", []),
                        "iterations_completed": latest_state.get("iteration", 0),
                        "citation_verification": node_output.get("citation_verification", {}),
                    }
                }

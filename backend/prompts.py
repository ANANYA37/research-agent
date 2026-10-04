"""Prompt templates for the research agent's LLM calls."""

SEARCH_PLANNER_PROMPT = """You are a research assistant planning web searches for a given topic.

TOPIC: {topic}

EXISTING FINDINGS SO FAR:
{existing_findings}

PREVIOUS QUERIES ALREADY USED:
{previous_queries}

Based on the topic and what has already been found, generate exactly {num_queries} NEW search queries that will help gather comprehensive information. Focus on:
- Different angles and perspectives on the topic
- Filling knowledge gaps from the existing findings
- Recent developments and current state
- Do NOT repeat any of the previous queries listed above

Return ONLY a JSON array of search query strings, nothing else.
Example: ["query one", "query two", "query three"]
"""

CONTENT_ANALYZER_PROMPT = """You are a research analyst evaluating gathered information.

RESEARCH TOPIC: {topic}

ALL GATHERED INFORMATION:
{gathered_content}

NUMBER OF SOURCES: {num_sources}
CURRENT ITERATION: {current_iteration} of {max_iterations}

Analyze the gathered information and determine:
1. What key aspects of the topic are well covered?
2. What important gaps or missing perspectives remain?
3. Is the information sufficient to write a comprehensive report?

Respond in the following JSON format ONLY:
{{
    "sufficient": true or false,
    "covered_aspects": ["aspect1", "aspect2"],
    "missing_aspects": ["gap1", "gap2"],
    "reasoning": "Brief explanation of your assessment",
    "suggested_queries": ["query1", "query2"] 
}}

Note: If this is the final iteration ({current_iteration} == {max_iterations}), set "sufficient" to true regardless — we must write the report with what we have.
"""

REPORT_WRITER_PROMPT = """You are an expert research writer. Synthesize the following research findings into a well-structured, comprehensive markdown report.

RESEARCH TOPIC: {topic}

{visual_directive}

GATHERED INFORMATION:
{gathered_content}

SOURCES:
{sources_list}

Write a professional report following this structure:
1. **Title** — Clear, descriptive title
2. **Executive Summary** — 2-3 paragraph overview of key findings
3. **Key Findings** — Main discoveries organized by theme/subtopic, using ## headers
4. **Analysis** — Your synthesis and connections between findings
5. **Conclusion** — Summary of the current state and potential implications
6. **Sources** — Numbered list of all sources with URLs

Guidelines:
- Write in clear, professional prose
- Use markdown formatting (headers, bold, lists, blockquotes)
- Cite sources inline using [Source N] notation
- Include specific data points, statistics, and quotes where available
- Be objective and balanced — present multiple perspectives
- Aim for 600-1000 words
- Do NOT hallucinate or invent information not present in the gathered content
"""

"""Web search and scraping tools for the research agent."""

import os
import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit
import httpx
from bs4 import BeautifulSoup
from tavily import TavilyClient
from dotenv import load_dotenv
from tenacity import retry, wait_exponential, stop_after_attempt

load_dotenv()

import logging
import ssl

logger = logging.getLogger(__name__)


async def _validate_public_url(url: str) -> None:
    """Reject non-HTTP URLs and any hostname resolving to a non-public address."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP(S) URLs can be scraped")
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ValueError("Could not resolve scrape hostname") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0].split("%", 1)[0]).is_global for item in addresses):
        raise ValueError("Scraping private or reserved IP addresses is not allowed")

# Initialize Tavily client
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


@retry(wait=wait_exponential(multiplier=1, min=1, max=8), stop=stop_after_attempt(3))
async def tavily_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Search the web using Tavily API.
    
    Returns a list of results, each containing:
    - title: Page title
    - url: Page URL
    - content: Snippet/summary from Tavily
    """
    try:
        # Run synchronous client in a thread pool so we don't block the async loop
        response = await asyncio.to_thread(
            tavily_client.search,
            query=query,
            search_depth="basic",
            max_results=max_results,
            include_answer=False,
        )
        
        results = []
        for item in response.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "score": item.get("score", 0),
            })
        
        return results
    
    except Exception as e:
        logger.error(f"[Tavily Search Error] {e}")
        return []


async def scrape_page(url: str, timeout: float = 10.0) -> dict:
    """
    Scrape a web page and extract clean text content.
    
    Uses httpx for async HTTP and BeautifulSoup for parsing.
    Returns dict with 'url', 'title', 'content', 'success'.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        await _validate_public_url(url)
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=timeout,
            verify=True,
        ) as client:
            response = await client.get(url, headers=headers)
            if response.is_redirect:
                raise ValueError("Redirects are not followed while scraping")
            response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Remove unwanted elements
        for tag in soup(["script", "style", "nav", "footer", "header", 
                         "aside", "form", "iframe", "noscript"]):
            tag.decompose()
        
        # Extract title
        title = ""
        if soup.title:
            title = soup.title.get_text(strip=True)
        
        # Extract main content — prefer article/main tags
        main_content = soup.find("article") or soup.find("main") or soup.find("body")
        
        if main_content:
            # Get text with some structure preserved
            paragraphs = main_content.find_all(["p", "h1", "h2", "h3", "h4", "li"])
            text_parts = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                if len(text) > 20:  # Skip very short fragments
                    text_parts.append(text)
            
            content = "\n\n".join(text_parts)
        else:
            content = soup.get_text(separator="\n", strip=True)
        
        # Truncate to avoid token limits — tighter limit for production
        # Each char saved compounds across all sources in LLM prompts
        if len(content) > 800:
            content = content[:800] + "... [truncated]"
        
        return {
            "url": url,
            "title": title,
            "content": content,
            "success": True,
        }
    
    except httpx.TimeoutException:
        return {"url": url, "title": "", "content": "", "success": False, "error": "Timeout"}
    except httpx.HTTPStatusError as e:
        return {"url": url, "title": "", "content": "", "success": False, "error": f"HTTP {e.response.status_code}"}
    except (ssl.SSLError, httpx.ConnectError) as e:
        logger.warning(f"SSL/Connection error scraping {url}: {e}")
        return {"url": url, "title": "", "content": "", "success": False, "error": f"Connection/SSL Error: {e}"}
    except Exception as e:
        return {"url": url, "title": "", "content": "", "success": False, "error": str(e)}

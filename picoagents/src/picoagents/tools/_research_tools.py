"""
Research tools for information retrieval and content extraction.

These tools enable agents to search the web, fetch content, and extract
information from various sources without using LLMs.
"""

import asyncio
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Sequence
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from ..types import ToolResult
from ._base import BaseTool

if TYPE_CHECKING:
    from ..context import AgentContext

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

try:
    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

try:
    import arxiv

    ARXIV_AVAILABLE = True
except ImportError:
    ARXIV_AVAILABLE = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi

    YOUTUBE_TRANSCRIPT_AVAILABLE = True
except ImportError:
    YOUTUBE_TRANSCRIPT_AVAILABLE = False

try:
    import html2text

    HTML2TEXT_AVAILABLE = True
except ImportError:
    HTML2TEXT_AVAILABLE = False


class GoogleSearchTool(BaseTool):
    """Search the web using Google Custom Search API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        cse_id: Optional[str] = None,
        allowed_domains: Optional[List[str]] = None,
        blocked_domains: Optional[List[str]] = None,
    ) -> None:
        super().__init__(
            name="google_search",
            description=(
                "Search the web using Google Custom Search API. Returns titles, URLs, and snippets from search results. "
                "Results are filtered based on allowed/blocked domain rules for security."
            ),
        )
        self.api_key = api_key
        self.cse_id = cse_id
        self.allowed_domains = allowed_domains or []
        self.blocked_domains = blocked_domains or []

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"},
                "num_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5, max: 10)",
                },
                "language": {
                    "type": "string",
                    "description": "Language code for search results (e.g., en, es, fr)",
                },
                "country": {
                    "type": "string",
                    "description": "Country code for search results (e.g., us, uk, ca)",
                },
                "safe_search": {
                    "type": "boolean",
                    "description": "Enable safe search filtering (default: true)",
                },
            },
            "required": ["query"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        if not HTTPX_AVAILABLE:
            return ToolResult(
                success=False,
                result=None,
                error="httpx not installed. Install with: pip install httpx",
                metadata={},
            )

        query = parameters["query"]
        num_results = min(max(1, parameters.get("num_results", 5)), 10)
        language = parameters.get("language", "en")
        country = parameters.get("country")
        safe_search = parameters.get("safe_search", True)

        if not self.api_key or not self.cse_id:
            return ToolResult(
                success=False,
                result=None,
                error="Google API key and CSE ID not provided. Pass api_key and cse_id to GoogleSearchTool constructor.",
                metadata={"query": query},
            )

        try:
            search_params = {
                "key": self.api_key,
                "cx": self.cse_id,
                "q": query,
                "num": num_results,
                "hl": language,
                "safe": "active" if safe_search else "off",
            }

            if country:
                search_params["gl"] = country

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params=search_params,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

            results = []
            if "items" in data:
                for item in data.get("items", []):
                    url = item.get("link", "")

                    # Apply domain filtering
                    if self._is_domain_allowed(url):
                        results.append(
                            {
                                "title": item.get("title", ""),
                                "url": url,
                                "snippet": item.get("snippet", ""),
                            }
                        )

            return ToolResult(
                success=True,
                result=results,
                error=None,
                metadata={
                    "query": query,
                    "count": len(results),
                    "filtered": len(data.get("items", [])) - len(results),
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                result=None,
                error=f"Google search failed: {str(e)}",
                metadata={"query": query},
            )

    def _is_domain_allowed(self, url: str) -> bool:
        """
        Check if URL passes domain filtering rules.

        Args:
            url: URL to check

        Returns:
            True if URL is allowed, False otherwise
        """
        try:
            from urllib.parse import urlparse

            domain = urlparse(url).netloc.lower()

            # Check blocked domains first
            if self.blocked_domains:
                for blocked in self.blocked_domains:
                    blocked_lower = blocked.lower()
                    # Match exact domain or subdomain (ends with .blocked_domain)
                    if domain == blocked_lower or domain.endswith("." + blocked_lower):
                        return False

            # If allowed_domains is specified, only allow those
            if self.allowed_domains:
                for allowed in self.allowed_domains:
                    allowed_lower = allowed.lower()
                    # Match exact domain or subdomain (ends with .allowed_domain)
                    if domain == allowed_lower or domain.endswith("." + allowed_lower):
                        return True
                return False  # Not in allowed list

            # No restrictions or passed all checks
            return True
        except Exception:
            # If parsing fails, be conservative and block
            return False


class WebSearchTool(BaseTool):
    """Search with anonymous Parallel MCP, or Tavily when a key is supplied.

    Set provider explicitly to keep that selection even without credentials.
    A failed provider never silently falls back to another service.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        allowed_domains: Optional[List[str]] = None,
        blocked_domains: Optional[List[str]] = None,
        *,
        provider: Optional[Literal["parallel", "tavily"]] = None,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(
            name="web_search",
            description=(
                "Search the web for information. Returns titles, URLs, and snippets from search results. "
                "Results are filtered based on allowed/blocked domain rules for security."
            ),
        )
        if provider not in (None, "parallel", "tavily"):
            raise ValueError("provider must be 'parallel' or 'tavily'")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.provider = provider or ("tavily" if api_key else "parallel")
        self.timeout = timeout
        self.api_key = api_key
        self.allowed_domains = allowed_domains or []
        self.blocked_domains = blocked_domains or []

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"},
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5)",
                },
            },
            "required": ["query"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """Execute a standalone search; each call is a new research run."""
        return await self._execute(parameters, str(uuid4()))

    async def execute_with_context(
        self, parameters: Dict[str, Any], context: "AgentContext"
    ) -> ToolResult:
        # AgentContext.reset() clears metadata. Never reuse user/session IDs,
        # which may contain personal data, as Parallel conversation identities.
        key = "_parallel_search_session_id"
        if self.provider == "parallel" and key not in context.metadata:
            context.metadata[key] = str(uuid4())
        return await self._execute(parameters, context.metadata.get(key))

    async def _execute(
        self, parameters: Dict[str, Any], session_id: Optional[str]
    ) -> ToolResult:
        if self.provider == "parallel":
            return await self._execute_parallel(parameters, session_id)
        if not HTTPX_AVAILABLE:
            return ToolResult(
                success=False,
                result=None,
                error="httpx not installed. Install with: pip install httpx",
                metadata={},
            )

        query = parameters["query"]
        max_results = parameters.get("max_results", 5)

        if not self.api_key:
            return ToolResult(
                success=False,
                result=None,
                error="Tavily API key not provided. Pass api_key to WebSearchTool constructor.",
                metadata={"query": query},
            )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.api_key,
                        "query": query,
                        "max_results": max_results,
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()

            results = []
            for item in data.get("results", []):
                url = item.get("url", "")

                # Apply domain filtering
                if self._is_domain_allowed(url):
                    results.append(
                        {
                            "title": item.get("title", ""),
                            "url": url,
                            "snippet": item.get("content", ""),
                        }
                    )

            return ToolResult(
                success=True,
                result=results,
                error=None,
                metadata={
                    "query": query,
                    "count": len(results),
                    "filtered": len(data.get("results", [])) - len(results),
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                result=None,
                error=f"Web search failed: {str(e)}",
                metadata={"query": query},
            )

    async def _execute_parallel(
        self, parameters: Dict[str, Any], session_id: Optional[str]
    ) -> ToolResult:
        query = parameters["query"]
        metadata = {"query": query, "provider": "parallel"}
        try:
            from ._parallel_search import search

            max_results = parameters.get("max_results", 5)
            if (
                isinstance(max_results, bool)
                or not isinstance(max_results, int)
                or max_results < 1
            ):
                raise ValueError("max_results must be a positive integer")
            data = await asyncio.wait_for(search(query, session_id), self.timeout)
            items = data["results"]
            results = []
            filtered = 0
            for item in items:
                url = item["url"]
                if not self._is_domain_allowed(url):
                    filtered += 1
                    continue
                results.append(
                    {
                        "title": item.get("title") or "",
                        "url": url,
                        "snippet": "\n".join(item["excerpts"]),
                    }
                )
            results = results[:max_results]
            return ToolResult(
                success=True,
                result=results,
                error=None,
                metadata={**metadata, "count": len(results), "filtered": filtered},
            )
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                result=None,
                error="Parallel search timed out",
                metadata=metadata,
            )
        except Exception as e:
            return ToolResult(
                success=False,
                result=None,
                error=f"Parallel search failed: {e}",
                metadata=metadata,
            )

    def _is_domain_allowed(self, url: str) -> bool:
        """
        Check if URL passes domain filtering rules.

        Args:
            url: URL to check

        Returns:
            True if URL is allowed, False otherwise
        """
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                return False
            domain = parsed.hostname.lower()

            # Check blocked domains first
            if self.blocked_domains:
                for blocked in self.blocked_domains:
                    blocked_lower = blocked.lower()
                    # Match exact domain or subdomain (ends with .blocked_domain)
                    if domain == blocked_lower or domain.endswith("." + blocked_lower):
                        return False

            # If allowed_domains is specified, only allow those
            if self.allowed_domains:
                for allowed in self.allowed_domains:
                    allowed_lower = allowed.lower()
                    # Match exact domain or subdomain (ends with .allowed_domain)
                    if domain == allowed_lower or domain.endswith("." + allowed_lower):
                        return True
                return False  # Not in allowed list

            # No restrictions or passed all checks
            return True
        except Exception:
            # If parsing fails, be conservative and block
            return False


class WebFetchTool(BaseTool):
    """Fetch content from a URL."""

    def __init__(
        self,
        allowed_domains: Optional[List[str]] = None,
        blocked_domains: Optional[List[str]] = None,
        max_content_length: int = 100000,
    ) -> None:
        super().__init__(
            name="web_fetch",
            description=(
                "Fetch content from a URL in multiple formats: raw HTML, plain text, or structured markdown. "
                "Markdown format preserves document structure (headings, links, lists, tables) for better analysis. "
                "URL access is filtered based on allowed/blocked domain rules for security. "
                "Content is truncated if it exceeds maximum length."
            ),
        )
        self.allowed_domains = allowed_domains or []
        self.blocked_domains = blocked_domains or []
        self.max_content_length = max_content_length

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "output_format": {
                    "type": "string",
                    "enum": ["html", "text", "markdown"],
                    "description": "Output format: 'html' (raw HTML), 'text' (plain text), or 'markdown' (structured markdown). Default: 'html'",
                },
            },
            "required": ["url"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        if not HTTPX_AVAILABLE:
            return ToolResult(
                success=False,
                result=None,
                error="httpx not installed. Install with: pip install httpx",
                metadata={},
            )

        url = parameters["url"]
        output_format = parameters.get("output_format", "html")

        # Handle legacy extract_text parameter for backward compatibility
        if "extract_text" in parameters and parameters["extract_text"]:
            output_format = "text"

        try:
            parsed_url = urlparse(url)
            if not parsed_url.scheme or not parsed_url.netloc:
                raise ValueError("Invalid URL format")

            # Check domain filtering
            if not self._is_domain_allowed(url):
                return ToolResult(
                    success=False,
                    result=None,
                    error=f"URL domain is blocked or not in allowed list: {parsed_url.netloc}",
                    metadata={"url": url, "domain": parsed_url.netloc},
                )

            # Add browser-like headers
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }

            async with httpx.AsyncClient(
                follow_redirects=True, headers=headers
            ) as client:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()

            content = response.text
            original_length = len(content)

            # Process based on output format
            if output_format == "markdown":
                if not HTML2TEXT_AVAILABLE:
                    return ToolResult(
                        success=False,
                        result=None,
                        error="html2text not installed. Install with: pip install html2text or pip install picoagents[research]",
                        metadata={"url": url},
                    )

                # Configure html2text converter
                h = html2text.HTML2Text()
                h.body_width = 0  # Don't wrap lines
                h.ignore_images = False
                h.ignore_emphasis = False
                h.ignore_links = False
                h.ignore_tables = False

                content = h.handle(content)

            elif output_format == "text":
                if not BS4_AVAILABLE:
                    return ToolResult(
                        success=False,
                        result=None,
                        error="beautifulsoup4 not installed. Install with: pip install beautifulsoup4",
                        metadata={"url": url},
                    )

                soup = BeautifulSoup(content, "html.parser")
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                text = soup.get_text()
                lines = (line.strip() for line in text.splitlines())
                content = "\n".join(line for line in lines if line)

            # Truncate content if too long (after processing)
            was_truncated = False
            if len(content) > self.max_content_length:
                content = content[: self.max_content_length]
                was_truncated = True

            return ToolResult(
                success=True,
                result=content,
                error=None,
                metadata={
                    "url": url,
                    "output_format": output_format,
                    "content_length": len(content),
                    "original_length": original_length,
                    "status_code": response.status_code,
                    "truncated": was_truncated,
                    "max_length": self.max_content_length,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                result=None,
                error=f"Failed to fetch URL: {str(e)}",
                metadata={"url": url},
            )

    def _is_domain_allowed(self, url: str) -> bool:
        """
        Check if URL passes domain filtering rules.

        Args:
            url: URL to check

        Returns:
            True if URL is allowed, False otherwise
        """
        try:
            from urllib.parse import urlparse

            domain = urlparse(url).netloc.lower()

            # Check blocked domains first
            if self.blocked_domains:
                for blocked in self.blocked_domains:
                    blocked_lower = blocked.lower()
                    # Match exact domain or subdomain (ends with .blocked_domain)
                    if domain == blocked_lower or domain.endswith("." + blocked_lower):
                        return False

            # If allowed_domains is specified, only allow those
            if self.allowed_domains:
                for allowed in self.allowed_domains:
                    allowed_lower = allowed.lower()
                    # Match exact domain or subdomain (ends with .allowed_domain)
                    if domain == allowed_lower or domain.endswith("." + allowed_lower):
                        return True
                return False  # Not in allowed list

            # No restrictions or passed all checks
            return True
        except Exception:
            # If parsing fails, be conservative and block
            return False


class ExtractTextTool(BaseTool):
    """Extract clean text content from HTML."""

    def __init__(self) -> None:
        super().__init__(
            name="extract_text",
            description="Extract clean text content from HTML, removing scripts, styles, and tags.",
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "html": {
                    "type": "string",
                    "description": "HTML content to extract text from",
                },
                "selector": {
                    "type": "string",
                    "description": "Optional CSS selector to extract specific elements",
                },
            },
            "required": ["html"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        if not BS4_AVAILABLE:
            return ToolResult(
                success=False,
                result=None,
                error="beautifulsoup4 not installed. Install with: pip install beautifulsoup4",
                metadata={},
            )

        html = parameters["html"]
        selector = parameters.get("selector")

        try:
            soup = BeautifulSoup(html, "html.parser")

            if selector:
                elements = soup.select(selector)
                if not elements:
                    raise ValueError(f"No elements found matching selector: {selector}")
                text_parts = [elem.get_text(strip=True) for elem in elements]
                text = "\n\n".join(text_parts)
            else:
                for script in soup(["script", "style"]):
                    script.decompose()
                text = soup.get_text()
                lines = (line.strip() for line in text.splitlines())
                text = "\n".join(line for line in lines if line)

            return ToolResult(
                success=True,
                result=text,
                error=None,
                metadata={"length": len(text), "selector": selector},
            )

        except Exception as e:
            return ToolResult(
                success=False,
                result=None,
                error=f"Text extraction failed: {str(e)}",
                metadata={},
            )


class ArxivSearchTool(BaseTool):
    """Search arXiv for academic papers."""

    def __init__(self) -> None:
        super().__init__(
            name="arxiv_search",
            description="Search arXiv for academic papers. Returns titles, authors, abstracts, and PDF URLs.",
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (can use arXiv query syntax)",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5)",
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["relevance", "lastUpdatedDate", "submittedDate"],
                    "description": "Sort order for results (default: relevance)",
                },
            },
            "required": ["query"],
        }

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        if not ARXIV_AVAILABLE:
            return ToolResult(
                success=False,
                result=None,
                error="arxiv package not installed. Install with: pip install arxiv",
                metadata={},
            )

        query = parameters["query"]
        max_results = parameters.get("max_results", 5)
        sort_by_str = parameters.get("sort_by", "relevance")

        try:
            sort_by_map = {
                "relevance": arxiv.SortCriterion.Relevance,
                "lastUpdatedDate": arxiv.SortCriterion.LastUpdatedDate,
                "submittedDate": arxiv.SortCriterion.SubmittedDate,
            }
            sort_by = sort_by_map.get(sort_by_str, arxiv.SortCriterion.Relevance)

            search = arxiv.Search(query=query, max_results=max_results, sort_by=sort_by)

            results = []
            for paper in search.results():
                results.append(
                    {
                        "title": paper.title,
                        "authors": [author.name for author in paper.authors],
                        "abstract": paper.summary,
                        "pdf_url": paper.pdf_url,
                        "published": paper.published.isoformat(),
                        "arxiv_id": paper.entry_id.split("/")[-1],
                    }
                )

            return ToolResult(
                success=True,
                result=results,
                error=None,
                metadata={"query": query, "count": len(results)},
            )

        except Exception as e:
            return ToolResult(
                success=False,
                result=None,
                error=f"arXiv search failed: {str(e)}",
                metadata={"query": query},
            )


class YouTubeCaptionTool(BaseTool):
    """Extract captions/transcripts from YouTube videos."""

    def __init__(self) -> None:
        super().__init__(
            name="youtube_caption",
            description=(
                "Extract captions/transcripts from YouTube videos. "
                "Provide a YouTube URL and get the full transcript text. "
                "Supports both standard YouTube URLs and youtu.be short links."
            ),
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "YouTube video URL (e.g., https://www.youtube.com/watch?v=VIDEO_ID or https://youtu.be/VIDEO_ID)",
                },
                "language": {
                    "type": "string",
                    "description": "Preferred caption language code (e.g., 'en', 'es', 'fr'). Defaults to 'en'.",
                },
            },
            "required": ["url"],
        }

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from various YouTube URL formats."""
        # Handle youtu.be short links
        if "youtu.be" in url:
            parsed = urlparse(url)
            return parsed.path.lstrip("/").split("?")[0]

        # Handle standard YouTube URLs
        parsed = urlparse(url)
        if parsed.hostname in ("www.youtube.com", "youtube.com", "m.youtube.com"):
            if parsed.path == "/watch":
                query_params = parse_qs(parsed.query)
                return query_params.get("v", [None])[0]
            elif parsed.path.startswith("/embed/"):
                return parsed.path.split("/")[2]
            elif parsed.path.startswith("/v/"):
                return parsed.path.split("/")[2]

        return None

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        if not YOUTUBE_TRANSCRIPT_AVAILABLE:
            return ToolResult(
                success=False,
                result=None,
                error="youtube-transcript-api not installed. Install with: pip install youtube-transcript-api",
                metadata={},
            )

        url = parameters["url"]
        language = parameters.get("language", "en")

        try:
            # Extract video ID
            video_id = self._extract_video_id(url)
            if not video_id:
                return ToolResult(
                    success=False,
                    result=None,
                    error=f"Could not extract video ID from URL: {url}",
                    metadata={"url": url},
                )

            # Get transcript using youtube-transcript-api
            # Create an instance of the API
            yt_api = YouTubeTranscriptApi()

            # Get list of available transcripts
            try:
                transcript_list = yt_api.list(video_id)
            except Exception as e:
                error_msg = str(e)
                # Provide more helpful error messages for common issues
                if "no element found" in error_msg.lower():
                    error_msg = (
                        "Could not fetch video transcripts. This may be due to: "
                        "(1) YouTube rate limiting/bot detection, "
                        "(2) video has no captions, "
                        "(3) regional restrictions, or "
                        "(4) the video is private/unavailable. "
                        f"Original error: {error_msg}"
                    )
                return ToolResult(
                    success=False,
                    result=None,
                    error=error_msg,
                    metadata={"video_id": video_id, "url": url},
                )

            # Get available languages
            available_languages = [t.language_code for t in transcript_list]

            # Try to fetch transcript in the requested language
            try:
                fetched = transcript_list.find_transcript([language])
                actual_language = fetched.language_code
            except Exception:
                # If requested language not available, use the first available
                try:
                    fetched = transcript_list.find_transcript(available_languages[:1])
                    actual_language = fetched.language_code
                except Exception as e:
                    return ToolResult(
                        success=False,
                        result=None,
                        error=f"No captions available for this video: {str(e)}",
                        metadata={
                            "video_id": video_id,
                            "url": url,
                            "available_languages": available_languages,
                        },
                    )

            # Fetch the transcript data
            transcript_data = fetched.fetch()

            # Combine all transcript segments into one text
            # transcript_data is a FetchedTranscript with snippets
            transcript = " ".join(snippet.text for snippet in transcript_data)

            # Clean up the transcript
            transcript = re.sub(r"\s+", " ", transcript).strip()

            return ToolResult(
                success=True,
                result=transcript,
                error=None,
                metadata={
                    "video_id": video_id,
                    "url": url,
                    "language": actual_language,
                    "length": len(transcript),
                    "available_languages": available_languages,
                    "segment_count": len(transcript_data),
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                result=None,
                error=f"Failed to extract captions: {str(e)}",
                metadata={"url": url},
            )


def create_research_tools(
    tavily_api_key: Optional[str] = None,
    google_api_key: Optional[str] = None,
    google_cse_id: Optional[str] = None,
    *,
    web_search_provider: Optional[Literal["parallel", "tavily", "disabled"]] = None,
) -> Sequence[BaseTool]:
    """
    Create a list of research tools for information retrieval.

    Args:
        tavily_api_key: Optional API key for Tavily web search
        google_api_key: Optional API key for Google Custom Search
        google_cse_id: Optional Custom Search Engine ID for Google search
        web_search_provider: Explicit web-search selection, or "disabled" to
            omit WebSearchTool. By default, preserve supplied Tavily/Google
            credentials; otherwise use anonymous Parallel Search MCP.

    Returns:
        List of research tool instances

    Raises:
        ImportError: If required dependencies are not installed
    """
    if web_search_provider not in (None, "parallel", "tavily", "disabled"):
        raise ValueError("Unknown web_search_provider")
    tools: List[BaseTool] = []

    if HTTPX_AVAILABLE:
        # Add Google search if credentials provided
        if google_api_key and google_cse_id:
            tools.append(GoogleSearchTool(api_key=google_api_key, cse_id=google_cse_id))

        # A configured Google-only tool set stays Google-only. Explicit choices
        # take precedence; provider failures never trigger a fallback.
        if web_search_provider != "disabled" and (
            web_search_provider is not None
            or tavily_api_key
            or not (google_api_key and google_cse_id)
        ):
            tools.append(
                WebSearchTool(api_key=tavily_api_key, provider=web_search_provider)
            )

        tools.append(WebFetchTool())

    if BS4_AVAILABLE:
        tools.append(ExtractTextTool())

    if ARXIV_AVAILABLE:
        tools.append(ArxivSearchTool())

    if YOUTUBE_TRANSCRIPT_AVAILABLE:
        tools.append(YouTubeCaptionTool())

    if not tools:
        raise ImportError(
            "No research tools available. Install dependencies with: "
            "pip install httpx beautifulsoup4 arxiv youtube-transcript-api"
        )

    return tools

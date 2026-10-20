"""Anonymous Search MCP calls using PicoAgents' supported HTTP transport."""

import json
from typing import Any, Dict, Optional


async def search(query: str, session_id: Optional[str]) -> Dict[str, Any]:
    try:
        from mcp.client import Client
        from mcp.types import TextContent
    except ImportError as e:
        raise ImportError(
            "Parallel search requires MCP support. Install 'picoagents[mcp]' "
            "or 'picoagents[research]'."
        ) from e

    from ._mcp._config import HTTPServerConfig
    from ._mcp._transports import build_transport

    config = HTTPServerConfig(
        server_id="parallel-search",
        url="https://search.parallel.ai/mcp",
        headers={
            "User-Agent": "picoagents (https://github.com/victordibia/designing-multiagent-systems)"
        },
    )
    # The connection belongs to this call, but its identity belongs to the
    # conversation supplied by AgentContext, never to a cached client/tool.
    async with Client(build_transport(config)) as client:
        result = await client.call_tool(
            "web_search",
            arguments={
                "objective": query,
                "search_queries": [query],
                "session_id": session_id,
            },
        )
    text = "\n".join(c.text for c in result.content if isinstance(c, TextContent))
    if result.is_error:
        raise RuntimeError(text or "Parallel MCP returned an error")
    data = result.structured_content
    if data is None:
        data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("Invalid Parallel search response")
    for item in data["results"]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("url"), str)
            or not isinstance(item.get("excerpts"), list)
            or not all(isinstance(excerpt, str) for excerpt in item["excerpts"])
            or item.get("title") is not None
            and not isinstance(item["title"], str)
        ):
            raise ValueError("Invalid Parallel search result")
    return data

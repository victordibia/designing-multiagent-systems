"""
Lab server: basic tools.

A minimal MCP 2.0 server exercising plain tool calls, structured output,
and progress reporting. Used as a WebUI playground preset and a CI fixture.

Run standalone (stdio):
    python -m picoagents.webui.mcp.servers.basic_server

Or over streamable HTTP:
    python -m picoagents.webui.mcp.servers.basic_server --http
"""

import sys

from mcp.server.mcpserver import Context, MCPServer
from pydantic import BaseModel

server = MCPServer(
    "pico-lab-basic",
    instructions="Lab server with simple tools for testing MCP clients.",
)


@server.tool()
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


class WordStats(BaseModel):
    words: int
    characters: int
    longest_word: str


@server.tool()
def word_stats(text: str) -> WordStats:
    """Compute word statistics for a text (structured output)."""
    words = text.split()
    return WordStats(
        words=len(words),
        characters=len(text),
        longest_word=max(words, key=len) if words else "",
    )


@server.tool()
async def slow_echo(text: str, steps: int, ctx: Context) -> str:
    """Echo text after reporting progress over `steps` increments."""
    import anyio

    steps = max(1, min(steps, 10))
    for i in range(steps):
        await anyio.sleep(0.1)
        await ctx.report_progress(i + 1, steps, f"step {i + 1}/{steps}")
    return text


if __name__ == "__main__":
    if "--http" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8000
        server.run("streamable-http", port=port)
    else:
        server.run("stdio")

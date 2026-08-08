"""
Configuration classes for MCP server connections.

Supports multiple transport types: stdio, streamable HTTP, in-memory, and
legacy SSE (deprecated in the 2026-07-28 spec).
"""

from typing import Any, Dict, List, Literal, Optional

TransportType = Literal["stdio", "sse", "streamable-http", "memory"]


class MCPServerConfig:
    """Base configuration for an MCP server connection."""

    def __init__(
        self,
        server_id: str,
        transport: TransportType,
        env: Optional[Dict[str, str]] = None,
    ):
        self.server_id = server_id
        """Unique identifier for this server"""

        self.transport = transport
        """Transport type: 'stdio', 'streamable-http', 'memory', or legacy 'sse'"""

        self.env = env
        """Environment variables"""


class StdioServerConfig(MCPServerConfig):
    """
    Configuration for stdio transport MCP servers.

    This transport spawns a subprocess and communicates via stdin/stdout.
    Best for local development and testing.

    Example:
        ```python
        config = StdioServerConfig(
            server_id="filesystem",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        )
        ```
    """

    def __init__(
        self,
        server_id: str,
        command: str,
        args: List[str],
        env: Optional[Dict[str, str]] = None,
    ):
        super().__init__(server_id, "stdio", env)
        self.command = command
        """Command to start the MCP server (e.g., 'python', 'node', 'npx')"""

        self.args = args
        """Arguments for the server command"""


class HTTPServerConfig(MCPServerConfig):
    """
    Configuration for HTTP/SSE transport MCP servers.

    Use this for remote servers or production deployments.
    Supports both SSE and streamable HTTP transports.

    Example:
        ```python
        # Streamable HTTP (recommended)
        config = HTTPServerConfig(
            server_id="weather",
            url="http://api.example.com/mcp",
            transport="streamable-http"
        )

        # SSE
        config = HTTPServerConfig(
            server_id="github",
            url="http://localhost:3000/sse",
            transport="sse"
        )
        ```
    """

    def __init__(
        self,
        server_id: str,
        url: str,
        transport: Literal["sse", "streamable-http"] = "streamable-http",
        headers: Optional[Dict[str, str]] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        super().__init__(server_id, transport, env)
        self.url = url
        """Server URL (e.g., 'http://localhost:8000/mcp')"""

        self.headers = headers
        """Optional HTTP headers (e.g., for authentication)"""


class InMemoryServerConfig(MCPServerConfig):
    """
    Configuration for an in-process MCP server (no subprocess, no network).

    Wraps an `mcp.server.mcpserver.MCPServer` (or low-level `Server`) instance
    directly. Used for tests and built-in demo servers in the WebUI playground.

    Example:
        ```python
        from mcp.server.mcpserver import MCPServer

        server = MCPServer("demo")

        @server.tool()
        def add(a: int, b: int) -> int:
            return a + b

        config = InMemoryServerConfig(server_id="demo", server=server)
        ```
    """

    def __init__(self, server_id: str, server: Any):
        super().__init__(server_id, "memory", None)
        self.server = server
        """The in-process MCP server instance"""

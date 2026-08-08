"""
MCP (Model Context Protocol) integration for PicoAgents.

This module provides integration with MCP servers, allowing agents to use
tools from any MCP-compliant server as if they were native PicoAgents tools.

Example:
    ```python
    from picoagents.tools import create_mcp_tools, StdioServerConfig

    # Configure MCP server
    config = StdioServerConfig(
        server_id="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    )

    # Create tools
    manager, tools = await create_mcp_tools([config])

    # Use with agent
    agent = Agent(name="mcp_agent", tools=tools, ...)
    ```
"""

from ._config import (
    HTTPServerConfig,
    InMemoryServerConfig,
    MCPServerConfig,
    StdioServerConfig,
    TransportType,
)
from ._integration import create_mcp_tools
from ._tap import WireFrame, WireTap
from ._tool import MCPTool

from ._client import MCPClientManager

__all__ = [
    "MCPTool",
    "MCPClientManager",
    "MCPServerConfig",
    "StdioServerConfig",
    "HTTPServerConfig",
    "InMemoryServerConfig",
    "TransportType",
    "WireFrame",
    "WireTap",
    "create_mcp_tools",
]

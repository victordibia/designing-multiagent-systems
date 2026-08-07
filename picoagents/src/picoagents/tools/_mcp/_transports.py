"""
Transport construction for MCP servers (mcp SDK 2.0).

Builds Transport objects (async context managers yielding read/write streams)
the high-level `mcp.client.Client` accepts. Supports stdio, streamable HTTP,
and legacy SSE (deprecated in the 2026-07-28 spec, kept for older servers).
"""

from typing import Any

from mcp.client.stdio import StdioServerParameters, stdio_client

from ._config import (
    HTTPServerConfig,
    InMemoryServerConfig,
    MCPServerConfig,
    StdioServerConfig,
)


def build_transport(config: MCPServerConfig) -> Any:
    """
    Build a Transport for a server config.

    Args:
        config: Server configuration

    Returns:
        An async context manager yielding (read_stream, write_stream),
        suitable for passing to `mcp.client.Client`.

    Raises:
        ValueError: If transport type is not supported
    """
    if isinstance(config, InMemoryServerConfig):
        from mcp.client._memory import InMemoryTransport

        return InMemoryTransport(config.server)
    if isinstance(config, StdioServerConfig):
        return stdio_client(
            StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env,
            )
        )
    if isinstance(config, HTTPServerConfig):
        if config.transport == "sse":
            return _build_sse(config)
        return _build_streamable_http(config)
    raise ValueError(f"Unknown transport: {config.transport}")


def _build_streamable_http(config: HTTPServerConfig) -> Any:
    from mcp.client.streamable_http import streamable_http_client

    if config.headers:
        from mcp.shared._httpx_utils import create_mcp_http_client

        return streamable_http_client(
            config.url, http_client=create_mcp_http_client(headers=config.headers)
        )
    return streamable_http_client(config.url)


def _build_sse(config: HTTPServerConfig) -> Any:
    """Legacy HTTP+SSE transport - deprecated in the 2026-07-28 spec."""
    from mcp.client.sse import sse_client

    return sse_client(config.url, headers=config.headers)

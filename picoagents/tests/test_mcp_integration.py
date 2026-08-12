"""
Tests for MCP (Model Context Protocol) integration.

These tests verify that PicoAgents can correctly:
1. Configure MCP servers (stdio, HTTP, SSE transports)
2. Connect to MCP servers and discover tools
3. Wrap MCP tools as PicoAgents tools
4. Execute MCP tools and handle results
5. Manage server lifecycle (connect/disconnect)

Uses mock MCP servers to avoid external dependencies.
"""

import pytest

# Try importing MCP dependencies
pytest.importorskip("mcp", reason="MCP not installed, skipping MCP tests")

import anyio
from mcp.types import CallToolResult, TextContent, Tool

from picoagents.tools import (
    HTTPServerConfig,
    MCPClientManager,
    MCP_AVAILABLE,
    StdioServerConfig,
    create_mcp_tools,
)


@pytest.fixture
def anyio_backend():
    """Use asyncio as the async backend."""
    return "asyncio"


# ============================================================================
# Configuration Tests
# ============================================================================


def test_stdio_config():
    """Test stdio server configuration."""
    config = StdioServerConfig(
        server_id="test_server",
        command="python",
        args=["-m", "mcp_server"],
        env={"API_KEY": "test123"},
    )

    assert config.server_id == "test_server"
    assert config.transport == "stdio"
    assert config.command == "python"
    assert config.args == ["-m", "mcp_server"]
    assert config.env == {"API_KEY": "test123"}


def test_http_config_streamable():
    """Test streamable HTTP server configuration."""
    config = HTTPServerConfig(
        server_id="http_server",
        url="http://localhost:8000/mcp",
        transport="streamable-http",
        headers={"Authorization": "Bearer token"},
    )

    assert config.server_id == "http_server"
    assert config.transport == "streamable-http"
    assert config.url == "http://localhost:8000/mcp"
    assert config.headers == {"Authorization": "Bearer token"}


def test_http_config_sse():
    """Test SSE server configuration."""
    config = HTTPServerConfig(
        server_id="sse_server", url="http://localhost:3000/sse", transport="sse"
    )

    assert config.server_id == "sse_server"
    assert config.transport == "sse"
    assert config.url == "http://localhost:3000/sse"


# ============================================================================
# Client Manager Tests
# ============================================================================


def test_client_manager_initialization():
    """Test MCPClientManager initializes correctly."""
    manager = MCPClientManager()

    assert len(manager.list_servers()) == 0
    assert manager.get_tools() == []
    assert not manager.is_connected("any_server")


def test_client_manager_add_server():
    """Test adding servers to manager."""
    manager = MCPClientManager()

    config1 = StdioServerConfig(server_id="server1", command="python", args=[])
    config2 = StdioServerConfig(server_id="server2", command="node", args=[])

    manager.add_server(config1)
    manager.add_server(config2)

    assert len(manager.list_servers()) == 2
    assert "server1" in manager.list_servers()
    assert "server2" in manager.list_servers()


def test_client_manager_duplicate_server():
    """Test that adding duplicate server raises error."""
    manager = MCPClientManager()

    config = StdioServerConfig(server_id="dup", command="python", args=[])
    manager.add_server(config)

    with pytest.raises(ValueError, match="already registered"):
        manager.add_server(config)


@pytest.mark.anyio
async def test_client_manager_connect_unknown_server():
    """Test connecting to unregistered server raises error."""
    manager = MCPClientManager()

    with pytest.raises(ValueError, match="Unknown server"):
        await manager.connect("unknown")


# ============================================================================
# Mock MCP Server Integration Tests
# ============================================================================


@pytest.mark.anyio
async def test_mcp_tool_creation_from_mock():
    """Test MCPTool creation from mock MCP server."""
    from unittest.mock import AsyncMock, MagicMock

    from picoagents.tools._mcp import MCPTool

    # Create a mock client manager
    mock_manager = MagicMock(spec=MCPClientManager)
    mock_client = AsyncMock()

    # Mock call_tool response
    mock_result = CallToolResult(
        content=[TextContent(type="text", text="Mock tool result")],
        isError=False,
    )
    mock_client.call_tool = AsyncMock(return_value=mock_result)
    mock_manager.get_client = AsyncMock(return_value=mock_client)

    # Create MCPTool
    tool = MCPTool(
        mcp_tool_name="test_tool",
        mcp_tool_description="A test tool",
        mcp_tool_schema={
            "type": "object",
            "properties": {"arg": {"type": "string"}},
            "required": ["arg"],
        },
        client_manager=mock_manager,
        server_id="mock_server",
    )

    # Verify tool properties
    assert tool.name == "mcp_mock_server_test_tool"
    assert tool.mcp_tool_name == "test_tool"
    assert tool.server_id == "mock_server"
    assert tool.description == "A test tool"

    # Test tool execution
    result = await tool.execute({"arg": "test_value"})

    assert result.success is True
    assert result.result == "Mock tool result"
    assert result.metadata["mcp_server"] == "mock_server"
    assert result.metadata["mcp_tool"] == "test_tool"

    # Verify the client was fetched correctly
    mock_manager.get_client.assert_called_once_with("mock_server")
    mock_client.call_tool.assert_called_once_with(
        "test_tool", arguments={"arg": "test_value"}
    )


@pytest.mark.anyio
async def test_mcp_tool_handles_errors():
    """Test MCPTool handles errors from MCP server."""
    from unittest.mock import AsyncMock, MagicMock

    from picoagents.tools._mcp import MCPTool

    # Create a mock that raises an error
    mock_manager = MagicMock(spec=MCPClientManager)
    mock_manager.get_client = AsyncMock(side_effect=ConnectionError("Server down"))

    tool = MCPTool(
        mcp_tool_name="failing_tool",
        mcp_tool_description="A failing tool",
        mcp_tool_schema={"type": "object", "properties": {}},
        client_manager=mock_manager,
        server_id="failing_server",
    )

    # Test tool execution with error
    result = await tool.execute({})

    assert result.success is False
    assert result.error == "Server down"
    assert result.metadata["exception_type"] == "ConnectionError"


@pytest.mark.anyio
async def test_mcp_tool_structured_content():
    """Test MCPTool handles structured content correctly."""
    from unittest.mock import AsyncMock, MagicMock

    from picoagents.tools._mcp import MCPTool

    mock_manager = MagicMock(spec=MCPClientManager)
    mock_client = AsyncMock()

    # Mock with structured content
    mock_result = CallToolResult(
        content=[TextContent(type="text", text="Text fallback")],
        structuredContent={"result": "success", "data": {"value": 42}},
        isError=False,
    )
    mock_client.call_tool = AsyncMock(return_value=mock_result)
    mock_manager.get_client = AsyncMock(return_value=mock_client)

    tool = MCPTool(
        mcp_tool_name="structured_tool",
        mcp_tool_description="Tool with structured output",
        mcp_tool_schema={"type": "object", "properties": {}},
        client_manager=mock_manager,
        server_id="struct_server",
    )

    result = await tool.execute({})

    # Should prefer structured content over text
    assert result.success is True
    assert result.result == {"result": "success", "data": {"value": 42}}


# ============================================================================
# Integration Helper Tests
# ============================================================================


@pytest.mark.anyio
async def test_create_mcp_tools_without_autoconnect():
    """Test create_mcp_tools helper without autoconnect."""
    configs = [
        StdioServerConfig(server_id="test1", command="echo", args=["test"]),
        StdioServerConfig(server_id="test2", command="python", args=[]),
    ]

    manager, tools = await create_mcp_tools(configs, auto_connect=False)

    # Servers registered but not connected
    assert len(manager.list_servers()) == 2
    assert not manager.is_connected("test1")
    assert not manager.is_connected("test2")
    assert len(tools) == 0  # No tools discovered yet


# ============================================================================
# Lifecycle Tests
# ============================================================================


@pytest.mark.anyio
async def test_mcp_availability_flag():
    """Test that MCP_AVAILABLE flag is correct."""
    # If we got here, MCP is available (pytest.importorskip passed)
    assert MCP_AVAILABLE is True


def test_mcp_tool_repr():
    """Test MCPTool string representation."""
    from unittest.mock import MagicMock

    from picoagents.tools._mcp import MCPTool

    mock_manager = MagicMock()

    tool = MCPTool(
        mcp_tool_name="repr_tool",
        mcp_tool_description="Test repr",
        mcp_tool_schema={},
        client_manager=mock_manager,
        server_id="repr_server",
    )

    repr_str = repr(tool)
    assert "MCPTool" in repr_str
    assert "repr_server" in repr_str
    assert "repr_tool" in repr_str


def test_client_manager_repr():
    """Test MCPClientManager string representation."""
    manager = MCPClientManager()
    manager.add_server(StdioServerConfig(server_id="test", command="python", args=[]))

    repr_str = repr(manager)
    assert "MCPClientManager" in repr_str
    assert "servers=1" in repr_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
MCPClientManager - Manages connections to MCP servers (mcp SDK 2.0).

This module handles server lifecycle, discovery, and tool creation for
multiple MCP servers across different transports, using the high-level
`mcp.client.Client` from SDK 2.0 (protocol 2026-07-28). The SDK's Client
negotiates the connection itself (stateless `server/discover` on 2026-era
servers, legacy handshake otherwise).
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union

from mcp.client import Client

from .._base import BaseTool
from ._config import MCPServerConfig
from ._tap import FrameCallback, WireFrame, WireTap
from ._tool import MCPTool
from ._transports import build_transport

logger = logging.getLogger(__name__)

ElicitationHandler = Callable[[str, Any], Awaitable[Any]]
"""Async handler invoked as (server_id, ElicitRequestParams) -> ElicitResult.

Bridges MRTR (mid-call input) requests to the application - e.g. the WebUI
playground parks the call and asks the user. When no handler is set, servers
that elicit input receive a decline.
"""


class MCPClientManager:
    """
    Manages connections to MCP servers and provides tool discovery.

    This class handles:
    - Connecting to multiple MCP servers (stdio, streamable HTTP, legacy SSE)
    - Discovering available tools from each server
    - Creating MCPTool instances for discovered tools
    - Lifecycle management (startup/shutdown)
    - Optional MRTR (mid-call input) bridging via `elicitation_handler`
    - Optional wire-frame recording via `enable_wire_tap`

    Example:
        ```python
        manager = MCPClientManager()

        manager.add_server(StdioServerConfig(
            server_id="filesystem",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        ))

        await manager.connect("filesystem")
        tools = manager.get_tools("filesystem")

        agent = Agent(name="file_agent", tools=tools, ...)

        await manager.disconnect_all()
        ```
    """

    def __init__(
        self,
        elicitation_handler: Optional[ElicitationHandler] = None,
        enable_wire_tap: bool = False,
        on_frame: Optional[FrameCallback] = None,
        max_frames: int = 1000,
    ):
        """Initialize an empty client manager.

        Args:
            elicitation_handler: Optional async handler for MRTR input requests.
            enable_wire_tap: Record raw JSON-RPC frames per server.
            on_frame: Optional callback invoked as (server_id, frame) per frame.
            max_frames: Max frames retained per server (ring buffer).
        """
        self._servers: Dict[str, MCPServerConfig] = {}
        self._clients: Dict[str, Client] = {}
        self._runners: Dict[str, Tuple["asyncio.Task[None]", "asyncio.Event"]] = {}
        self._connect_locks: Dict[str, asyncio.Lock] = {}
        self._tools: Dict[str, List[MCPTool]] = {}
        self._taps: Dict[str, WireTap] = {}
        self._elicitation_handler = elicitation_handler
        self._enable_wire_tap = enable_wire_tap
        self._on_frame = on_frame
        self._max_frames = max_frames

    def add_server(self, config: MCPServerConfig) -> None:
        """
        Register an MCP server configuration.

        The server is not connected until connect() is called.

        Args:
            config: Server configuration with transport details

        Raises:
            ValueError: If a server with this ID is already registered
        """
        if config.server_id in self._servers:
            raise ValueError(f"Server '{config.server_id}' is already registered")

        self._servers[config.server_id] = config

    def remove_server(self, server_id: str) -> None:
        """Unregister a server. Must be disconnected first."""
        if server_id in self._clients:
            raise ValueError(f"Server '{server_id}' is connected; disconnect first")
        self._servers.pop(server_id, None)
        self._taps.pop(server_id, None)
        self._connect_locks.pop(server_id, None)

    def get_config(self, server_id: str) -> Optional[MCPServerConfig]:
        """Return the registered config for a server, if any."""
        return self._servers.get(server_id)

    async def connect(self, server_id: str) -> None:
        """
        Connect to an MCP server and discover its tools.

        This method:
        1. Builds the configured transport (optionally wire-tapped)
        2. Starts a runner task that owns the SDK client's lifecycle
        3. Discovers available tools and creates MCPTool instances

        Args:
            server_id: ID of the server to connect to

        Raises:
            ValueError: If server_id is not registered
            ConnectionError: If connection fails
        """
        if server_id not in self._servers:
            raise ValueError(f"Unknown server: {server_id}")

        lock = self._connect_locks.setdefault(server_id, asyncio.Lock())
        async with lock:
            await self._connect_locked(server_id)

    async def _connect_locked(self, server_id: str) -> None:
        if server_id in self._clients:
            return

        config = self._servers[server_id]

        transport: Any = build_transport(config)
        if self._enable_wire_tap:
            transport = WireTap(
                transport,
                server_id=server_id,
                max_frames=self._max_frames,
                on_frame=self._on_frame,
            )

        client = Client(
            transport,
            elicitation_callback=(
                self._make_elicitation_callback(server_id)
                if self._elicitation_handler
                else None
            ),
        )

        # The client's context (and its anyio cancel scopes) must be entered
        # and exited in the same task, but callers connect and disconnect from
        # different tasks (e.g. separate HTTP requests). A dedicated runner
        # task owns the client lifecycle; disconnect signals it to exit.
        loop = asyncio.get_running_loop()
        ready: "asyncio.Future[None]" = loop.create_future()
        stop = asyncio.Event()

        async def runner() -> None:
            try:
                async with client:
                    ready.set_result(None)
                    await stop.wait()
            except Exception as e:
                if not ready.done():
                    ready.set_exception(e)
                elif not stop.is_set():
                    # Post-connect transport death (server crashed, stream
                    # reset): surface it and drop the stale connection state.
                    logger.warning(
                        f"MCP connection to '{server_id}' died: {type(e).__name__}: {e}"
                    )
                    self._clients.pop(server_id, None)
                    self._runners.pop(server_id, None)
                    self._taps.pop(server_id, None)
                    self._tools.pop(server_id, None)

        task = loop.create_task(runner())
        try:
            await ready
        except Exception as e:
            stop.set()
            await asyncio.gather(task, return_exceptions=True)
            raise ConnectionError(
                f"Failed to connect to MCP server '{server_id}': {e}"
            ) from e

        self._clients[server_id] = client
        self._runners[server_id] = (task, stop)
        if isinstance(transport, WireTap):
            self._taps[server_id] = transport

        try:
            await self._discover_tools(server_id)
        except Exception as e:
            await self.disconnect(server_id)
            raise ConnectionError(
                f"Failed to discover tools on MCP server '{server_id}': {e}"
            ) from e

    def _make_elicitation_callback(self, server_id: str) -> Any:
        handler = self._elicitation_handler
        assert handler is not None

        async def callback(_context: Any, params: Any) -> Any:
            return await handler(server_id, params)

        return callback

    async def _discover_tools(self, server_id: str) -> None:
        """
        Discover available tools from an MCP server.

        Args:
            server_id: Server to discover tools from
        """
        client = self._clients[server_id]

        tools_response = await client.list_tools()

        mcp_tools = []
        for tool in tools_response.tools:
            mcp_tool = MCPTool(
                mcp_tool_name=tool.name,
                mcp_tool_description=tool.description or "",
                mcp_tool_schema=tool.input_schema,
                client_manager=self,
                server_id=server_id,
            )
            mcp_tools.append(mcp_tool)

        self._tools[server_id] = mcp_tools

    async def get_session(self, server_id: str) -> Client:
        """
        Get the MCP client for a server (named for pre-2.0 compatibility).

        Automatically connects if not already connected.

        Args:
            server_id: Server ID

        Returns:
            The connected `mcp.client.Client` for the server

        Raises:
            ValueError: If server_id is not registered
        """
        if server_id not in self._clients:
            await self.connect(server_id)
        return self._clients[server_id]

    # 2.0 name; get_session is kept so existing code and mocks keep working
    get_client = get_session

    def get_server_info(self, server_id: str) -> Dict[str, Any]:
        """
        Return negotiated connection details for a connected server.

        Includes protocol version, server info, and capabilities as
        discovered during connection (`server/discover` or legacy init).
        """
        if server_id not in self._clients:
            raise ValueError(f"Server '{server_id}' is not connected")
        client = self._clients[server_id]

        def dump(model: Any) -> Any:
            if model is None:
                return None
            try:
                return model.model_dump(by_alias=True, exclude_none=True, mode="json")
            except Exception:
                return str(model)

        return {
            "server_id": server_id,
            "protocol_version": getattr(client, "protocol_version", None),
            "server_info": dump(getattr(client, "server_info", None)),
            "capabilities": dump(getattr(client, "server_capabilities", None)),
            "instructions": getattr(client, "instructions", None),
        }

    def get_wire_frames(self, server_id: str) -> List[WireFrame]:
        """Return recorded wire frames for a server (empty if tap disabled)."""
        tap = self._taps.get(server_id)
        return list(tap.frames) if tap else []

    def get_tools(
        self, server_id: Optional[str] = None
    ) -> List[Union[BaseTool, Callable[..., Any]]]:
        """
        Get tools from MCP servers.

        Args:
            server_id: If provided, return tools from specific server.
                      If None, return tools from all connected servers.

        Returns:
            List of tools compatible with Agent's tools parameter.
            Returns Union type to match Agent signature exactly.
        """
        if server_id:
            tools: List[Union[BaseTool, Callable[..., Any]]] = list(
                self._tools.get(server_id, [])
            )
            return tools

        all_tools: List[Union[BaseTool, Callable[..., Any]]] = []
        for tools_list in self._tools.values():
            all_tools.extend(tools_list)
        return all_tools

    def list_servers(self) -> List[str]:
        """
        List all registered server IDs.

        Returns:
            List of server IDs
        """
        return list(self._servers.keys())

    def is_connected(self, server_id: str) -> bool:
        """
        Check if a server is currently connected.

        Args:
            server_id: Server ID to check

        Returns:
            True if connected, False otherwise
        """
        return server_id in self._clients

    async def disconnect(self, server_id: str) -> None:
        """
        Disconnect from an MCP server.

        Cleans up the client, wire tap, and cached tools.

        Args:
            server_id: Server to disconnect from
        """
        if server_id in self._clients:
            self._clients.pop(server_id)
            task, stop = self._runners.pop(server_id)
            stop.set()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=10)
            except Exception:
                logger.warning(f"MCP client for '{server_id}' did not close cleanly; cancelling")
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        self._taps.pop(server_id, None)

        if server_id in self._tools:
            del self._tools[server_id]

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        server_ids = list(self._clients.keys())
        for server_id in server_ids:
            await self.disconnect(server_id)

    @asynccontextmanager
    async def managed_connection(self, server_id: str):
        """
        Context manager for automatic connection/disconnection.

        Ensures proper cleanup even if errors occur.

        Args:
            server_id: Server to connect to

        Yields:
            The manager instance

        Example:
            ```python
            async with manager.managed_connection("github"):
                tools = manager.get_tools("github")
                # Use tools...
            # Automatically disconnected
            ```
        """
        await self.connect(server_id)
        try:
            yield self
        finally:
            await self.disconnect(server_id)

    def __repr__(self) -> str:
        connected = [sid for sid in self._servers if self.is_connected(sid)]
        return (
            f"MCPClientManager("
            f"servers={len(self._servers)}, "
            f"connected={len(connected)}, "
            f"tools={sum(len(t) for t in self._tools.values())})"
        )

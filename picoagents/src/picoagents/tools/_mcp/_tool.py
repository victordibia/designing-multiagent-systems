"""
MCPTool - Bridge between MCP tools and PicoAgents tools.

This module provides the MCPTool class that wraps MCP server tools
as PicoAgents BaseTool instances, enabling seamless integration.
"""

from typing import TYPE_CHECKING, Any, Dict

from .._base import ApprovalMode, BaseTool
from ...types import ToolResult

if TYPE_CHECKING:
    from mcp.types import CallToolResult

    from ._client import MCPClientManager


class MCPTool(BaseTool):
    """
    Wraps an MCP server tool as a PicoAgents tool.

    This bridge allows MCP tools to be used transparently
    in PicoAgents workflows alongside native tools.

    The tool automatically handles:
    - Parameter validation using MCP schemas
    - Execution via MCP client
    - Result conversion between MCP and PicoAgents formats
    - Error handling and reporting

    Example:
        ```python
        # MCPTool instances are typically created by MCPClientManager
        # during tool discovery, not instantiated directly
        manager = MCPClientManager()
        await manager.connect("filesystem")
        tools = manager.get_tools("filesystem")

        # Each tool is an MCPTool instance
        for tool in tools:
            result = await tool.execute({"path": "/tmp/file.txt"})
        ```
    """

    def __init__(
        self,
        mcp_tool_name: str,
        mcp_tool_description: str,
        mcp_tool_schema: Dict[str, Any],
        client_manager: "MCPClientManager",
        server_id: str,
        version: str = "1.0.0",
        approval_mode: ApprovalMode = ApprovalMode.NEVER,
    ):
        """
        Initialize MCP tool wrapper.

        Args:
            mcp_tool_name: Name of the tool on the MCP server
            mcp_tool_description: Tool description from MCP server
            mcp_tool_schema: JSON schema for tool parameters
            client_manager: Manager for MCP client connections
            server_id: ID of the MCP server providing this tool
            version: Tool version
            approval_mode: Whether approval is required before execution
        """
        # Namespace tool name by server to avoid conflicts
        tool_name = f"mcp_{server_id}_{mcp_tool_name}"

        super().__init__(
            name=tool_name,
            description=mcp_tool_description,
            version=version,
            approval_mode=approval_mode,
        )

        self.mcp_tool_name = mcp_tool_name
        self._parameters_schema = mcp_tool_schema
        self.client_manager = client_manager
        self.server_id = server_id

    @property
    def parameters(self) -> Dict[str, Any]:
        """Return the MCP tool's parameter schema."""
        return self._parameters_schema

    async def execute(self, parameters: Dict[str, Any]) -> ToolResult:
        """
        Execute the MCP tool via the client manager.

        Args:
            parameters: Tool parameters matching the schema

        Returns:
            ToolResult with execution outcome
        """
        try:
            # Get the MCP client (connects on first use)
            client = await self.client_manager.get_client(self.server_id)

            # Call the MCP tool
            result: "CallToolResult" = await client.call_tool(
                self.mcp_tool_name, arguments=parameters
            )

            # Convert MCP result to PicoAgents ToolResult
            output = self._extract_result_content(result)

            return ToolResult(
                success=not result.is_error,
                result=output,
                error=None if not result.is_error else "MCP tool execution failed",
                metadata={
                    "tool_name": self.name,
                    "mcp_server": self.server_id,
                    "mcp_tool": self.mcp_tool_name,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                result=None,
                error=str(e),
                metadata={
                    "tool_name": self.name,
                    "exception_type": type(e).__name__,
                },
            )

    def _extract_result_content(self, result: "CallToolResult") -> Any:
        """
        Extract content from MCP CallToolResult.

        Prefers structured content over text content when available.

        Args:
            result: MCP tool call result

        Returns:
            Extracted content (dict for structured, str for text)
        """
        # Prefer structured content if available (MCP 2025-06-18+)
        if getattr(result, "structured_content", None):
            return result.structured_content

        # Fall back to text content
        try:
            from mcp.types import TextContent

            text_parts = []
            for content in result.content:
                if isinstance(content, TextContent):
                    text_parts.append(content.text)

            return "\n".join(text_parts) if text_parts else None
        except ImportError:
            # If mcp types not available, return raw content
            return str(result.content) if result.content else None

    def __repr__(self) -> str:
        return (
            f"MCPTool(name='{self.name}', "
            f"server='{self.server_id}', "
            f"mcp_tool='{self.mcp_tool_name}')"
        )

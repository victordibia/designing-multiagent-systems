"""
Tool system for picoagents framework.

This module provides the foundation for tools that agents can use to
interact with the world beyond text generation.
"""

from ._base import ApprovalMode, BaseTool, FunctionTool
from ._core_tools import (
    CalculatorTool,
    DateTimeTool,
    JSONParserTool,
    RegexTool,
    TaskStatusTool,
    ThinkTool,
    create_core_tools,
)
from ._decorator import tool
from ._memory_tool import MemoryBackend, MemoryTool

try:
    from ._research_tools import (
        ArxivSearchTool,
        YouTubeCaptionTool,
        create_research_tools,
    )

    RESEARCH_TOOLS_AVAILABLE = True
except ImportError:
    RESEARCH_TOOLS_AVAILABLE = False
    ArxivSearchTool = None  # type: ignore
    YouTubeCaptionTool = None  # type: ignore

from ._coding_tools import create_coding_tools

# Context engineering tools
from ._context_tools import (
    MultiEditTool,
    SkillsTool,
    TaskTool,
    TodoListSessionsTool,
    TodoReadTool,
    TodoWriteTool,
    create_context_engineering_tools,
    create_multi_edit_tool,
    create_skills_tool,
    create_task_tool,
    create_todo_tools,
    get_current_session_id,
    list_todo_sessions,
    set_session_id,
    set_todo_path,
)

# MCP support (optional dependency)
try:
    from ._mcp import (
        HTTPServerConfig,
        InMemoryServerConfig,
        MCPClientManager,
        MCPServerConfig,
        MCPTool,
        StdioServerConfig,
        TransportType,
        WireTap,
        create_mcp_tools,
    )

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    MCPTool = None  # type: ignore
    MCPClientManager = None  # type: ignore
    MCPServerConfig = None  # type: ignore
    StdioServerConfig = None  # type: ignore
    HTTPServerConfig = None  # type: ignore
    InMemoryServerConfig = None  # type: ignore
    WireTap = None  # type: ignore
    TransportType = None  # type: ignore
    create_mcp_tools = None  # type: ignore

__all__ = [
    "ApprovalMode",
    "BaseTool",
    "FunctionTool",
    "tool",
    "create_core_tools",
    "create_research_tools",
    "create_coding_tools",
    "MemoryTool",
    "MemoryBackend",
    "ThinkTool",
    "TaskStatusTool",
    "CalculatorTool",
    "DateTimeTool",
    "JSONParserTool",
    "RegexTool",
    "ArxivSearchTool",
    "YouTubeCaptionTool",
    "RESEARCH_TOOLS_AVAILABLE",
    # Context engineering tools
    "TaskTool",
    "TodoWriteTool",
    "TodoReadTool",
    "TodoListSessionsTool",
    "SkillsTool",
    "MultiEditTool",
    "create_task_tool",
    "create_todo_tools",
    "create_skills_tool",
    "create_multi_edit_tool",
    "create_context_engineering_tools",
    "set_todo_path",
    "set_session_id",
    "get_current_session_id",
    "list_todo_sessions",
    # MCP integration
    "MCPTool",
    "MCPClientManager",
    "MCPServerConfig",
    "StdioServerConfig",
    "HTTPServerConfig",
    "InMemoryServerConfig",
    "WireTap",
    "TransportType",
    "create_mcp_tools",
    "MCP_AVAILABLE",
]

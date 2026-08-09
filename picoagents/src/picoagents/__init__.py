"""
Picoagents Framework

A lightweight, type-safe framework for building AI agents with LLMs.
Supports tool calling, memory, streaming, and multi-agent orchestration.
"""

# Auto-instrument with OpenTelemetry if enabled
import os

if os.getenv("PICOAGENTS_ENABLE_OTEL", "false").lower() in ("true", "1", "yes"):
    try:
        from ._otel import auto_instrument

        auto_instrument()
    except Exception:
        pass  # Gracefully continue if instrumentation fails

# Cancellation support
from ._cancellation_token import CancellationToken

# Component configuration system
from ._component_config import (
    Component,
    ComponentBase,
    ComponentFromConfig,
    ComponentLoader,
    ComponentModel,
    ComponentSchemaType,
    ComponentToConfig,
    ComponentType,
)

# Middleware system
from ._middleware import (
    BaseMiddleware,
    GuardrailMiddleware,
    LoggingMiddleware,
    MetricsMiddleware,
    MiddlewareChain,
    MiddlewareContext,
    PIIRedactionMiddleware,
    RateLimitMiddleware,
)

# Instruction presets
from ._instructions import get_instructions

# Deterministic loop hooks
from ._hooks import (
    BaseEndHook,
    BaseStartHook,
    CompletionCheckHook,
    CompositeTermination,
    LLMCompletionCheckHook,
    LoopContext,
    MaxRestartsTermination,
    PlanningHook,
    TerminationCondition,
)

# Agent implementations
from .agents import (
    Agent,
    AgentConfigurationError,
    AgentError,
    AgentExecutionError,
    AgentToolError,
    BaseAgent,
)

# Evaluation system
from .eval import (
    AgentEvalTarget,
    EvalJudge,
    EvalRunner,
    LLMEvalJudge,
    ModelEvalTarget,
    OrchestratorEvalTarget,
    Target,
)

# LLM clients
from .llm import (
    AuthenticationError,
    BaseChatCompletionClient,
    BaseChatCompletionError,
    InvalidRequestError,
    OpenAIChatCompletionClient,
    RateLimitError,
)

# Memory system
from .memory import BaseMemory, FileMemory, ListMemory, MemoryContent, MemoryQueryResult

# Context system
from .context import (
    AgentContext,
    ToolApprovalRequest,
    ToolApprovalResponse,
)

# Compaction strategies
from .compaction import (
    CompactionStrategy,
    HeadTailCompaction,
    NoCompaction,
    SlidingWindowCompaction,
)

# Core message types
from .messages import (
    AssistantMessage,
    Message,
    MultiModalMessage,
    SystemMessage,
    ToolCallRequest,
    ToolMessage,
    UserMessage,
)

# Orchestration patterns
from .orchestration import (
    BaseOrchestrator,
    BaseTermination,
    CancellationTermination,
    CompositeTermination,
    ExternalTermination,
    FunctionCallTermination,
    HandoffTermination,
    MaxMessageTermination,
    RoundRobinOrchestrator,
    TextMentionTermination,
    TimeoutTermination,
    TokenUsageTermination,
)

# Tool system
from .tools import ApprovalMode, BaseTool, FunctionTool, tool

# Core data types
from .types import (
    AgentEvent,
    AgentResponse,
    ChatCompletionChunk,
    ChatCompletionResult,
    OrchestrationEvent,
    OrchestrationResponse,
    StopMessage,
    ToolResult,
    Usage,
)

# Workflow system
from .workflow import (
    BaseStep,
    Context,
    EchoStep,
    FunctionStep,
    HttpStep,
    PicoAgentStep,
    StepMetadata,
    TransformStep,
    Workflow,
    WorkflowMetadata,
    WorkflowRunner,
)

def _detect_version() -> str:
    """Version from installed package metadata; pyproject.toml is the source
    of truth. Falls back for a source tree that was never installed."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("picoagents")
    except PackageNotFoundError:  # pragma: no cover - source checkout only
        return "0.0.0+unknown"


__version__: str = _detect_version()

__all__ = [
    # Context
    "AgentContext",
    "ToolApprovalRequest",
    "ToolApprovalResponse",
    # Compaction
    "CompactionStrategy",
    "HeadTailCompaction",
    "SlidingWindowCompaction",
    "NoCompaction",
    # Messages
    "Message",
    "SystemMessage",
    "UserMessage",
    "AssistantMessage",
    "ToolMessage",
    "MultiModalMessage",
    "ToolCallRequest",
    # Types
    "Usage",
    "ToolResult",
    "AgentResponse",
    "ChatCompletionResult",
    "ChatCompletionChunk",
    "AgentEvent",
    "StopMessage",
    "OrchestrationResponse",
    "OrchestrationEvent",
    # Cancellation
    "CancellationToken",
    # Component Configuration
    "ComponentModel",
    "ComponentFromConfig",
    "ComponentToConfig",
    "ComponentSchemaType",
    "ComponentLoader",
    "ComponentBase",
    "Component",
    "ComponentType",
    # Agents
    "BaseAgent",
    "Agent",
    "AgentError",
    "AgentExecutionError",
    "AgentConfigurationError",
    "AgentToolError",
    # Tools
    "BaseTool",
    "FunctionTool",
    "ApprovalMode",
    "tool",
    # Memory
    "BaseMemory",
    "MemoryContent",
    "MemoryQueryResult",
    "ListMemory",
    "FileMemory",
    # LLM
    "BaseChatCompletionClient",
    "BaseChatCompletionError",
    "RateLimitError",
    "AuthenticationError",
    "InvalidRequestError",
    "OpenAIChatCompletionClient",
    # Orchestration
    "BaseOrchestrator",
    "RoundRobinOrchestrator",
    "BaseTermination",
    "MaxMessageTermination",
    "TextMentionTermination",
    "TokenUsageTermination",
    "TimeoutTermination",
    "HandoffTermination",
    "ExternalTermination",
    "CancellationTermination",
    "FunctionCallTermination",
    "CompositeTermination",
    # Workflow system
    "Workflow",
    "WorkflowRunner",
    "BaseStep",
    "FunctionStep",
    "EchoStep",
    "HttpStep",
    "TransformStep",
    "PicoAgentStep",
    "WorkflowMetadata",
    "StepMetadata",
    "Context",
    # Evaluation
    "Target",
    "EvalJudge",
    "EvalRunner",
    "AgentEvalTarget",
    "ModelEvalTarget",
    "OrchestratorEvalTarget",
    "LLMEvalJudge",
    # Instructions
    "get_instructions",
    # Middleware
    "BaseMiddleware",
    "MiddlewareContext",
    "MiddlewareChain",
    "LoggingMiddleware",
    "RateLimitMiddleware",
    "PIIRedactionMiddleware",
    "GuardrailMiddleware",
    "MetricsMiddleware",
]

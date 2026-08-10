"""
Core data types and models for the picoagents framework using Pydantic.

This module defines all the structured types used throughout the framework
for type safety and data validation.
"""

from datetime import datetime
import warnings
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Union

from pydantic import BaseModel, Field

from .messages import Message

if TYPE_CHECKING:
    from .context import AgentContext, ToolApprovalRequest


class Usage(BaseModel):
    """Structured execution statistics and resource consumption."""

    duration_ms: int = Field(..., description="Total execution time in milliseconds")
    llm_calls: int = Field(default=0, description="Number of LLM API calls made")
    tokens_input: int = Field(default=0, description="Total input tokens consumed")
    tokens_output: int = Field(default=0, description="Total output tokens generated")
    tool_calls: int = Field(default=0, description="Number of tool executions")
    memory_operations: int = Field(
        default=0, description="Number of memory read/write operations"
    )
    cost_estimate: Optional[float] = Field(
        default=None, description="Estimated cost in USD"
    )

    def __add__(self, other: "Usage") -> "Usage":
        """Aggregate usage statistics from multiple sources."""
        return Usage(
            duration_ms=max(
                self.duration_ms, other.duration_ms
            ),  # Max for parallel execution
            llm_calls=self.llm_calls + other.llm_calls,
            tokens_input=self.tokens_input + other.tokens_input,
            tokens_output=self.tokens_output + other.tokens_output,
            tool_calls=self.tool_calls + other.tool_calls,
            memory_operations=self.memory_operations + other.memory_operations,
            cost_estimate=(self.cost_estimate or 0) + (other.cost_estimate or 0)
            or None,
        )

    class Config:
        frozen = True


class ToolResult(BaseModel):
    """Standardized tool execution result."""

    success: bool = Field(..., description="Whether tool execution succeeded")
    result: Any = Field(..., description="The actual result data")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Execution time, etc."
    )

    class Config:
        frozen = True


class AgentResponse(BaseModel):
    """Final result from agent.run() containing context with all state and messages."""

    context: Optional["AgentContext"] = Field(
        default=None, description="Complete context with messages and state"
    )
    source: str = Field(..., description="Source agent that generated this response")
    usage: Usage = Field(
        ..., description="Execution statistics and resource consumption"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now, description="When the message was created"
    )
    finish_reason: str = Field(
        ...,
        description="Why the agent stopped: stop, approval_needed, max_iterations, error, cancelled",
    )

    class Config:
        frozen = False  # Allow modification for context updates

    @property
    def messages(self) -> List[Message]:
        """Backward compatibility - access messages through context."""
        return self.context.messages if self.context else []

    @property
    def needs_approval(self) -> bool:
        """Check if response is waiting for approvals."""
        return self.context.waiting_for_approval if self.context else False

    @property
    def approval_requests(self) -> List["ToolApprovalRequest"]:
        """Get pending approval requests."""
        return self.context.pending_approval_requests if self.context else []

    @property
    def final_content(self) -> str:
        """Get the content of the last message, truncated for display."""
        if self.messages:
            content = self.messages[-1].content
            return content[:50] + "..." if len(content) > 50 else content
        return "No messages"

    def __str__(self) -> str:
        """Returns a user-friendly string representation with messages and usage."""
        # Concat all message str representations
        messages_str = "\n".join(str(msg) for msg in self.messages)

        # Format duration
        duration_s = self.usage.duration_ms / 1000

        # Format tokens
        tokens_in = (
            f"{self.usage.tokens_input/1000:.1f}k"
            if self.usage.tokens_input >= 1000
            else str(self.usage.tokens_input)
        )
        tokens_out = (
            f"{self.usage.tokens_output/1000:.1f}k"
            if self.usage.tokens_output >= 1000
            else str(self.usage.tokens_output)
        )

        # Format cost if available
        cost_str = (
            f", cost: ${self.usage.cost_estimate:.4f}"
            if self.usage.cost_estimate
            else ""
        )

        # Add approval status if needed
        if self.needs_approval:
            approval_str = f" | ⚠️ {len(self.approval_requests)} approvals needed"
        else:
            approval_str = f" | finish: {self.finish_reason}"

        usage_line = f"[usage] duration: {duration_s:.1f}s, tokens: in:{tokens_in}, out:{tokens_out}{cost_str}{approval_str}"

        return f"{messages_str}\n\n{usage_line}"

    def __repr__(self) -> str:
        """Returns an unambiguous, developer-friendly representation."""
        approval_info = f", approvals_needed={len(self.approval_requests)}" if self.needs_approval else ""
        return f"AgentResponse(source='{self.source}', messages={len(self.messages)}, finish_reason='{self.finish_reason}', usage={self.usage}{approval_info})"


class ChatCompletionResult(BaseModel):
    """Standardized LLM response from BaseChatCompletionClient."""

    message: "AssistantMessage" = Field(..., description="The LLM's response")
    usage: Usage = Field(..., description="Token consumption and timing metrics")
    model: str = Field(..., description="Actual model used for the request")
    finish_reason: str = Field(
        ..., description="Completion status: stop, tool_calls, length, error"
    )
    structured_output: Optional[BaseModel] = Field(
        default=None,
        description="Parsed structured output when output_format is specified",
    )

    class Config:
        frozen = True


class ChatCompletionChunk(BaseModel):
    """Streaming response chunk from BaseChatCompletionClient."""

    content: str = Field(..., description="Partial text content from stream")
    is_complete: bool = Field(..., description="Whether this is the final chunk")
    tool_call_chunk: Optional[Dict[str, Any]] = Field(
        default=None, description="Partial tool call data"
    )
    usage: Optional["Usage"] = Field(
        default=None,
        description="Token usage statistics (only present in final chunk when stream_options.include_usage=true)",
    )

    class Config:
        frozen = True


# Base event class for streaming
class BaseEvent(BaseModel):
    """Abstract base class for all agent events."""

    timestamp: datetime = Field(
        default_factory=datetime.now, description="When the event occurred"
    )
    source: str = Field(
        ..., description="Source of the event (agent name, system, orchestrator, etc.)"
    )
    event_type: str = Field(..., description="Type of event")

    class Config:
        frozen = True

    def __str__(self) -> str:
        """Returns a user-friendly string representation."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"[{self.source}] {time_str} | {self.event_type}"

    def __repr__(self) -> str:
        """Returns an unambiguous, developer-friendly representation."""
        class_name = self.__class__.__name__
        return f"{class_name}(event_type='{self.event_type}', source='{self.source}', timestamp='{self.timestamp}')"


# Execution Events
class TaskStartEvent(BaseEvent):
    """Event emitted when task processing begins."""

    event_type: str = Field(default="task_start", description="Event type identifier")
    task: str = Field(..., description="The task being started")


class TaskCompleteEvent(BaseEvent):
    """Event emitted when task processing ends."""

    event_type: str = Field(
        default="task_complete", description="Event type identifier"
    )
    result: str = Field(..., description="The final task result")


class ModelCallEvent(BaseEvent):
    """Event emitted when LLM API call is initiated."""

    event_type: str = Field(default="model_call", description="Event type identifier")
    input_messages: Sequence[Message] = Field(
        ..., description="Messages sent to the model"
    )
    model: str = Field(..., description="Model being called")


class ModelResponseEvent(BaseEvent):
    """Event emitted when LLM response is received."""

    event_type: str = Field(
        default="model_response", description="Event type identifier"
    )
    response: str = Field(..., description="The model's response")
    has_tool_calls: bool = Field(
        default=False, description="Whether response contains tool calls"
    )


class ModelStreamChunkEvent(BaseEvent):
    """Event emitted for each streaming chunk from LLM."""

    event_type: str = Field(
        default="model_stream_chunk", description="Event type identifier"
    )
    chunk: str = Field(..., description="Incremental text chunk")
    is_final: bool = Field(default=False, description="Whether this is the final chunk")


# Tool Events
class ToolCallEvent(BaseEvent):
    """Event emitted when tool execution begins."""

    event_type: str = Field(default="tool_call", description="Event type identifier")
    tool_name: str = Field(..., description="Name of the tool being called")
    parameters: Dict[str, Any] = Field(..., description="Parameters passed to the tool")
    call_id: str = Field(..., description="Unique identifier for this tool call")

    def __str__(self) -> str:
        """Returns a user-friendly string representation with tool details."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        params_str = ", ".join([f"{k}={v}" for k, v in self.parameters.items()])
        return f"[{self.source}] {time_str} | tool_call: {self.tool_name}({params_str})"


class ToolCallResponseEvent(BaseEvent):
    """Event emitted when tool execution completes."""

    event_type: str = Field(
        default="tool_call_response", description="Event type identifier"
    )
    call_id: str = Field(..., description="Unique identifier for this tool call")
    result: Optional[ToolResult] = Field(
        default=None, description="Tool execution result"
    )

    def __str__(self) -> str:
        """Returns a user-friendly string representation with result info."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        if self.result:
            status = "✓" if self.result.success else "✗"
            result_preview = (
                str(self.result.result)[:50] + "..."
                if len(str(self.result.result)) > 50
                else str(self.result.result)
            )
            return (
                f"[{self.source}] {time_str} | tool_response: {status} {result_preview}"
            )
        else:
            return f"[{self.source}] {time_str} | tool_response: (no result)"


class ToolApprovalEvent(BaseEvent):
    """Event emitted when tool execution requires approval."""

    event_type: str = Field(
        default="tool_approval", description="Event type identifier"
    )
    approval_request: "ToolApprovalRequest" = Field(
        ..., description="The approval request details"
    )

    def __str__(self) -> str:
        """Returns a user-friendly string representation."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"[{self.source}] {time_str} | ⚠️ approval needed: {self.approval_request.tool_name}"


class ToolValidationEvent(BaseEvent):
    """Event emitted after parameter validation."""

    event_type: str = Field(
        default="tool_validation", description="Event type identifier"
    )
    tool_name: str = Field(..., description="Name of the tool being validated")
    is_valid: bool = Field(..., description="Whether parameters are valid")
    errors: Optional[List[str]] = Field(default=None, description="Validation error messages")


# Memory Events
class MemoryUpdateEvent(BaseEvent):
    """Event emitted when memory state changes."""

    event_type: str = Field(
        default="memory_update", description="Event type identifier"
    )
    operation: str = Field(
        ..., description="Type of memory operation: add, update, delete"
    )
    content_summary: str = Field(..., description="Summary of what was stored/updated")


class MemoryRetrievalEvent(BaseEvent):
    """Event emitted when memory content is accessed."""

    event_type: str = Field(
        default="memory_retrieval", description="Event type identifier"
    )
    query: str = Field(..., description="Query used to retrieve memories")
    results_count: int = Field(..., description="Number of memories retrieved")


# Error Events
class ErrorEvent(BaseEvent):
    """Event emitted for recoverable errors."""

    event_type: str = Field(default="error", description="Event type identifier")
    error_message: str = Field(..., description="Description of the error")
    error_type: str = Field(..., description="Type/category of error")
    is_recoverable: bool = Field(
        default=True, description="Whether error can be recovered from"
    )


class FatalErrorEvent(BaseEvent):
    """Event emitted for unrecoverable errors that terminate execution."""

    event_type: str = Field(default="fatal_error", description="Event type identifier")
    error_message: str = Field(..., description="Description of the fatal error")
    error_type: str = Field(..., description="Type/category of error")
    is_recoverable: bool = Field(
        default=False, description="Always false for fatal errors"
    )


# Union type for all events
AgentEvent = Union[
    TaskStartEvent,
    TaskCompleteEvent,
    ModelCallEvent,
    ModelResponseEvent,
    ModelStreamChunkEvent,
    ToolCallEvent,
    ToolCallResponseEvent,
    ToolApprovalEvent,
    ToolValidationEvent,
    MemoryUpdateEvent,
    MemoryRetrievalEvent,
    ErrorEvent,
    FatalErrorEvent,
]


# Orchestration Types
class StopMessage(BaseModel):
    """Information about why orchestration stopped."""

    content: str = Field(..., description="Human-readable reason for stopping")
    source: str = Field(
        ..., description="What caused the stop (termination condition name)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional stop details"
    )

    class Config:
        frozen = True


class OrchestrationResponse(BaseModel):
    """Final result from orchestrator execution."""

    messages: Sequence[Message] = Field(
        ..., description="Complete conversation/execution history"
    )
    final_result: str = Field(..., description="Summary result or final output")
    usage: Usage = Field(
        ..., description="Aggregate resource consumption across all agents"
    )
    stop_message: StopMessage = Field(..., description="Termination details")
    pattern_metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Pattern-specific execution data"
    )

    @property
    def truncated_result(self) -> str:
        """Get the final result, truncated for display."""
        if len(self.final_result) > 80:
            return self.final_result[:80] + "..."
        return self.final_result

    def __str__(self) -> str:
        """Returns a user-friendly string representation with key metrics."""
        # Format duration
        duration_s = self.usage.duration_ms / 1000

        # Format tokens
        tokens_in = (
            f"{self.usage.tokens_input/1000:.1f}k"
            if self.usage.tokens_input >= 1000
            else str(self.usage.tokens_input)
        )
        tokens_out = (
            f"{self.usage.tokens_output/1000:.1f}k"
            if self.usage.tokens_output >= 1000
            else str(self.usage.tokens_output)
        )

        # Format cost if available
        cost_str = (
            f", cost: ${self.usage.cost_estimate:.4f}"
            if self.usage.cost_estimate
            else ""
        )

        # Get pattern name from metadata
        pattern = self.pattern_metadata.get("pattern", "Unknown")

        return f"🏁 {pattern}: {self.truncated_result} | duration: {duration_s:.1f}s, tokens: in:{tokens_in}, out:{tokens_out}, calls: {self.usage.llm_calls} {cost_str}. Stop reason: {self.stop_message.content}"

    def __repr__(self) -> str:
        """Returns an unambiguous, developer-friendly representation."""
        pattern = self.pattern_metadata.get("pattern", "Unknown")
        iterations = self.pattern_metadata.get("iterations_completed", 0)
        return f"OrchestrationResponse(pattern='{pattern}', messages={len(self.messages)}, iterations={iterations}, usage={self.usage}, stop='{self.stop_message.source}')"

    class Config:
        frozen = True


# Orchestration Events for Streaming
class OrchestrationStartEvent(BaseEvent):
    """Event emitted when orchestration begins."""

    event_type: str = Field(
        default="orchestration_start", description="Event type identifier"
    )
    task: str = Field(..., description="The task being orchestrated")
    pattern: str = Field(..., description="Orchestration pattern being used")


class OrchestrationCompleteEvent(BaseEvent):
    """Event emitted when orchestration ends."""

    event_type: str = Field(
        default="orchestration_complete", description="Event type identifier"
    )
    result: str = Field(..., description="Final orchestration result")
    stop_reason: str = Field(..., description="Why orchestration stopped")


class AgentSelectionEvent(BaseEvent):
    """Event emitted when an agent is selected for execution."""

    event_type: str = Field(
        default="agent_selection", description="Event type identifier"
    )
    selected_agent: str = Field(..., description="Name of selected agent")
    selection_reason: Optional[str] = Field(
        default=None, description="Why this agent was selected"
    )


class AgentExecutionStartEvent(BaseEvent):
    """Event emitted when agent execution begins."""

    event_type: str = Field(
        default="agent_execution_start", description="Event type identifier"
    )
    executing_agent: str = Field(..., description="Name of executing agent")
    context_size: int = Field(..., description="Number of messages in context")


class AgentExecutionCompleteEvent(BaseEvent):
    """Event emitted when agent execution completes."""

    event_type: str = Field(
        default="agent_execution_complete", description="Event type identifier"
    )
    executing_agent: str = Field(..., description="Name of executed agent")
    success: bool = Field(..., description="Whether execution succeeded")
    message_count: int = Field(..., description="Number of messages produced")


# Union type for orchestration events
OrchestrationEvent = Union[
    OrchestrationStartEvent,
    OrchestrationCompleteEvent,
    AgentSelectionEvent,
    AgentExecutionStartEvent,
    AgentExecutionCompleteEvent,
]


# Configuration types moved to respective modules for better organization


# Evaluation Types


class Task(BaseModel):
    """A task to run and evaluate."""

    name: str = Field(..., description="Human-readable task name")
    input: str = Field(..., description="Input/prompt for the task")
    expected_output: Optional[str] = Field(
        default=None, description="Expected output for comparison"
    )
    id: Optional[str] = Field(default=None, description="Unique task identifier")
    category: str = Field(default="general", description="Task category for filtering")
    eval_criteria: List[str] = Field(
        default_factory=list, description="Criteria to evaluate on"
    )
    rubric: Dict[str, str] = Field(
        default_factory=dict,
        description="Per-criterion scoring guidance, e.g. {'completeness': '10: All files. 5: Most. 0: None.'}",
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional task metadata"
    )

    class Config:
        frozen = True


class RunTrajectory(BaseModel):
    """What happened when a task was run against a target."""

    task: Task = Field(..., description="The task that was run")
    messages: Sequence[Message] = Field(..., description="Complete message sequence")
    success: bool = Field(..., description="Whether execution succeeded")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    usage: Optional[Usage] = Field(default=None, description="Resource consumption")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional execution metadata"
    )

    class Config:
        frozen = True


class EvalScore(BaseModel):
    """Evaluation score with dimensional breakdown."""

    overall: float = Field(..., description="Overall score (0-10 scale)")
    dimensions: Dict[str, float] = Field(
        default_factory=dict, description="Scores by evaluation dimension"
    )
    reasoning: Dict[str, str] = Field(
        default_factory=dict, description="Reasoning for each dimension"
    )
    trajectory: Optional["RunTrajectory"] = Field(
        default=None, description="The trajectory that was scored"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional scoring metadata"
    )

    def get_final_response(self) -> str:
        """Extract the final response from the trajectory."""
        if (
            not self.trajectory
            or not self.trajectory.success
            or not self.trajectory.messages
        ):
            return f"EXECUTION FAILED: {self.trajectory.error if self.trajectory else 'No trajectory'}"

        final_message = self.trajectory.messages[-1]
        return getattr(final_message, "content", str(final_message))

    def get_full_conversation(self) -> str:
        """Get the complete conversation as a formatted string."""
        if not self.trajectory or not self.trajectory.messages:
            return f"EXECUTION FAILED: {self.trajectory.error if self.trajectory else 'No trajectory'}"

        return "\n".join(str(msg) for msg in self.trajectory.messages)

    class Config:
        frozen = True


# Fix forward references
from .context import AgentContext, ToolApprovalRequest
from .messages import AssistantMessage

ChatCompletionResult.model_rebuild()
AgentResponse.model_rebuild()
AssistantMessage.model_rebuild()  # Rebuild to resolve Usage forward reference


# ---------------------------------------------------------------------------
# Deprecated aliases (0.4.0 -> 0.5.0 eval consolidation)
# ---------------------------------------------------------------------------

_RENAMED_IN_0_5_0 = {
    "EvalTask": ("Task", "Task"),
    "EvalTrajectory": ("RunTrajectory", "RunTrajectory"),
}

_REMOVED_IN_0_5_0 = {
    # EvalResult bundled task + trajectory + score; the runner now returns
    # picoagents.eval.TaskResult, which carries the same information.
    "EvalResult": "picoagents.eval.TaskResult",
}


def __getattr__(name: str) -> Any:
    """Map 0.4.0 eval type names to their 0.5.0 replacements (PEP 562)."""
    if name in _RENAMED_IN_0_5_0:
        new_name, attr = _RENAMED_IN_0_5_0[name]
        warnings.warn(
            f"picoagents.types.{name} was renamed to {new_name} in 0.5.0; "
            f"import {new_name} instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return globals()[attr]
    if name in _REMOVED_IN_0_5_0:
        raise AttributeError(
            f"picoagents.types.{name} was removed in 0.5.0. "
            f"Use {_REMOVED_IN_0_5_0[name]} instead."
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

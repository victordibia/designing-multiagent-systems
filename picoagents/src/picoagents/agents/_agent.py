"""
Concrete Agent implementation following the stub.md specification.

This module implements a full-featured agent that can reason using LLMs,
act through tools, maintain memory, and communicate with other agents.
"""

import asyncio
import os
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from .._cancellation_token import CancellationToken
from .._component_config import Component, ComponentModel
from ..context import AgentContext
from ..messages import (
    AssistantMessage,
    Message,
    ToolCallRequest,
    ToolMessage,
    UserMessage,
)
from ..types import (
    AgentEvent,
    AgentResponse,
    ChatCompletionChunk,
    ErrorEvent,
    ModelCallEvent,
    ModelResponseEvent,
    TaskCompleteEvent,
    TaskStartEvent,
    ToolCallEvent,
    ToolCallResponseEvent,
    Usage,
)
from ._base import AgentToolError, BaseAgent


class AgentConfig(BaseModel):
    """Configuration for Agent serialization."""

    name: str
    description: str
    instructions: str
    model_client: ComponentModel  # Serialized model client
    tools: List[ComponentModel] = Field(
        default_factory=list
    )  # Serialized tools (excluding FunctionTools)
    memory: Optional[ComponentModel] = None  # Serialized memory
    max_iterations: int = 10
    output_format_schema: Optional[
        Dict[str, Any]
    ] = None  # JSON schema for output format
    summarize_tool_result: bool = (
        True  # If False, stop after tool execution without LLM summarization
    )


class Agent(Component[AgentConfig], BaseAgent):
    """
    A concrete agent implementation following stub.md specification.

    This implementation demonstrates:
    - Integration with generative AI models for reasoning
    - Tool calling and execution for acting
    - Memory management for adaptation
    - Message history for communication
    - Streaming support with events
    """

    component_config_schema = AgentConfig
    component_type = "agent"
    component_provider_override = "picoagents.agents.Agent"

    def _should_create_span(self) -> bool:
        """Check if we should create OpenTelemetry spans."""
        return os.getenv("PICOAGENTS_ENABLE_OTEL", "false").lower() in (
            "true",
            "1",
            "yes",
        )

    async def run(
        self,
        task: Optional[Union[str, UserMessage, List[Message]]] = None,
        context: Optional[AgentContext] = None,
        cancellation_token: Optional[CancellationToken] = None,
        persist: bool = False,
    ) -> AgentResponse:
        """
        Execute the agent's main reasoning and action loop.

        Each call operates on an isolated context and does not mutate
        self.context. The conversation state is returned in
        response.context. For multi-turn conversations, pass the
        previous response's context to the next call::

            r1 = await agent.run("hello")
            r2 = await agent.run("follow up", context=r1.context)

        This design makes Agent safe for concurrent use — multiple
        run() calls on the same instance will not interfere.

        Args:
            task: Optional new task (can continue from context alone
                if not provided)
            context: Existing context to continue from. If not
                provided, self.context is deep-copied as starting
                point (typically empty).
            cancellation_token: Optional token for cancelling
                execution
            persist: If True, save the run to ~/.picoagents/ (DB
                index + JSON file with full response data)

        Returns:
            AgentResponse containing context with all state and
            messages
        """
        trace_id = None

        # Wrap execution in OpenTelemetry span if enabled
        if self._should_create_span():
            try:
                from opentelemetry import trace

                tracer = trace.get_tracer("picoagents")
                with tracer.start_as_current_span(f"agent {self.name}") as span:
                    response = await self._run_internal(
                        task, context, cancellation_token
                    )
                    if persist:
                        ctx = span.get_span_context()
                        trace_id = format(ctx.trace_id, "032x")
            except Exception:
                # If OTel fails, fall back to normal execution
                response = await self._run_internal(
                    task, context, cancellation_token
                )
        else:
            response = await self._run_internal(
                task, context, cancellation_token
            )

        if persist:
            try:
                from ..store import get_default_store

                store = get_default_store()
                await store.save_agent_run(
                    self, response, trace_id=trace_id
                )
            except Exception as e:
                import logging

                logging.getLogger(__name__).warning(
                    f"Failed to persist run: {e}"
                )

        return response

    async def _run_internal(
        self,
        task: Optional[Union[str, UserMessage, List[Message]]] = None,
        context: Optional[AgentContext] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> AgentResponse:
        """Internal implementation of run() without span wrapping."""
        # Use provided context or create new one
        working_context = context if context else self.context.model_copy(deep=True)

        # Add new task to context if provided
        if task:
            if isinstance(task, str):
                working_context.add_message(UserMessage(content=task, source="user"))
            elif isinstance(task, UserMessage):
                working_context.add_message(task)
            elif isinstance(task, list):
                for msg in task:
                    working_context.add_message(msg)

        final_response = None
        start_time = time.time()

        try:
            async for item in self.run_stream(None, working_context, cancellation_token, False, False):
                # Capture the final AgentResponse
                if isinstance(item, AgentResponse):
                    final_response = item

            # Return the final response from the stream, or create fallback
            if final_response:
                return final_response
            else:
                # Fallback if no AgentResponse was yielded
                duration_ms = int((time.time() - start_time) * 1000)
                return AgentResponse(
                    context=working_context,
                    source=self.name,
                    finish_reason="no_response",
                    usage=Usage(duration_ms=duration_ms),
                )

        except asyncio.CancelledError:
            # Re-raise cancellation for proper handling
            raise
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            usage_stats = Usage(duration_ms=duration_ms)

            # Return error response with context
            error_message = AssistantMessage(
                content=f"Error: {str(e)}", source=self.name
            )
            working_context.add_message(error_message)
            return AgentResponse(
                context=working_context,
                source=self.name,
                finish_reason="error",
                usage=usage_stats,
            )

    async def run_stream(
        self,
        task: Optional[Union[str, UserMessage, List[Message]]] = None,
        context: Optional[AgentContext] = None,
        cancellation_token: Optional[CancellationToken] = None,
        verbose: bool = False,
        stream_tokens: bool = False,
    ) -> AsyncGenerator[
        Union[Message, AgentEvent, AgentResponse, ChatCompletionChunk], None
    ]:
        """
        Execute the agent with streaming output.

        Yields both Messages (for UI/conversation), Events (for debugging/observability),
        and final AgentResponse (for usage statistics).

        Args:
            task: The task or query for the agent to address
            cancellation_token: Optional token for cancelling execution
            verbose: Enable detailed event logging
            stream_tokens: Enable token-level streaming from LLM. Note: Automatically
                          disabled if middleware is configured, as middleware requires
                          complete requests/responses. A warning will be issued if this occurs.

        Yields:
            Messages, events, ChatCompletionChunks (if stream_tokens=True), and final AgentResponse
        """
        start_time = time.time()
        messages_yielded = []
        llm_calls = 0
        tokens_input = 0
        tokens_output = 0

        # Note: Token-level streaming (stream_tokens=True) bypasses middleware
        # to enable real-time token streaming. Middleware is applied to complete
        # messages in the non-streaming path. Agent-level streaming (run_stream)
        # works with middleware via execute_stream().
        # TODO: Consider adding middleware support for token streaming in future
        effective_stream_tokens = stream_tokens

        # Use provided context or create one
        working_context = context if context else self.context.model_copy(deep=True)

        try:
            # Check for cancellation at the start
            if cancellation_token and cancellation_token.is_cancelled():
                raise asyncio.CancelledError()

            # 1. Add task to context if provided
            if task:
                task_messages = self._convert_task_to_messages(task)
                for msg in task_messages:
                    working_context.add_message(msg)

                # Yield the initial user message
                user_message = task_messages[0]
                yield user_message
                messages_yielded.append(user_message)

                # Emit task start event
                if verbose:
                    yield TaskStartEvent(source=self.name, task=user_message.content)

            # 1a. Check if resuming with pending tool calls that have approval responses
            # This handles the case where agent paused for approval and is now resuming
            if not task and working_context.messages:
                last_message = working_context.messages[-1]
                if isinstance(last_message, AssistantMessage) and last_message.tool_calls:
                    # Check if any tool calls have approval responses
                    has_approvals = any(
                        working_context.approval_responses.get(tc.call_id) is not None
                        for tc in last_message.tool_calls
                    )

                    if has_approvals:
                        # Process the pending tool calls with their approval responses
                        # Pass empty list since context messages are added inside _prepare_llm_messages
                        llm_messages_temp = await self._prepare_llm_messages(
                            [], context=working_context
                        )

                        # Process each tool call
                        for tool_call in last_message.tool_calls:
                            async for item in self._execute_tool_call(
                                tool_call, llm_messages_temp, cancellation_token,
                                context=working_context,
                            ):
                                yield item
                                if isinstance(
                                    item, (UserMessage, AssistantMessage, ToolMessage)
                                ):
                                    messages_yielded.append(item)

            # 2. Prepare messages for LLM including system instructions, memory, history
            # Pass empty list since context messages are added inside _prepare_llm_messages
            llm_messages = await self._prepare_llm_messages(
                [], context=working_context
            )

            # === DETERMINISTIC START HOOKS ===
            # Run before the first LLM call. These are Python code, not LLM-controlled.
            # Hooks can inject UserMessages (e.g., "create a plan first").
            loop_ctx = None
            if self.start_hooks or self.end_hooks:
                from .._hooks import LoopContext

                loop_ctx = LoopContext(
                    agent_context=working_context,
                    llm_messages=llm_messages,
                    agent_name=self.name,
                    model_client=self.model_client,
                )
                for hook in self.start_hooks:
                    injection = await hook.on_start(loop_ctx)
                    if injection:
                        hook_msg = UserMessage(
                            content=injection, source="hook"
                        )
                        working_context.add_message(hook_msg)
                        llm_messages.append(hook_msg)

            # 3. Make initial LLM call
            if verbose:
                yield ModelCallEvent(
                    source=self.name,
                    input_messages=llm_messages,
                    model=getattr(self.model_client, "model", "unknown"),
                )

            # Initialize assistant_message and completion reason
            assistant_message = AssistantMessage(
                content="Task completed", source=self.name
            )
            llm_finish_reason = "stop"  # Track the LLM's last finish reason

            iteration = 0
            while iteration < self.max_iterations:
                try:
                    # Check for cancellation at the start of each iteration
                    if cancellation_token and cancellation_token.is_cancelled():
                        raise asyncio.CancelledError()

                    # === CONTEXT COMPACTION HOOK ===
                    # Apply compaction strategy BEFORE each LLM call.
                    # This is critical: the compacted list REPLACES llm_messages,
                    # so subsequent iterations work with bounded context.
                    if self.compaction:
                        llm_messages = self.compaction.compact(llm_messages)

                    # Get tools for LLM if available
                    tools = self._get_tools_for_llm() if self.tools else None

                    if effective_stream_tokens:
                        # STREAMING PATH: Stream tokens and accumulate result
                        accumulated_content = ""
                        accumulated_tool_calls = {}  # Dict by call_id for final state
                        last_call_id = (
                            None  # Track last seen call_id for chunks without ID
                        )
                        structured_output = None
                        streaming_usage = None  # Track usage from final chunk

                        async for chunk in self.model_client.create_stream(
                            llm_messages, tools=tools, output_format=self.output_format
                        ):
                            # Check for cancellation during streaming
                            if cancellation_token and cancellation_token.is_cancelled():
                                raise asyncio.CancelledError()

                            if not chunk.is_complete:
                                # Yield chunk for real-time streaming
                                yield chunk

                                # Accumulate content
                                if chunk.content:
                                    accumulated_content += chunk.content

                                # Store tool call data (each chunk has complete state)
                                if chunk.tool_call_chunk:
                                    call_id = chunk.tool_call_chunk.get("id")

                                    # Update last_call_id when we see a new ID
                                    if call_id:
                                        last_call_id = call_id

                                    # Use last_call_id for chunks without explicit ID
                                    effective_call_id = call_id or last_call_id

                                    if effective_call_id:
                                        # Store the complete state from this chunk
                                        accumulated_tool_calls[effective_call_id] = {
                                            "id": effective_call_id,
                                            "function": chunk.tool_call_chunk.get(
                                                "function", {}
                                            ),
                                            "extra_content": chunk.tool_call_chunk.get(
                                                "extra_content"
                                            ),
                                        }
                            else:
                                # Stream complete - capture usage from final chunk
                                if chunk.usage:
                                    streaming_usage = chunk.usage
                                llm_finish_reason = (
                                    "stop"  # Streaming typically ends with "stop"
                                )
                                break

                        # Build tool calls from accumulated data
                        tool_calls = []
                        if accumulated_tool_calls:
                            import json

                            for call_id, tc_data in accumulated_tool_calls.items():
                                try:
                                    # Validate we have complete tool call data
                                    if (
                                        tc_data["function"]["name"]
                                        and tc_data["function"]["arguments"]
                                    ):
                                        tool_calls.append(
                                            ToolCallRequest(
                                                tool_name=tc_data["function"]["name"],
                                                parameters=json.loads(
                                                    tc_data["function"]["arguments"]
                                                ),
                                                call_id=tc_data["id"],
                                                extra_content=tc_data.get("extra_content"),
                                            )
                                        )
                                    else:
                                        print(
                                            f"Warning: Incomplete tool call data for {call_id}: {tc_data}"
                                        )
                                except (json.JSONDecodeError, KeyError) as e:
                                    # Skip malformed tool calls
                                    print(
                                        f"Warning: Skipping malformed tool call {call_id}: {e}"
                                    )
                                    continue

                        # Create completion result for consistency
                        from ..types import ChatCompletionResult

                        accumulated_message = AssistantMessage(
                            content=accumulated_content,
                            source="llm",
                            tool_calls=tool_calls if tool_calls else None,
                        )
                        completion_result = ChatCompletionResult(
                            message=accumulated_message,
                            usage=Usage(
                                duration_ms=streaming_usage.duration_ms if streaming_usage else 0,
                                llm_calls=1,
                                tokens_input=streaming_usage.tokens_input if streaming_usage else 0,
                                tokens_output=streaming_usage.tokens_output if streaming_usage else 0,
                                tool_calls=len(tool_calls),
                            ),
                            model=getattr(self.model_client, "model", "unknown"),
                            finish_reason=llm_finish_reason,
                            structured_output=structured_output,
                        )

                        original_message = completion_result.message

                    else:
                        # NON-STREAMING PATH: Use middleware as before
                        from ..types import ChatCompletionResult

                        async def _model_call(messages):
                            task = asyncio.create_task(
                                self.model_client.create(
                                    messages,
                                    tools=tools,
                                    output_format=self.output_format,
                                )
                            )
                            if cancellation_token:
                                cancellation_token.link_future(task)
                            return await task

                        # Prepare metadata with model information for middleware
                        model_metadata = {}
                        if hasattr(self.model_client, "model"):
                            model_metadata["model"] = self.model_client.model

                        # Execute through middleware chain (streaming)
                        completion_result = None
                        async for item in self.middleware_chain.execute_stream(
                            operation="model_call",
                            agent_name=self.name,
                            agent_context=working_context,
                            data=llm_messages,
                            func=_model_call,
                            metadata=model_metadata,
                        ):
                            # Check if this is an event (not the final result)
                            # Result will be ChatCompletionResult
                            if isinstance(item, ChatCompletionResult):
                                completion_result = item
                            else:
                                # This is an event from middleware
                                yield item

                                # Check for approval pause
                                if isinstance(item, ToolApprovalEvent):
                                    return  # PAUSE - middleware requested approval

                        if completion_result is None:
                            # Middleware paused without yielding result
                            return

                        original_message = completion_result.message
                        llm_finish_reason = (
                            completion_result.finish_reason
                        )  # Capture LLM finish reason

                    # Always create new AssistantMessage with source (same for both paths)
                    assistant_message = AssistantMessage(
                        content=original_message.content,
                        source=self.name,
                        tool_calls=original_message.tool_calls,
                        structured_content=completion_result.structured_output
                        if completion_result.structured_output
                        else None,
                        usage=completion_result.usage if hasattr(completion_result, "usage") else None,
                    )

                    llm_calls += 1

                    # Track token usage if available
                    if hasattr(completion_result, "usage"):
                        tokens_input += getattr(
                            completion_result.usage, "tokens_input", 0
                        )
                        tokens_output += getattr(
                            completion_result.usage, "tokens_output", 0
                        )

                    # Only yield assistant messages that don't have tool calls
                    # Messages with tool calls are internal orchestration, we'll yield the final response after tools execute
                    if not assistant_message.tool_calls:
                        yield assistant_message
                        messages_yielded.append(assistant_message)

                    # Emit model response event
                    if verbose:
                        yield ModelResponseEvent(
                            source=self.name,
                            response=assistant_message.content,
                            has_tool_calls=assistant_message.tool_calls is not None,
                        )

                    # Add assistant message to context and working messages
                    working_context.add_message(assistant_message)
                    llm_messages.append(assistant_message)

                    # 4. Handle tool calls if present
                    if assistant_message.tool_calls:
                        # Track if any tool needs approval
                        approval_needed = False

                        # Check if we can execute tools in parallel (multiple independent calls)
                        if len(assistant_message.tool_calls) > 1:
                            # Execute tools in parallel using asyncio.gather
                            async for item in self._execute_tool_calls_parallel(
                                assistant_message.tool_calls,
                                llm_messages,
                                cancellation_token,
                                context=working_context,
                            ):
                                yield item
                                # Track messages for final response
                                if isinstance(
                                    item, (UserMessage, AssistantMessage, ToolMessage)
                                ):
                                    messages_yielded.append(item)
                                # Check if this is an approval event
                                from ..types import ToolApprovalEvent
                                if isinstance(item, ToolApprovalEvent):
                                    approval_needed = True
                        else:
                            # Single tool call - execute sequentially
                            for tool_call in assistant_message.tool_calls:
                                async for item in self._execute_tool_call(
                                    tool_call, llm_messages, cancellation_token,
                                    context=working_context,
                                ):
                                    yield item
                                    # Track messages for final response
                                    if isinstance(
                                        item,
                                        (UserMessage, AssistantMessage, ToolMessage),
                                    ):
                                        messages_yielded.append(item)
                                    # Check if this is an approval event
                                    from ..types import ToolApprovalEvent
                                    if isinstance(item, ToolApprovalEvent):
                                        approval_needed = True

                        # If approval is needed, stop and return
                        if approval_needed:
                            # Set finish reason and break
                            llm_finish_reason = "approval_needed"
                            break

                        # Check if we should skip LLM summarization
                        if not self.summarize_tool_result:
                            # Stop after tool execution without LLM call
                            break

                        # Continue loop for next LLM call after tool execution
                        iteration += 1
                        continue

                    # No tool calls - check end hooks before stopping.
                    # End hooks are deterministic Python code that can
                    # inject a UserMessage to resume the loop.
                    should_continue = False
                    if loop_ctx is not None:
                        loop_ctx.iteration = iteration
                        loop_ctx.llm_messages = llm_messages

                        for hook in self.end_hooks:
                            injection = await hook.on_end(loop_ctx)
                            if injection:
                                resume_msg = UserMessage(
                                    content=injection,
                                    source="hook",
                                )
                                working_context.add_message(resume_msg)
                                llm_messages.append(resume_msg)
                                loop_ctx.restart_count += 1
                                should_continue = True
                                break  # First hook to inject wins

                    if should_continue:
                        iteration += 1
                        continue
                    break

                except asyncio.CancelledError:
                    # Re-raise cancellation for proper handling
                    raise
                except Exception as e:
                    error_event = ErrorEvent(
                        source=self.name,
                        error_message=str(e),
                        error_type=type(e).__name__,
                    )
                    yield error_event

                    # Yield error message
                    error_message = AssistantMessage(
                        content=f"I encountered an error: {str(e)}", source=self.name
                    )
                    yield error_message
                    messages_yielded.append(error_message)
                    break

            # Emit task completion event
            if verbose:
                yield TaskCompleteEvent(
                    source=self.name, result=assistant_message.content
                )

            # Determine finish reason based on LLM completion and agent state
            if iteration >= self.max_iterations:
                finish_reason = "max_iterations"
            else:
                # Use the LLM's finish reason
                finish_reason = llm_finish_reason

            # Yield final AgentResponse with complete conversation and usage stats
            duration_ms = int((time.time() - start_time) * 1000)
            tool_calls = sum(
                1 for msg in messages_yielded if isinstance(msg, ToolMessage)
            )

            # Create context for response - use working_context which has all updates
            response_context = working_context

            final_response = AgentResponse(
                context=response_context,
                source=self.name,
                finish_reason=finish_reason,
                usage=Usage(
                    duration_ms=duration_ms,
                    llm_calls=llm_calls,
                    tokens_input=tokens_input,
                    tokens_output=tokens_output,
                    tool_calls=tool_calls,
                ),
            )
            yield final_response

        except asyncio.CancelledError:
            # Handle cancellation gracefully
            yield ErrorEvent(
                source=self.name,
                error_message="Agent execution was cancelled",
                error_type="CancelledError",
                is_recoverable=False,
            )

            # Yield final cancellation message
            cancel_message = AssistantMessage(
                content="Agent execution was cancelled", source=self.name
            )
            yield cancel_message
            messages_yielded.append(cancel_message)

            # Yield final AgentResponse for cancelled execution
            duration_ms = int((time.time() - start_time) * 1000)
            tool_calls = sum(
                1 for msg in messages_yielded if isinstance(msg, ToolMessage)
            )

            # Create context for cancel response - use working_context which has all updates
            cancel_context = working_context

            cancel_response = AgentResponse(
                context=cancel_context,
                source=self.name,
                finish_reason="cancelled",
                usage=Usage(
                    duration_ms=duration_ms,
                    llm_calls=llm_calls,
                    tokens_input=tokens_input,
                    tokens_output=tokens_output,
                    tool_calls=tool_calls,
                ),
            )
            yield cancel_response

            # Re-raise the cancellation
            raise

        except Exception as e:
            # Emit fatal error event
            yield ErrorEvent(
                source=self.name,
                error_message=str(e),
                error_type=type(e).__name__,
                is_recoverable=False,
            )

            # Yield final error message
            error_message = AssistantMessage(
                content=f"Fatal error: {str(e)}", source=self.name
            )
            yield error_message
            messages_yielded.append(error_message)

            # Yield final AgentResponse even for errors
            duration_ms = int((time.time() - start_time) * 1000)
            tool_calls = sum(
                1 for msg in messages_yielded if isinstance(msg, ToolMessage)
            )

            # Create context for error response - use working_context which has all updates
            error_context = working_context

            error_response = AgentResponse(
                context=error_context,
                source=self.name,
                finish_reason="error",
                usage=Usage(
                    duration_ms=duration_ms,
                    llm_calls=llm_calls,
                    tokens_input=tokens_input,
                    tokens_output=tokens_output,
                    tool_calls=tool_calls,
                ),
            )
            yield error_response

    async def _execute_tool_calls_parallel(
        self,
        tool_calls: List[ToolCallRequest],
        llm_messages: List[Message],
        cancellation_token: Optional[CancellationToken] = None,
        context: Optional[AgentContext] = None,
    ) -> AsyncGenerator[Union[Message, AgentEvent], None]:
        """
        Execute multiple tool calls in parallel for improved performance.

        This method uses asyncio.gather to execute independent tool calls concurrently,
        following Anthropic's best practice of parallel tool execution for Claude 4 models.

        Args:
            tool_calls: List of tool calls to execute in parallel
            llm_messages: Current message history for context
            cancellation_token: Optional token for cancelling execution
            context: Explicit context to use (for concurrent safety)

        Yields:
            Events and ToolMessages from all tool executions
        """
        # Check for cancellation before starting
        if cancellation_token and cancellation_token.is_cancelled():
            raise asyncio.CancelledError()

        # Collect all items from parallel execution
        async def collect_tool_results(tool_call):
            """Helper to collect all items from a single tool execution."""
            items = []
            async for item in self._execute_tool_call(
                tool_call, llm_messages, cancellation_token,
                context=context,
            ):
                items.append(item)
            return items

        try:
            # Execute all tool calls in parallel
            results = await asyncio.gather(
                *[collect_tool_results(tc) for tc in tool_calls], return_exceptions=True
            )

            # Yield all items in order (tool events, then messages)
            # First yield all tool call events
            for items in results:
                if isinstance(items, Exception):
                    # Handle exception from one of the tool calls
                    error_event = ErrorEvent(
                        source=self.name,
                        error_message=str(items),
                        error_type=type(items).__name__,
                    )
                    yield error_event
                    continue

                # Yield items from this tool execution
                for item in items:
                    yield item

        except asyncio.CancelledError:
            # Handle cancellation for all parallel calls
            raise
        except Exception as e:
            # Handle any unexpected errors
            error_event = ErrorEvent(
                source=self.name,
                error_message=f"Parallel tool execution failed: {str(e)}",
                error_type=type(e).__name__,
            )
            yield error_event
            raise

    async def _execute_tool_call(
        self,
        tool_call: ToolCallRequest,
        llm_messages: List[Message],
        cancellation_token: Optional[CancellationToken] = None,
        context: Optional[AgentContext] = None,
    ) -> AsyncGenerator[Union[Message, AgentEvent], None]:
        """
        Execute a single tool call and yield events and result message.

        Args:
            tool_call: The tool call to execute
            llm_messages: Current message history for context
            cancellation_token: Optional token for cancelling execution
            context: Explicit context to use (for concurrent safety).
                     Falls back to self.context if not provided.

        Yields:
            Events and the final ToolMessage
        """
        working_context = context if context is not None else self.context
        # Check for cancellation before tool execution
        if cancellation_token and cancellation_token.is_cancelled():
            raise asyncio.CancelledError()

        # Emit tool call event
        tool_event = ToolCallEvent(
            source=self.name,
            tool_name=tool_call.tool_name,
            parameters=tool_call.parameters,
            call_id=tool_call.call_id,
        )
        yield tool_event

        try:
            # Find the tool
            tool = self._find_tool(tool_call.tool_name)
            if tool is None:
                # Tool not found
                result = ToolMessage(
                    content=f"Tool '{tool_call.tool_name}' not found",
                    source=self.name,
                    tool_call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    success=False,
                    error=f"Tool '{tool_call.tool_name}' not found",
                )
                # Emit tool response event
                tool_response_event = ToolCallResponseEvent(
                    source=self.name, call_id=tool_call.call_id, result=None
                )
                yield tool_response_event

                # Add tool result to context and working messages
                working_context.add_message(result)
                llm_messages.append(result)

                # Yield the final result message
                yield result
                return

            # Check if tool requires approval
            from ..tools._base import ApprovalMode

            if tool.approval_mode == ApprovalMode.ALWAYS:
                # Check if we already have approval for this specific tool call
                existing_approval = working_context.get_approval_response(tool_call.call_id)

                if existing_approval is None:
                    # No approval yet - create approval request and pause
                    approval_request = working_context.add_approval_request(
                        tool_call=tool_call,
                        tool_name=tool_call.tool_name
                    )

                    # Emit approval needed event
                    from ..types import ToolApprovalEvent
                    approval_event = ToolApprovalEvent(
                        source=self.name,
                        approval_request=approval_request
                    )
                    yield approval_event

                    # Do NOT execute the tool - just return without yielding a result
                    # The agent will stop and wait for approval
                    return

                # We have approval - check if it was granted
                if not existing_approval.approved:
                    # User denied approval
                    result = ToolMessage(
                        content=f"Tool execution denied: {existing_approval.reason or 'User declined approval'}",
                        source=self.name,
                        tool_call_id=tool_call.call_id,
                        tool_name=tool_call.tool_name,
                        success=False,
                        error="Approval denied"
                    )

                    # Emit denial event
                    tool_response_event = ToolCallResponseEvent(
                        source=self.name, call_id=tool_call.call_id, result=None
                    )
                    yield tool_response_event

                    # Add result to context and messages
                    working_context.add_message(result)
                    llm_messages.append(result)

                    # Yield the denial message
                    yield result
                    return

                # Approval granted - proceed with execution below

            # Check if tool supports streaming
            if tool.supports_streaming():
                # Execute streaming tool
                tool_result = None
                async for item in tool.execute_stream(
                    tool_call.parameters, cancellation_token
                ):
                    from ..messages import Message
                    from ..types import ToolResult

                    if isinstance(item, ToolResult):
                        # This is the final result - convert to ToolMessage
                        tool_result = item
                        result = ToolMessage(
                            content=str(item.result)
                            if item.success
                            else f"Error: {item.error}",
                            source=self.name,
                            tool_call_id=tool_call.call_id,
                            tool_name=tool_call.tool_name,
                            success=item.success,
                            error=item.error,
                            metadata=item.metadata,
                        )
                        # Add to context and messages
                        working_context.add_message(result)
                        llm_messages.append(result)
                        yield result
                    elif isinstance(item, Message):
                        # Forward streaming messages from tool directly
                        yield item
                    else:
                        # Forward other events
                        yield item

                # Emit tool response event
                tool_response_event = ToolCallResponseEvent(
                    source=self.name, call_id=tool_call.call_id, result=tool_result
                )
                yield tool_response_event
            else:
                # Traditional tool execution through middleware
                from ..types import ToolResult

                async def _tool_call(data):
                    task = asyncio.create_task(tool.execute(data.parameters))
                    if cancellation_token:
                        cancellation_token.link_future(task)
                    return await task

                # Execute through middleware chain (streaming)
                tool_result = None
                async for item in self.middleware_chain.execute_stream(
                    operation="tool_call",
                    agent_name=self.name,
                    agent_context=working_context,
                    data=tool_call,
                    func=_tool_call,
                ):
                    # Check if this is the final result (ToolResult)
                    # Events will be various event types
                    if isinstance(item, ToolResult):
                        tool_result = item
                    else:
                        # This is an event from middleware
                        yield item

                        # Check for approval pause
                        if isinstance(item, ToolApprovalEvent):
                            return  # PAUSE - middleware requested approval

                if tool_result is None:
                    # Middleware paused without yielding result
                    return

                result = ToolMessage(
                    content=str(tool_result.result)
                    if tool_result.success
                    else f"Error: {tool_result.error}",
                    source=self.name,
                    tool_call_id=tool_call.call_id,
                    tool_name=tool_call.tool_name,
                    success=tool_result.success,
                    error=tool_result.error,
                    metadata=tool_result.metadata,
                )

                # Emit tool response event
                tool_response_event = ToolCallResponseEvent(
                    source=self.name, call_id=tool_call.call_id, result=tool_result
                )
                yield tool_response_event

                # Add tool result to context and working messages
                working_context.add_message(result)
                llm_messages.append(result)

                # Yield the final result message
                yield result

        except asyncio.CancelledError:
            # Handle tool cancellation
            error_msg = "Tool execution was cancelled"
            error_result = ToolMessage(
                content=error_msg,
                source=self.name,
                tool_call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                success=False,
                error=error_msg,
            )

            # Add error result to context and working messages
            working_context.add_message(error_result)
            llm_messages.append(error_result)

            # Yield the error result
            yield error_result

            # Re-raise cancellation
            raise

        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            error_result = ToolMessage(
                content=error_msg,
                source=self.name,
                tool_call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                success=False,
                error=error_msg,
            )

            # Add error result to context and working messages
            working_context.add_message(error_result)
            llm_messages.append(error_result)

            # Yield the error result
            yield error_result

    def _to_config(self) -> AgentConfig:
        """Convert agent to configuration for serialization."""
        from ..tools import FunctionTool  # Import here to avoid circular import

        # Serialize model client
        model_client_config = self.model_client.dump_component()

        # Serialize tools (skip FunctionTools as they can't be serialized)
        tool_configs = []
        for tool in self.tools:
            if isinstance(tool, FunctionTool):
                # Skip FunctionTools as they cannot be serialized safely
                continue
            try:
                tool_configs.append(tool.dump_component())
            except NotImplementedError:
                # Skip tools that don't support serialization
                continue

        # Serialize memory if present
        memory_config = None
        if self.memory:
            try:
                memory_config = self.memory.dump_component()
            except NotImplementedError:
                # Skip memory that doesn't support serialization
                pass

        # Serialize output format schema if present
        output_format_schema = None
        if self.output_format:
            try:
                output_format_schema = self.output_format.model_json_schema()
            except Exception:
                # Skip if schema extraction fails
                pass

        return AgentConfig(
            name=self.name,
            description=self.description,
            instructions=self.instructions,
            model_client=model_client_config,
            tools=tool_configs,
            memory=memory_config,
            max_iterations=self.max_iterations,
            output_format_schema=output_format_schema,
            summarize_tool_result=self.summarize_tool_result,
        )

    @classmethod
    def _from_config(cls, config: AgentConfig) -> "Agent":
        """Create agent from configuration."""
        from pydantic import create_model

        from ..llm import BaseChatCompletionClient
        from ..memory import BaseMemory
        from ..tools import BaseTool

        # Deserialize model client
        model_client = BaseChatCompletionClient.load_component(config.model_client)

        # Deserialize tools
        tools = []
        for tool_config in config.tools:
            try:
                tool = BaseTool.load_component(tool_config)
                tools.append(tool)
            except Exception:
                # Skip tools that fail to deserialize
                continue

        # Deserialize memory
        memory = None
        if config.memory:
            try:
                memory = BaseMemory.load_component(config.memory)
            except Exception:
                # Skip memory that fails to deserialize
                pass

        # Recreate output format from schema if present
        output_format = None
        if config.output_format_schema:
            try:
                # Extract field definitions from schema (simplified approach)
                properties = config.output_format_schema.get("properties", {})
                field_definitions = {}
                for field_name, field_schema in properties.items():
                    # Use Any type for simplicity - could be enhanced later
                    from typing import Any

                    field_definitions[field_name] = (Any, None)

                if field_definitions:
                    schema_title = config.output_format_schema.get(
                        "title", "OutputFormat"
                    )
                    output_format = create_model(schema_title, **field_definitions)
            except Exception:
                # Skip if recreation fails
                pass

        return cls(
            name=config.name,
            description=config.description,
            instructions=config.instructions,
            model_client=model_client,
            tools=tools,
            memory=memory,
            max_iterations=config.max_iterations,
            output_format=output_format,
            summarize_tool_result=config.summarize_tool_result,
        )

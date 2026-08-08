"""
Execution engine for PicoAgents WebUI.

Streams raw PicoAgent events with session context management.
"""

import logging
from typing import Any, AsyncGenerator, List, Optional

from .._cancellation_token import CancellationToken
from ..messages import Message
from ..types import AgentResponse
from ..workflow import WorkflowRunner
from ._models import WebUIStreamEvent
from ._sessions import SessionManager

logger: logging.Logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Engine for executing PicoAgents entities with session management."""

    def __init__(self, session_manager: SessionManager) -> None:
        """Initialize execution engine.

        Args:
            session_manager: Session manager for tracking executions
        """
        self.session_manager = session_manager

    async def execute_agent_stream(
        self,
        agent: Any,
        messages: List[Message],
        session_id: Optional[str] = None,
        stream_tokens: bool = True,
        approval_responses: Optional[List[Any]] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream raw PicoAgent events with session management.

        Args:
            agent: Agent object to execute
            messages: New messages to add to session
            session_id: Optional existing session ID (creates new if None)
            stream_tokens: Enable token-level streaming
            approval_responses: Optional tool approval responses to inject into context
            cancellation_token: Optional token to cancel execution

        Yields:
            Server-sent events containing raw PicoAgent events
        """
        # Create or get existing session
        if session_id is None:
            session_id = self.session_manager.create_session_id()

        # Use both id and name - prefer id for consistency
        entity_id = getattr(agent, "id", None) or getattr(agent, "name", "unknown")
        context = await self.session_manager.get_or_create(
            session_id, entity_id, "agent"
        )

        # Inject approval responses into context before adding messages
        if approval_responses:
            for response in approval_responses:
                context.add_approval_response(response)

        # Add new messages to context
        for msg in messages:
            context.add_message(msg)

        try:
            # Stream raw PicoAgent events
            # Don't pass messages as task since we already added them to context
            # The agent will use context.messages directly
            async for event in agent.run_stream(
                task=None,  # Context already has messages
                context=context,
                verbose=True,
                stream_tokens=stream_tokens,
                cancellation_token=cancellation_token,
            ):
                # Transform AgentResponse to include messages at top level for frontend
                if isinstance(event, AgentResponse):
                    # Extract messages from context for frontend compatibility
                    event_data = {
                        "messages": [msg.model_dump() for msg in event.context.messages] if event.context else [],
                        "usage": event.usage.model_dump(),
                        "source": event.source,
                        "finish_reason": event.finish_reason,
                        "timestamp": event.timestamp.isoformat(),
                    }
                    wrapped_event = WebUIStreamEvent(
                        session_id=session_id,
                        event=event_data,
                    )
                else:
                    # Wrap the raw event with session context
                    wrapped_event = WebUIStreamEvent(
                        session_id=session_id,
                        event=event,  # Raw PicoAgent event
                    )

                yield f"data: {wrapped_event.model_dump_json()}\n\n"

            # Update session with final context
            # Agent has already updated context.messages internally
            await self.session_manager.update(session_id, context)

        except Exception as e:
            logger.error(f"Error in agent streaming execution: {e}")
            error_event = WebUIStreamEvent(
                session_id=session_id, event={"event_type": "error", "message": str(e)}
            )
            yield f"data: {error_event.model_dump_json()}\n\n"

    async def execute_orchestrator_stream(
        self,
        orchestrator: Any,
        messages: List[Message],
        session_id: Optional[str] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream raw orchestrator events with session management.

        Args:
            orchestrator: Orchestrator object to execute
            messages: New messages to add to session
            session_id: Optional existing session ID
            cancellation_token: Optional token to cancel execution

        Yields:
            Server-sent events containing raw orchestrator events
        """
        if session_id is None:
            session_id = self.session_manager.create_session_id()

        # Use both id and name - prefer id for consistency
        entity_id = getattr(orchestrator, "id", None) or getattr(orchestrator, "name", "unknown")
        context = await self.session_manager.get_or_create(
            session_id, entity_id, "orchestrator"
        )

        # Add new messages to context
        for msg in messages:
            context.add_message(msg)

        try:
            # Stream raw orchestrator events
            async for event in orchestrator.run_stream(
                context.messages, cancellation_token=cancellation_token
            ):
                wrapped_event = WebUIStreamEvent(
                    session_id=session_id, event=event
                )
                yield f"data: {wrapped_event.model_dump_json()}\n\n"

            # Update session
            await self.session_manager.update(session_id, context)

        except Exception as e:
            logger.error(f"Error in orchestrator streaming: {e}")
            error_event = WebUIStreamEvent(
                session_id=session_id, event={"event_type": "error", "message": str(e)}
            )
            yield f"data: {error_event.model_dump_json()}\n\n"

    async def execute_workflow_stream(
        self,
        workflow: Any,
        input_data: Any,
        session_id: Optional[str] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream raw workflow events with session management.

        Args:
            workflow: Workflow object to execute
            input_data: Input data for workflow
            session_id: Optional existing session ID
            cancellation_token: Optional token to cancel execution

        Yields:
            Server-sent events containing raw workflow events
        """
        if session_id is None:
            session_id = self.session_manager.create_session_id()

        # Use both id and name - prefer id for consistency
        entity_id = getattr(workflow, "id", None) or getattr(workflow, "name", "unknown")
        context = await self.session_manager.get_or_create(
            session_id, entity_id, "workflow"
        )

        # Store input data in metadata
        context.metadata["last_input"] = input_data

        try:
            # Create workflow runner and stream events
            runner = WorkflowRunner()
            async for event in runner.run_stream(
                workflow, input_data, cancellation_token=cancellation_token
            ):
                wrapped_event = WebUIStreamEvent(
                    session_id=session_id, event=event
                )
                yield f"data: {wrapped_event.model_dump_json()}\n\n"

            # Update session
            await self.session_manager.update(session_id, context)

        except Exception as e:
            logger.error(f"Error in workflow streaming: {e}")
            error_event = WebUIStreamEvent(
                session_id=session_id, event={"event_type": "error", "message": str(e)}
            )
            yield f"data: {error_event.model_dump_json()}\n\n"

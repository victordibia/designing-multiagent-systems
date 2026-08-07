"""
FastAPI server for PicoAgents WebUI.

Provides REST API endpoints and serves the frontend UI.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, List, Optional, cast

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .._cancellation_token import CancellationToken
from ..context import ToolApprovalResponse
from ..messages import Message
from ..types import AgentResponse
from ._execution import ExecutionEngine
from ._models import AddExampleRequest, Entity, HealthResponse
from ._registry import EntityRegistry
from ._sessions import SessionManager

logger: logging.Logger = logging.getLogger(__name__)


class RunEntityRequest(BaseModel):
    """Request model for entity execution - minimal wrapper around PicoAgents types."""

    messages: Optional[List[Message]] = Field(
        default=None, description="List of messages (for agents/orchestrators)"
    )
    input_data: Optional[Any] = Field(default=None, description="Input data (for workflows)")
    session_id: Optional[str] = Field(
        default=None, description="Optional session ID for tracking"
    )
    stream_tokens: bool = Field(
        True, description="Enable token-level streaming for agents (default: True)"
    )
    approval_responses: Optional[List[ToolApprovalResponse]] = Field(
        default=None, description="Tool approval responses to inject into session context"
    )


class PicoAgentsWebUIServer:
    """FastAPI server for PicoAgents WebUI."""

    def __init__(
        self,
        entities_dir: Optional[str] = None,
        enable_cors: bool = True,
        cors_origins: Optional[List[str]] = None,
    ) -> None:
        """Initialize the WebUI server.

        Args:
            entities_dir: Directory to scan for entities
            enable_cors: Whether to enable CORS middleware
            cors_origins: List of allowed CORS origins
        """
        self.entities_dir = entities_dir
        self.enable_cors = enable_cors
        self.cors_origins = cors_origins or ["*"]

        # Initialize components
        self.registry = EntityRegistry(entities_dir)
        self.session_manager = SessionManager()
        self.execution_engine = ExecutionEngine(self.session_manager)

        # Persistence store (optional — requires picoagents[persist])
        self._store = None
        try:
            from ..store import PicoStore

            self._store = PicoStore()
        except ImportError:
            logger.info(
                "sqlmodel not installed — persistence disabled. "
                "Install with: pip install picoagents[persist]"
            )

    def create_app(self) -> FastAPI:
        """Create the FastAPI application with all routes and middleware."""
        store = self._store

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            logger.info("Starting PicoAgents WebUI Server")
            if store is not None:
                await store.initialize()
                app.state.store = store
                from ._eval_jobs import EvalJobManager

                app.state.eval_jobs = EvalJobManager(store)
                logger.info("Persistence store initialized")
            yield
            # Shutdown
            playground = getattr(app.state, "mcp_playground", None)
            if playground is not None:
                await playground.shutdown()
            logger.info("Shutting down PicoAgents WebUI Server")

        app = FastAPI(
            title="PicoAgents WebUI",
            description="Web interface for interacting with PicoAgents entities",
            version="0.1.0",
            lifespan=lifespan,
        )

        if self.enable_cors:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=self.cors_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )

        self._register_routes(app)

        # Include persistence routers if store is available
        if store is not None:
            from ._eval_router import router as eval_router
            from ._runs_router import router as runs_router

            app.include_router(runs_router)
            app.include_router(eval_router)

        # MCP playground (requires picoagents[mcp] with mcp>=2.0)
        try:
            from picoagents.tools import MCP_AVAILABLE

            if MCP_AVAILABLE:
                from ._mcp_router import router as mcp_router

                app.include_router(mcp_router)
        except ImportError:
            logger.info("MCP not installed; playground routes disabled")

        self._mount_frontend(app)
        return app

    def _register_routes(self, app: FastAPI) -> None:
        """Register all API routes."""

        @app.get("/api/health", response_model=HealthResponse)
        async def health_check():
            """Health check endpoint."""
            entities = self.registry.list_entities()
            return HealthResponse(
                status="healthy",
                entities_dir=self.entities_dir,
                entities_count=len(entities),
            )

        @app.get("/api/entities", response_model=List[Entity])
        async def list_entities():
            """List all discovered entities."""
            try:
                return self.registry.list_entities()
            except Exception as e:
                logger.error(f"Error listing entities: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @app.get("/api/entities/{entity_id}", response_model=Entity)
        async def get_entity(entity_id: str):
            """Get detailed information about a specific entity."""
            entity_info = self.registry.get_entity_info(entity_id)
            if not entity_info:
                raise HTTPException(
                    status_code=404, detail=f"Entity {entity_id} not found"
                )
            return entity_info

        @app.delete("/api/entities/{entity_id}")
        async def delete_entity(entity_id: str):
            """Delete an entity from the registry."""
            try:
                removed = self.registry.unregister_entity(entity_id)
                if not removed:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Entity {entity_id} not found or cannot be removed (directory-discovered entities cannot be deleted)"
                    )
                return {"status": "success", "entity_id": entity_id, "message": "Entity removed successfully"}
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error deleting entity {entity_id}: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @app.post("/api/entities/{entity_id}/run", response_model=AgentResponse)
        async def run_entity(entity_id: str, request: RunEntityRequest):
            """Execute an entity (non-streaming)."""
            entity_obj = self.registry.get_entity_object(entity_id)
            if not entity_obj:
                raise HTTPException(
                    status_code=404, detail=f"Entity {entity_id} not found"
                )

            entity_info = self.registry.get_entity_info(entity_id)
            if not entity_info:
                raise HTTPException(
                    status_code=404, detail=f"Entity info for {entity_id} not found"
                )

            try:
                if entity_info.type == "agent":
                    if not request.messages:
                        raise HTTPException(
                            status_code=400,
                            detail="Messages required for agent execution",
                        )

                    return await self.execution_engine.execute_agent(
                        agent=entity_obj,
                        messages=cast(List[Any], request.messages),
                    )
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Non-streaming execution not supported for {entity_info.type}",
                    )

            except HTTPException:
                # Re-raise HTTP exceptions as-is
                raise
            except Exception as e:
                logger.error(f"Error executing entity {entity_id}: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @app.post("/api/entities/{entity_id}/run/stream")
        async def run_entity_stream(entity_id: str, request: RunEntityRequest):
            """Execute an entity with streaming response."""
            entity_obj = self.registry.get_entity_object(entity_id)
            if not entity_obj:
                raise HTTPException(
                    status_code=404, detail=f"Entity {entity_id} not found"
                )

            entity_info = self.registry.get_entity_info(entity_id)
            if not entity_info:
                raise HTTPException(
                    status_code=404, detail=f"Entity info for {entity_id} not found"
                )

            # Create cancellation token for this request
            cancellation_token = CancellationToken()

            async def cancellable_generator():
                """Wraps the event generator to detect client disconnect and trigger cancellation."""
                try:
                    if entity_info.type == "agent":
                        # Allow empty messages if approval_responses provided (resuming after approval)
                        if not request.messages and not request.approval_responses:
                            raise HTTPException(
                                status_code=400,
                                detail="Messages required for agent execution",
                            )

                        event_generator = self.execution_engine.execute_agent_stream(
                            agent=entity_obj,
                            messages=cast(List[Any], request.messages)
                            if request.messages
                            else [],
                            session_id=request.session_id,
                            stream_tokens=request.stream_tokens,
                            approval_responses=request.approval_responses,
                            cancellation_token=cancellation_token,
                        )
                    elif entity_info.type == "orchestrator":
                        if not request.messages:
                            raise HTTPException(
                                status_code=400,
                                detail="Messages required for orchestrator execution",
                            )

                        event_generator = self.execution_engine.execute_orchestrator_stream(
                            orchestrator=entity_obj,
                            messages=cast(List[Any], request.messages),
                            session_id=request.session_id,
                            cancellation_token=cancellation_token,
                        )
                    elif entity_info.type == "workflow":
                        if request.input_data is None:
                            raise HTTPException(
                                status_code=400,
                                detail="Input data required for workflow execution",
                            )

                        event_generator = self.execution_engine.execute_workflow_stream(
                            workflow=entity_obj,
                            input_data=request.input_data,
                            session_id=request.session_id,
                            cancellation_token=cancellation_token,
                        )
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Unknown entity type: {entity_info.type}",
                        )

                    # Stream events until completion or cancellation
                    async for event in event_generator:
                        yield event

                except (GeneratorExit, asyncio.CancelledError):
                    # Client disconnected - trigger cancellation
                    logger.info(
                        f"Client disconnected for {entity_info.type} {entity_id}, "
                        f"session {request.session_id}, triggering cancellation"
                    )
                    cancellation_token.cancel()
                    raise

            try:
                return StreamingResponse(
                    cancellable_generator(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Access-Control-Allow-Origin": "*",
                    },
                )

            except HTTPException:
                # Re-raise HTTP exceptions as-is
                raise
            except Exception as e:
                logger.error(f"Error streaming entity {entity_id}: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @app.get("/api/sessions")
        async def list_sessions(entity_id: Optional[str] = None):
            """List all sessions with metadata, optionally filtered by entity."""
            try:
                sessions = await self.session_manager.list(entity_id=entity_id)
                return sessions
            except Exception as e:
                logger.error(f"Error listing sessions: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @app.post("/api/sessions")
        async def create_session(request: dict):
            """Create a new empty session.

            Request body: {"entity_id": str, "entity_type": str}
            """
            try:
                entity_id = request.get("entity_id")
                entity_type = request.get("entity_type", "agent")

                if not entity_id:
                    raise HTTPException(status_code=400, detail="entity_id is required")

                # Generate new session ID
                session_id = self.session_manager.create_session_id()

                # Create empty session context
                context = await self.session_manager.get_or_create(
                    session_id, entity_id, entity_type
                )

                return {
                    "id": session_id,  # Match SessionInfo interface
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "created_at": context.created_at.isoformat(),
                    "message_count": 0,
                    "last_activity": context.created_at.isoformat(),
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error creating session: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @app.get("/api/sessions/{session_id}")
        async def get_session(session_id: str):
            """Get session context."""
            context = await self.session_manager.get(session_id)
            if not context:
                raise HTTPException(
                    status_code=404, detail=f"Session {session_id} not found"
                )
            return context.model_dump()

        @app.get("/api/sessions/{session_id}/messages")
        async def get_session_messages(session_id: str):
            """Get all messages for a session."""
            context = await self.session_manager.get(session_id)
            if not context:
                raise HTTPException(
                    status_code=404, detail=f"Session {session_id} not found"
                )

            return {
                "session_id": session_id,
                "messages": [msg.model_dump() for msg in context.messages],
            }

        @app.delete("/api/sessions/{session_id}")
        async def delete_session(session_id: str):
            """Delete a session."""
            success = await self.session_manager.delete(session_id)
            if not success:
                raise HTTPException(
                    status_code=404, detail=f"Session {session_id} not found"
                )
            return {"status": "deleted", "session_id": session_id}

        @app.post("/api/cache/clear")
        async def clear_cache():
            """Clear entity cache for hot reloading."""
            try:
                self.registry.clear_cache()
                return {"status": "cache_cleared"}
            except Exception as e:
                logger.error(f"Error clearing cache: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @app.get("/api/stats")
        async def get_stats():
            """Get system statistics."""
            try:
                entities = self.registry.list_entities()
                sessions = await self.session_manager.list()

                return {
                    "entities": {
                        "total": len(entities),
                        "by_type": {
                            "agents": len([e for e in entities if e.type == "agent"]),
                            "orchestrators": len(
                                [e for e in entities if e.type == "orchestrator"]
                            ),
                            "workflows": len(
                                [e for e in entities if e.type == "workflow"]
                            ),
                        },
                    },
                    "sessions": {
                        "total_sessions": len(sessions),
                        "total_messages": sum(s["message_count"] for s in sessions),
                    },
                }
            except Exception as e:
                logger.error(f"Error getting stats: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @app.post("/api/entities/add", response_model=Entity)
        async def add_example(request: AddExampleRequest):
            """Add an example from GitHub repository."""
            try:
                import tempfile
                import urllib.request
                from pathlib import Path

                # GitHub raw content URL
                # Note: Examples are at the root of the repository, not in picoagents subdirectory
                base_url = "https://raw.githubusercontent.com/victordibia/designing-multiagent-systems/main"
                file_url = f"{base_url}/{request.github_path}"

                logger.info(f"Downloading example from: {file_url}")

                # Download file content
                with urllib.request.urlopen(file_url) as response:
                    file_content = response.read().decode("utf-8")

                # Create a temporary directory for the example
                temp_dir = Path(tempfile.gettempdir()) / "picoagents_examples"
                temp_dir.mkdir(exist_ok=True)

                # Save the file
                example_file = temp_dir / f"{request.example_id}.py"
                example_file.write_text(file_content)

                logger.info(f"Saved example to: {example_file}")

                # Register with the entity registry
                entity_info = self.registry.register_from_file(
                    str(example_file), request.example_id
                )

                if not entity_info:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to register example: {request.example_id}",
                    )

                logger.info(f"Successfully registered example: {request.example_id}")
                return entity_info

            except urllib.error.HTTPError as e:
                logger.error(f"GitHub download failed: {e}")
                raise HTTPException(
                    status_code=404,
                    detail=f"Example not found on GitHub: {request.github_path}",
                )
            except Exception as e:
                logger.error(f"Error adding example: {e}")
                raise HTTPException(status_code=500, detail=str(e))

    def _mount_frontend(self, app: FastAPI) -> None:
        """Mount the frontend static files."""
        # Get the directory where this module is located
        module_dir = Path(__file__).parent
        frontend_dir = module_dir / "ui"

        # Only mount if frontend build directory exists
        if frontend_dir.exists() and frontend_dir.is_dir():
            app.mount(
                "/",
                StaticFiles(directory=str(frontend_dir), html=True),
                name="frontend",
            )
            logger.info(f"Mounted frontend from {frontend_dir}")
        else:
            logger.warning(f"Frontend not found at {frontend_dir} - serving API only")

            # Serve a simple message at root
            @app.get("/")
            async def root():
                return {
                    "message": "PicoAgents WebUI API",
                    "docs": "/docs",
                    "health": "/api/health",
                    "note": "Frontend not built - run 'npm run build' in frontend directory",
                }


def create_app(
    entities_dir: Optional[str] = None,
    **kwargs: Any,
) -> FastAPI:
    """Create FastAPI app for PicoAgents WebUI.

    Args:
        entities_dir: Directory to scan for entities
        **kwargs: Additional arguments passed to server

    Returns:
        FastAPI application instance
    """
    server = PicoAgentsWebUIServer(entities_dir=entities_dir, **kwargs)
    return server.create_app()

"""
PicoAgents WebUI - Web interface for PicoAgents entities.

Provides a web-based interface for discovering, running, and interacting with
PicoAgents agents, orchestrators, and workflows.
"""

import logging
from typing import Any, List, Optional

from ._cli import webui
from ._discovery import PicoAgentsScanner
from ._execution import ExecutionEngine
from ._models import (
    AgentInfo,
    Entity,
    EntityInfo,
    OrchestratorInfo,
    WorkflowInfo,
)
from ._registry import EntityRegistry
from ._server import PicoAgentsWebUIServer, create_app
from ._sessions import SessionManager

logger: logging.Logger = logging.getLogger(__name__)


def launch(
    entities_dir: Optional[str] = None,
    port: int = 8080,
    host: str = "127.0.0.1",
    auto_open: bool = True,
    reload: bool = False,
    log_level: str = "info",
) -> None:
    """Launch PicoAgents WebUI with entities discovery.

    This is the main entry point for launching the web interface. It will scan
    the specified directory for PicoAgents entities and start a web server.

    Args:
        entities_dir: Directory to scan for entities (default: current directory)
        port: Port to run the server on
        host: Host to bind the server to
        auto_open: Whether to automatically open browser
        reload: Enable auto-reload for development
        log_level: Logging level (debug, info, warning, error)

    Example:
        ```python
        from picoagents.webui import launch

        # Launch with default settings
        launch()

        # Launch with custom directory and port
        launch(entities_dir="./my_agents", port=8000)
        ```
    """
    webui(
        entities_dir=entities_dir,
        port=port,
        host=host,
        auto_open=auto_open,
        reload=reload,
        log_level=log_level,
    )


class WebUIServer:
    """Programmatic interface to the WebUI server.

    Provides fine-grained control over the WebUI server for advanced use cases
    and integration with larger applications.
    """

    def __init__(
        self,
        entities_dir: Optional[str] = None,
        port: int = 8080,
        host: str = "127.0.0.1",
        enable_cors: bool = True,
        cors_origins: Optional[List[str]] = None,
    ) -> None:
        """Initialize WebUI server.

        Args:
            entities_dir: Directory to scan for entities
            port: Port to run server on
            host: Host to bind server to
            enable_cors: Whether to enable CORS middleware
            cors_origins: List of allowed CORS origins
        """
        self._server = PicoAgentsWebUIServer(
            entities_dir=entities_dir,
            enable_cors=enable_cors,
            cors_origins=cors_origins,
        )
        self.port = port
        self.host = host
        self._app: Optional[Any] = None

    def register_entity(self, entity_id: str, entity_obj: Any) -> None:
        """Register an in-memory entity.

        Args:
            entity_id: Unique identifier for the entity
            entity_obj: Entity object (Agent, Orchestrator, or Workflow)

        Example:
            ```python
            from picoagents import Agent
            from picoagents.llm import OpenAIChatCompletionClient

            server = WebUIServer()

            agent = Agent(
                name="example",
                description="Example agent",
                instructions="You are a helpful assistant",
                model_client=OpenAIChatCompletionClient()
            )

            server.register_entity("my_agent", agent)
            ```
        """
        self._server.registry.register_entity(entity_id, entity_obj)

    def get_app(self) -> Any:
        """Get the FastAPI application instance.

        Returns:
            FastAPI application that can be embedded or extended
        """
        if self._app is None:
            self._app = self._server.create_app()
        return self._app

    def start(self, auto_open: bool = False) -> None:
        """Start the WebUI server.

        Args:
            auto_open: Whether to automatically open browser
        """
        entities_count = len(self._server.registry.list_entities())

        logger.info(f"📋 Serving {entities_count} entities")

        # Get the app with registered entities
        app = self.get_app()

        # Use the shared webui() function to start server
        webui(
            entities_dir=None,  # Don't scan - we have in-memory entities
            port=self.port,
            host=self.host,
            auto_open=auto_open,
            app=app,  # Pass our pre-configured app
        )


def serve(
    entities: Optional[List[Any]] = None,
    entities_dir: Optional[str] = None,
    port: int = 8080,
    host: str = "127.0.0.1",
    auto_open: bool = True,
) -> None:
    """Serve entities via web interface.

    Simple API for serving agents, orchestrators, and workflows.
    Entities can be provided directly as objects or discovered from a directory.

    Args:
        entities: List of entity objects (Agent, Orchestrator, Workflow) to serve
        entities_dir: Directory to scan for additional entities (if not provided,
                      only serves in-memory entities)
        port: Port to run server on (default: 8080)
        host: Host to bind server to (default: 127.0.0.1)
        auto_open: Whether to automatically open browser (default: True)

    Example:
        ```python
        from picoagents import Agent
        from picoagents.orchestration import RoundRobinOrchestrator
        from picoagents.webui import serve

        # Create entities
        agent = Agent(name="assistant", model="gpt-4", ...)
        orchestrator = RoundRobinOrchestrator(agents=[agent], ...)

        # Serve only in-memory entities
        serve(entities=[agent, orchestrator], port=8080)

        # Or serve from directory
        serve(entities_dir="./my_agents", port=8080)

        # Or both
        serve(
            entities=[agent],
            entities_dir="./more_agents",
            port=8080
        )
        ```
    """
    # Only pass entities_dir if explicitly provided
    # This prevents scanning current directory when serving only in-memory entities
    server = WebUIServer(
        entities_dir=entities_dir if entities_dir else None,
        port=port,
        host=host
    )

    if entities:
        for i, entity in enumerate(entities):
            # Auto-generate ID from entity name or use index-based fallback
            entity_id = getattr(entity, "name", f"entity_{i}")
            server.register_entity(entity_id, entity)
            logger.info(f"Registered entity: {entity_id}")

    server.start(auto_open=auto_open)


def scan_entities(directory: str) -> List[Entity]:
    """Scan a directory for PicoAgents entities.

    Args:
        directory: Directory path to scan

    Returns:
        List of discovered entities

    Example:
        ```python
        from picoagents.webui import scan_entities

        entities = scan_entities("./my_agents")
        for entity in entities:
            logger.info(f"Found {entity.type}: {entity.id}")
        ```
    """
    scanner = PicoAgentsScanner(directory)
    return scanner.discover_entities()


# Export main public API
__all__ = [
    # Main functions
    "launch",
    "serve",
    "scan_entities",
    "create_app",
    # Classes
    "WebUIServer",
    "PicoAgentsWebUIServer",
    "PicoAgentsScanner",
    "EntityRegistry",
    "SessionManager",
    "ExecutionEngine",
    # Models
    "Entity",
    "EntityInfo",
    "AgentInfo",
    "OrchestratorInfo",
    "WorkflowInfo",
    # CLI function
    "webui",
]

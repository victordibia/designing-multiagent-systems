"""
Discovery system for PicoAgents entities.

Scans directories for PicoAgents agents, orchestrators, and workflows following
standard naming conventions.
"""

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._models import AgentInfo, Entity, OrchestratorInfo, WorkflowInfo

logger: logging.Logger = logging.getLogger(__name__)


class PicoAgentsScanner:
    """Scans filesystem for PicoAgents entities following naming conventions."""

    def __init__(self, entities_dir: str) -> None:
        """Initialize scanner with entities directory.

        Args:
            entities_dir: Directory path to scan for entities
        """
        self.entities_dir = Path(entities_dir).resolve()
        self._entity_cache: Dict[str, Any] = {}

    def discover_entities(self) -> List[Entity]:
        """Discover all PicoAgents entities in the entities directory.

        Returns:
            List of discovered entities (agents, orchestrators, workflows)
        """
        if not self.entities_dir.exists():
            logger.warning(f"Entities directory does not exist: {self.entities_dir}")
            return []

        discovered: List[Entity] = []

        # Add entities directory to Python path if not already there
        if str(self.entities_dir) not in sys.path:
            sys.path.insert(0, str(self.entities_dir))

        # Scan only top-level items in the directory (not recursive)
        for item in self.entities_dir.iterdir():
            # Skip hidden files/dirs and __pycache__
            if item.name.startswith(".") or item.name == "__pycache__":
                continue

            try:
                if item.is_dir():
                    # Directory-based entity (e.g., my_agent/__init__.py or my_agent/agent.py)
                    entities = self._discover_entities_in_directory(item)
                    discovered.extend(entities)
                elif (
                    item.is_file()
                    and item.suffix == ".py"
                    and not item.name.startswith("_")
                ):
                    # Single file entity (e.g., my_agent.py)
                    entities = self._discover_entities_in_file(item)
                    discovered.extend(entities)

            except Exception as e:
                logger.warning(f"Error scanning {item}: {e}")
                continue

        logger.info(f"Discovered {len(discovered)} PicoAgents entities")
        return discovered

    def get_entity_object(self, entity_id: str) -> Optional[Any]:
        """Get the actual entity object for execution.

        Args:
            entity_id: Entity identifier

        Returns:
            Entity object or None if not found
        """
        if entity_id in self._entity_cache:
            module = self._entity_cache[entity_id]
            return self._find_entity_in_module(module)

        # Try to reload if not in cache. Minted IDs are "{base_id}.{type}",
        # while _get_entity_id returns the bare base, so compare the base part.
        base_id = entity_id.rsplit(".", 1)[0]
        for py_file in self.entities_dir.rglob("*.py"):
            if self._get_entity_id(py_file) == base_id:
                module = self._load_module(py_file, entity_id)
                if module:
                    self._entity_cache[entity_id] = module
                    return self._find_entity_in_module(module)

        return None

    def clear_cache(self) -> None:
        """Clear the entity cache for hot reloading."""
        # Remove from sys.modules
        for entity_id in list(self._entity_cache.keys()):
            sys.modules.pop(f"picoagents_entity_{entity_id}", None)

        self._entity_cache.clear()
        logger.info("Cleared entity cache")

    def _discover_entities_in_directory(self, dir_path: Path) -> List[Entity]:
        """Discover entities in a directory using multiple import patterns.

        Args:
            dir_path: Directory containing entity

        Returns:
            List of discovered entities
        """
        entity_id = dir_path.name
        logger.debug(f"Scanning directory: {entity_id}")

        discovered: List[Entity] = []

        # Try different import patterns
        import_patterns = [
            entity_id,  # __init__.py
            f"{entity_id}.agent",  # agent.py
            f"{entity_id}.workflow",  # workflow.py
            f"{entity_id}.orchestrator",  # orchestrator.py
        ]

        for pattern in import_patterns:
            try:
                module = self._load_module_from_pattern(pattern)
                if module:
                    entities = self._find_entities_in_module(
                        module, entity_id, str(dir_path)
                    )
                    if entities:
                        discovered.extend(entities)
                        logger.debug(f"Found {len(entities)} entities in {pattern}")
                        break  # Stop after first successful pattern
            except Exception as e:
                logger.debug(f"Error trying pattern {pattern}: {e}")
                continue

        return discovered

    def _discover_entities_in_file(self, file_path: Path) -> List[Entity]:
        """Discover entities in a single Python file.

        Args:
            file_path: Python file to scan

        Returns:
            List of discovered entities
        """
        entity_id = file_path.stem
        logger.debug(f"Scanning file: {file_path.name}")

        try:
            module = self._load_module(file_path, entity_id)
            if module:
                return self._find_entities_in_module(module, entity_id, str(file_path))
        except Exception as e:
            logger.debug(f"Error scanning file {file_path}: {e}")

        return []

    def _load_module_from_pattern(self, pattern: str) -> Optional[Any]:
        """Load module using import pattern.

        Args:
            pattern: Import pattern to try (e.g., 'my_agent' or 'my_agent.agent')

        Returns:
            Loaded module or None if failed
        """
        try:
            # Check if module exists first
            spec = importlib.util.find_spec(pattern)
            if spec is None:
                return None

            module = importlib.import_module(pattern)
            logger.debug(f"Successfully imported {pattern}")
            return module

        except ModuleNotFoundError:
            logger.debug(f"Import pattern {pattern} not found")
            return None
        except Exception as e:
            logger.warning(f"Error importing {pattern}: {e}")
            return None

    def _find_entities_in_module(
        self, module: Any, base_id: str, module_path: str
    ) -> List[Entity]:
        """Find agent, orchestrator, and workflow entities in a loaded module.

        Args:
            module: Loaded Python module
            base_id: Base identifier for entities
            module_path: Path to module for metadata

        Returns:
            List of discovered entities
        """
        discovered: List[Entity] = []

        # Look for explicit variable names
        candidates = [
            ("agent", getattr(module, "agent", None)),
            ("orchestrator", getattr(module, "orchestrator", None)),
            ("workflow", getattr(module, "workflow", None)),
        ]

        for obj_type, obj in candidates:
            if obj is None:
                continue

            if self._is_valid_entity(obj, obj_type):
                entity_info = self._extract_entity_info_from_object(
                    obj, obj_type, base_id, module_path
                )
                if entity_info:
                    discovered.append(entity_info)
                    # Cache the module for later use
                    self._entity_cache[entity_info.id] = module
                    logger.debug(f"Found {obj_type}: {entity_info.id}")

        return discovered

    def _extract_entity_info_from_object(
        self, obj: Any, obj_type: str, base_id: str, module_path: str
    ) -> Optional[Entity]:
        """Extract entity information from a live object.

        Args:
            obj: Entity object
            obj_type: Type of entity (agent, orchestrator, workflow)
            base_id: Base identifier
            module_path: Path to module

        Returns:
            Entity information or None if extraction failed
        """
        try:
            # Generate entity ID
            entity_id = f"{base_id}.{obj_type}"

            # Common attributes
            common_attrs = {
                "id": entity_id,
                "name": getattr(obj, "name", base_id),
                "description": getattr(obj, "description", None),
                "source": "directory",
                "module_path": module_path,
                "has_env": (Path(module_path).parent / ".env").exists()
                if Path(module_path).is_file()
                else (Path(module_path) / ".env").exists(),
            }

            # Create appropriate info object based on type
            if obj_type == "agent":
                return self._create_agent_info(obj, common_attrs)
            elif obj_type == "orchestrator":
                return self._create_orchestrator_info(obj, common_attrs)
            elif obj_type == "workflow":
                return self._create_workflow_info(obj, common_attrs)

        except Exception as e:
            logger.warning(f"Error extracting entity info from {obj_type}: {e}")

        return None

    def _get_entity_id(self, py_file: Path) -> str:
        """Generate entity ID from file path.

        Args:
            py_file: Path to Python file

        Returns:
            Entity identifier
        """
        # Use relative path from entities_dir as ID
        relative_path = py_file.relative_to(self.entities_dir)
        return str(relative_path.with_suffix("")).replace("/", ".")

    def _load_module(self, py_file: Path, entity_id: str) -> Optional[Any]:
        """Load Python module from file.

        Args:
            py_file: Path to Python file
            entity_id: Entity identifier for module name

        Returns:
            Loaded module or None if loading failed
        """
        try:
            spec = importlib.util.spec_from_file_location(entity_id, py_file)
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[f"picoagents_entity_{entity_id}"] = module
            spec.loader.exec_module(module)

            logger.debug(f"Successfully loaded module {entity_id} from {py_file}")
            return module

        except Exception as e:
            logger.debug(f"Failed to load module {entity_id} from {py_file}: {e}")
            return None

    def _find_entity_in_module(self, module: Any) -> Optional[Any]:
        """Find PicoAgents entity in a loaded module.

        Args:
            module: Loaded Python module

        Returns:
            Entity object or None if not found
        """
        # Check for standard variable names
        candidates = [
            ("agent", getattr(module, "agent", None)),
            ("orchestrator", getattr(module, "orchestrator", None)),
            ("workflow", getattr(module, "workflow", None)),
        ]

        for name, obj in candidates:
            if obj is None:
                continue

            # Validate the object type
            if self._is_valid_entity(obj, name):
                return obj

        return None

    def _is_valid_entity(self, obj: Any, expected_type: str) -> bool:
        """Check if object is a valid PicoAgents entity.

        Args:
            obj: Object to validate
            expected_type: Expected type (agent, orchestrator, workflow)

        Returns:
            True if object is valid for the expected type
        """
        if expected_type == "agent":
            # Try strict type checking first
            try:
                from ..agents import BaseAgent

                if isinstance(obj, BaseAgent):
                    return True
            except ImportError:
                pass

            # Fall back to duck typing for mocks
            return (
                hasattr(obj, "run")
                and callable(getattr(obj, "run"))
                and hasattr(obj, "name")
                and hasattr(obj, "description")
            )

        elif expected_type == "orchestrator":
            # Try strict type checking first
            try:
                from ..orchestration import BaseOrchestrator

                if isinstance(obj, BaseOrchestrator):
                    return True
            except ImportError:
                pass

            # Fall back to duck typing for mocks
            return (
                hasattr(obj, "run_stream")
                and callable(getattr(obj, "run_stream"))
                and hasattr(obj, "agents")
                and hasattr(obj, "name")
            )

        elif expected_type == "workflow":
            # Try strict type checking first
            try:
                from ..workflow import Workflow

                if isinstance(obj, Workflow):
                    return True
            except ImportError:
                pass

            # Fall back to duck typing
            return hasattr(obj, "run_stream") and callable(getattr(obj, "run_stream"))

        return False



    def _create_agent_info(self, agent: Any, common_attrs: Dict[str, Any]) -> AgentInfo:
        """Create AgentInfo from agent object.

        Args:
            agent: Agent object
            common_attrs: Common attributes

        Returns:
            AgentInfo instance
        """
        tools = self._extract_agent_tools(agent)
        model = getattr(getattr(agent, "model_client", None), "model", None)
        memory_type = (
            type(getattr(agent, "memory", None)).__name__
            if getattr(agent, "memory", None)
            else None
        )
        example_tasks = getattr(agent, "example_tasks", [])

        return AgentInfo(
            **common_attrs,
            type="agent",
            tools=tools,
            model=model,
            memory_type=memory_type,
            example_tasks=example_tasks,
        )

    def _create_orchestrator_info(
        self, orchestrator: Any, common_attrs: Dict[str, Any]
    ) -> OrchestratorInfo:
        """Create OrchestratorInfo from orchestrator object.

        Args:
            orchestrator: Orchestrator object
            common_attrs: Common attributes

        Returns:
            OrchestratorInfo instance
        """
        orchestrator_type = (
            type(orchestrator).__name__.lower().replace("orchestrator", "")
        )
        agents = [agent.name for agent in getattr(orchestrator, "agents", [])]
        termination_conditions = self._extract_termination_conditions(orchestrator)
        example_tasks = getattr(orchestrator, "example_tasks", [])

        return OrchestratorInfo(
            **common_attrs,
            type="orchestrator",
            orchestrator_type=orchestrator_type,
            agents=agents,
            termination_conditions=termination_conditions,
            tools=[],  # Orchestrators don't have direct tools
            example_tasks=example_tasks,
        )

    def _create_workflow_info(
        self, workflow: Any, common_attrs: Dict[str, Any]
    ) -> WorkflowInfo:
        """Create WorkflowInfo from workflow object.

        Args:
            workflow: Workflow object
            common_attrs: Common attributes

        Returns:
            WorkflowInfo instance
        """
        steps = (
            list(getattr(workflow, "steps", {}).keys())
            if hasattr(workflow, "steps")
            else []
        )
        # Try both start_step and start_step_id for compatibility
        start_step = getattr(workflow, "start_step_id", None) or getattr(workflow, "start_step", None)
        input_schema = getattr(workflow, "input_schema", None)

        # If no explicit input_schema, try to infer from the start step's input_type
        if input_schema is None and start_step and hasattr(workflow, "steps"):
            workflow_steps = getattr(workflow, "steps", {})
            if start_step in workflow_steps:
                first_step = workflow_steps[start_step]
                if hasattr(first_step, "input_type"):
                    input_type = first_step.input_type
                    # Check if it's a Pydantic model with a schema
                    if hasattr(input_type, "model_json_schema"):
                        try:
                            input_schema = input_type.model_json_schema()
                        except Exception as e:
                            logger.debug(f"Could not extract input schema: {e}")

        example_tasks = getattr(workflow, "example_tasks", [])

        return WorkflowInfo(
            **common_attrs,
            type="workflow",
            steps=steps,
            start_step=start_step,
            input_schema=input_schema,
            tools=[],  # Workflows have steps, not direct tools
            example_tasks=example_tasks,
        )

    def _extract_agent_tools(self, agent: Any) -> List[str]:
        """Extract tool names from an agent.

        Args:
            agent: Agent object

        Returns:
            List of tool names
        """
        tools = getattr(agent, "tools", [])
        return [getattr(tool, "name", str(tool)) for tool in tools]

    def _extract_termination_conditions(self, orchestrator: Any) -> List[str]:
        """Extract termination condition names from an orchestrator.

        Args:
            orchestrator: Orchestrator object

        Returns:
            List of termination condition names
        """
        termination = getattr(orchestrator, "termination", None)
        if termination is None:
            return []

        if hasattr(termination, "__class__"):
            return [termination.__class__.__name__]

        return []

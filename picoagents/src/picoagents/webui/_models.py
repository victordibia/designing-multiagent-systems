"""
Minimal WebUI-specific models - reuse PicoAgents types everywhere else!
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import ConfigDict, BaseModel, Field


class EntityInfo(BaseModel):
    """WebUI-specific: Discovery metadata for entities."""

    id: str = Field(description="Unique identifier for the entity")
    name: Optional[str] = Field(default=None, description="Human-readable name")
    description: Optional[str] = Field(default=None, description="Entity description")
    type: str = Field(description="Entity type (agent, orchestrator, workflow)")
    source: str = Field(description="Source of discovery (directory, memory)")
    module_path: Optional[str] = Field(default=None, description="Path to the Python module")
    tools: List[str] = Field(
        default_factory=list, description="Available tools/functions"
    )
    has_env: bool = Field(False, description="Whether .env file exists")
    example_tasks: List[str] = Field(
        default_factory=list, description="Example tasks to help users discover capabilities"
    )


class AgentInfo(EntityInfo):
    """WebUI-specific: Agent discovery metadata."""

    type: str = Field(default="agent", description="Always 'agent'")
    model: Optional[str] = Field(default=None, description="LLM model being used")
    memory_type: Optional[str] = Field(default=None, description="Type of memory system")


class OrchestratorInfo(EntityInfo):
    """WebUI-specific: Orchestrator discovery metadata."""

    type: str = Field(default="orchestrator", description="Always 'orchestrator'")
    orchestrator_type: str = Field(
        description="Type of orchestrator (round_robin, ai, plan)"
    )
    agents: List[str] = Field(
        default_factory=list, description="Participating agent names"
    )
    termination_conditions: List[str] = Field(
        default_factory=list, description="Active termination conditions"
    )


class WorkflowInfo(EntityInfo):
    """WebUI-specific: Workflow discovery metadata."""

    type: str = Field(default="workflow", description="Always 'workflow'")
    steps: List[str] = Field(default_factory=list, description="Workflow step IDs")
    input_schema: Optional[Dict[str, Any]] = Field(
        default=None, description="Input schema definition"
    )
    start_step: Optional[str] = Field(default=None, description="Starting step ID")


# Union type for all entity discovery info
Entity = Union[AgentInfo, OrchestratorInfo, WorkflowInfo]


class WebUIStreamEvent(BaseModel):
    """WebUI-specific: Wrapper for PicoAgent events with session context."""

    session_id: str = Field(description="Session this event belongs to")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Event timestamp"
    )
    event: Any = Field(
        description="The actual PicoAgent event (AgentEvent, Message, etc.)"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)


class HealthResponse(BaseModel):
    """WebUI-specific: Health check response."""

    status: str = Field(description="Health status")
    entities_dir: Optional[str] = Field(default=None, description="Directory being scanned")
    entities_count: int = Field(0, description="Number of discovered entities")


class AddExampleRequest(BaseModel):
    """Request to add an example from GitHub."""

    example_id: str = Field(
        description="Example identifier (e.g., 'basic-agent', 'round-robin')"
    )
    github_path: str = Field(
        description="Path to example file in GitHub repo (e.g., 'examples/agents/basic-agent.py')"
    )


# For API requests, use PicoAgents types directly:
# - Use picoagents.messages.Message for chat messages
# - Use picoagents.types.AgentResponse for responses
# - Use picoagents.types.AgentEvent for events
# - Use List[Message] for message lists

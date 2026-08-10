"""SQLModel table definitions for PicoAgents persistence.

Defines 6 tables:
- runs: Universal run log for agent/orchestrator/eval executions
- datasets: Eval dataset metadata
- tasks: Individual eval tasks within datasets
- target_configs: Saved agent configurations for eval
- eval_runs: Eval run orchestration metadata
- eval_results: Per task x target scores

All tables use JSON columns for complex nested data (stored as text
in SQLite, parsed by SQLAlchemy). Heavy data (trajectories, messages)
lives in JSON files; these tables store only indexed metadata + a
file_path pointer.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Column
from sqlalchemy import JSON as SA_JSON
from sqlmodel import Field, SQLModel


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


# ---------------------------------------------------------------------------
# Runs — universal run log
# ---------------------------------------------------------------------------


class DBRun(SQLModel, table=True):
    """A single agent, orchestrator, or eval-task execution."""

    __tablename__ = "runs"

    id: str = Field(default_factory=_short_uuid, primary_key=True)
    run_type: str = Field(index=True)  # "agent" | "orchestrator" | "eval_task"
    agent_name: str = Field(index=True)
    model: Optional[str] = None
    status: str = "completed"  # "completed" | "error" | "cancelled"
    finish_reason: Optional[str] = None

    task_input: Optional[str] = None  # First user message, truncated
    duration_ms: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    llm_calls: int = 0
    tool_calls: int = 0
    cost_estimate: Optional[float] = None

    trace_id: Optional[str] = Field(default=None, index=True)
    tags: Optional[List[str]] = Field(
        default=None, sa_column=Column(SA_JSON)
    )
    parent_run_id: Optional[str] = Field(default=None, index=True)

    file_path: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


# ---------------------------------------------------------------------------
# Datasets — eval dataset metadata
# ---------------------------------------------------------------------------


class DBDataset(SQLModel, table=True):
    """A collection of tasks for evaluation."""

    __tablename__ = "datasets"

    id: str = Field(default_factory=_short_uuid, primary_key=True)
    name: str = Field(index=True)
    version: str = "1.0.0"
    description: str = ""
    source: str = "user"  # "user" | "builtin" | "generated"
    categories: Optional[List[str]] = Field(
        default=None, sa_column=Column(SA_JSON)
    )
    default_eval_criteria: Optional[List[str]] = Field(
        default=None, sa_column=Column(SA_JSON)
    )
    task_count: int = 0
    metadata_json: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column("metadata", SA_JSON)
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Tasks — individual eval tasks
# ---------------------------------------------------------------------------


class DBTask(SQLModel, table=True):
    """A single evaluation task, belongs to a dataset."""

    __tablename__ = "tasks"

    id: str = Field(default_factory=_short_uuid, primary_key=True)
    dataset_id: str = Field(index=True)
    # The task's id within its dataset. Not globally unique - two datasets
    # may each number their tasks 1..n - so it cannot be the primary key.
    task_key: Optional[str] = Field(default=None, index=True)
    name: str
    input: str
    expected_output: Optional[str] = None
    category: str = "general"
    eval_criteria: Optional[List[str]] = Field(
        default=None, sa_column=Column(SA_JSON)
    )
    rubric: Optional[Dict[str, str]] = Field(
        default=None, sa_column=Column(SA_JSON)
    )
    metadata_json: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column("metadata", SA_JSON)
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Target Configs — saved agent configurations for eval
# ---------------------------------------------------------------------------


class DBTargetConfig(SQLModel, table=True):
    """Saved agent configuration for evaluation targets."""

    __tablename__ = "target_configs"

    id: str = Field(default_factory=_short_uuid, primary_key=True)
    name: str = Field(index=True)
    target_type: str = "picoagent"  # "picoagent" | "claude_code" | "discovered_agent"
    config: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column(SA_JSON)
    )
    entity_id: Optional[str] = None
    description: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Eval Runs — eval run orchestration
# ---------------------------------------------------------------------------


class DBEvalRun(SQLModel, table=True):
    """An evaluation run: dataset × targets."""

    __tablename__ = "eval_runs"

    id: str = Field(default_factory=_short_uuid, primary_key=True)
    dataset_id: str = Field(index=True)
    dataset_name: str = ""
    status: str = "pending"  # "pending" | "running" | "completed" | "error" | "cancelled"

    target_ids: Optional[List[str]] = Field(
        default=None, sa_column=Column(SA_JSON)
    )
    target_names: Optional[List[str]] = Field(
        default=None, sa_column=Column(SA_JSON)
    )
    judge_type: Optional[str] = None
    judge_config: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column(SA_JSON)
    )

    # Progress tracking
    total_tasks: int = 0
    completed_tasks: int = 0
    current_target: Optional[str] = None
    current_task: Optional[str] = None

    error_message: Optional[str] = None
    file_path: Optional[str] = None

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Eval Results — per task × target scores
# ---------------------------------------------------------------------------


class DBEvalResult(SQLModel, table=True):
    """Result of one task × one target within an eval run."""

    __tablename__ = "eval_results"

    id: str = Field(default_factory=_short_uuid, primary_key=True)
    eval_run_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)

    task_id: str
    target_name: str = Field(index=True)
    overall_score: float = 0.0
    dimensions: Optional[Dict[str, float]] = Field(
        default=None, sa_column=Column(SA_JSON)
    )
    reasoning: Optional[Dict[str, str]] = Field(
        default=None, sa_column=Column(SA_JSON)
    )

    success: bool = False
    error: Optional[str] = None
    duration_ms: int = 0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    iterations: int = 0
    tool_calls: int = 0

    created_at: datetime = Field(default_factory=datetime.utcnow)

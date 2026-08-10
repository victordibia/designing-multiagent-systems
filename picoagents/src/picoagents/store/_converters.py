"""Converters between PicoAgents domain types and DB models.

Bridges the gap between runtime types (AgentResponse, OrchestrationResponse,
EvalResults, TaskResult) and the SQLModel DB models. Uses existing
serialization methods (model_dump, to_dict) wherever possible.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ._models import (
    DBDataset,
    DBEvalResult,
    DBEvalRun,
    DBRun,
    DBTask,
    DBTargetConfig,
    _short_uuid,
)

if TYPE_CHECKING:
    from ..agents._base import BaseAgent
    from ..eval._config import AgentConfig
    from ..eval._dataset import Dataset
    from ..eval._results import EvalResults, TaskResult
    from ..orchestration._base import BaseOrchestrator
    from ..types import AgentResponse, OrchestrationResponse


def _extract_task_input(response: AgentResponse) -> Optional[str]:
    """Extract first user message from an agent response, truncated."""
    if response.context:
        for msg in response.context.messages:
            if hasattr(msg, "role") and getattr(msg, "role", None) == "user":
                content = msg.content
                return content[:500] if len(content) > 500 else content
    return None


def _get_model_name(obj: Any) -> Optional[str]:
    """Extract model name from an agent or orchestrator."""
    if hasattr(obj, "model_client"):
        return getattr(obj.model_client, "model", None)
    return None


# ---------------------------------------------------------------------------
# Agent/Orchestrator runs → DBRun
# ---------------------------------------------------------------------------


def agent_response_to_db_run(
    agent: BaseAgent,
    response: AgentResponse,
    trace_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> DBRun:
    """Convert an AgentResponse to a DBRun row."""
    return DBRun(
        run_type="agent",
        agent_name=agent.name,
        model=_get_model_name(agent),
        status="completed" if response.finish_reason == "stop" else response.finish_reason,
        finish_reason=response.finish_reason,
        task_input=_extract_task_input(response),
        duration_ms=response.usage.duration_ms,
        tokens_input=response.usage.tokens_input,
        tokens_output=response.usage.tokens_output,
        llm_calls=response.usage.llm_calls,
        tool_calls=response.usage.tool_calls,
        cost_estimate=response.usage.cost_estimate,
        trace_id=trace_id,
        tags=tags,
        created_at=response.timestamp or datetime.utcnow(),
    )


def orchestration_response_to_db_run(
    orchestrator: BaseOrchestrator,
    response: OrchestrationResponse,
    trace_id: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> DBRun:
    """Convert an OrchestrationResponse to a DBRun row."""
    # Extract first user message from orchestration messages
    task_input = None
    for msg in response.messages:
        if hasattr(msg, "role") and getattr(msg, "role", None) == "user":
            content = msg.content
            task_input = content[:500] if len(content) > 500 else content
            break

    return DBRun(
        run_type="orchestrator",
        agent_name=orchestrator.name or orchestrator.__class__.__name__,
        model=None,  # orchestrators use multiple models
        status="completed",
        finish_reason=response.stop_message.source if response.stop_message else "completed",
        task_input=task_input,
        duration_ms=response.usage.duration_ms,
        tokens_input=response.usage.tokens_input,
        tokens_output=response.usage.tokens_output,
        llm_calls=response.usage.llm_calls,
        tool_calls=response.usage.tool_calls,
        cost_estimate=response.usage.cost_estimate,
        trace_id=trace_id,
        tags=tags,
    )


# ---------------------------------------------------------------------------
# Dataset ↔ DB
# ---------------------------------------------------------------------------


def dataset_to_db(
    dataset: Dataset,
) -> tuple[DBDataset, list[DBTask]]:
    """Convert a Dataset to DB models."""
    db_dataset = DBDataset(
        name=dataset.name,
        version=dataset.version,
        description=dataset.description,
        source="builtin",
        categories=dataset.categories or [],
        default_eval_criteria=dataset.default_eval_criteria or ["task_completion"],
        task_count=len(dataset.tasks),
        metadata_json=dataset.metadata or {},
    )

    db_tasks = []
    for task in dataset.tasks:
        db_task = DBTask(
            task_key=task.id,
            dataset_id=db_dataset.id,
            name=task.name,
            input=task.input,
            expected_output=task.expected_output,
            category=task.category,
            eval_criteria=task.eval_criteria or [],
            rubric=task.rubric or {},
            metadata_json=task.metadata or {},
        )
        db_tasks.append(db_task)

    return db_dataset, db_tasks


def db_to_dataset(
    db_dataset: DBDataset, db_tasks: list[DBTask]
) -> Dataset:
    """Convert DB models back to a Dataset."""
    from ..eval._dataset import Dataset
    from ..types import Task

    tasks = [
        Task(
            id=t.task_key or t.id,
            name=t.name,
            input=t.input,
            expected_output=t.expected_output,
            category=t.category,
            eval_criteria=t.eval_criteria or [],
            rubric=t.rubric or {},
            metadata=t.metadata_json or {},
        )
        for t in db_tasks
    ]

    return Dataset(
        name=db_dataset.name,
        version=db_dataset.version,
        description=db_dataset.description,
        tasks=tasks,
        categories=db_dataset.categories or [],
        default_eval_criteria=db_dataset.default_eval_criteria or ["task_completion"],
        metadata=db_dataset.metadata_json or {},
    )


# ---------------------------------------------------------------------------
# AgentConfig ↔ DBTargetConfig
# ---------------------------------------------------------------------------


def agent_config_to_db_target(config: AgentConfig) -> DBTargetConfig:
    """Convert an AgentConfig to a DBTargetConfig."""
    return DBTargetConfig(
        name=config.name,
        target_type="picoagent",
        config=config.to_dict(),
        description=f"{config.model_provider}/{config.model_name}",
    )


def db_target_to_agent_config(db_target: DBTargetConfig) -> AgentConfig:
    """Convert a DBTargetConfig back to an AgentConfig."""
    from ..eval._config import AgentConfig

    return AgentConfig.from_dict(db_target.config or {})


# ---------------------------------------------------------------------------
# TaskResult → DBEvalResult
# ---------------------------------------------------------------------------


def task_result_to_db_eval_result(
    eval_run_id: str,
    task_result: TaskResult,
    run_id: Optional[str] = None,
) -> DBEvalResult:
    """Convert a TaskResult to a DBEvalResult row."""
    return DBEvalResult(
        eval_run_id=eval_run_id,
        run_id=run_id,
        task_id=task_result.task_id,
        target_name=task_result.target_name,
        overall_score=task_result.score.overall,
        dimensions=task_result.score.dimensions or {},
        reasoning=task_result.score.reasoning or {},
        success=task_result.trajectory.success,
        error=task_result.trajectory.error,
        duration_ms=task_result.duration_ms,
        total_tokens=task_result.total_tokens,
        input_tokens=task_result.input_tokens,
        output_tokens=task_result.output_tokens,
        iterations=task_result.iterations,
        tool_calls=task_result.trajectory.usage.tool_calls
        if task_result.trajectory.usage
        else 0,
    )


# ---------------------------------------------------------------------------
# EvalResults → DB rows
# ---------------------------------------------------------------------------


def eval_results_to_db(
    results: EvalResults,
    file_path: Optional[str] = None,
) -> tuple[DBEvalRun, list[DBEvalResult]]:
    """Convert EvalResults to DB models (eval_run + eval_results)."""
    db_eval_run = DBEvalRun(
        id=results.run_id,
        dataset_id="",  # Must be set by caller if known
        dataset_name=results.dataset_name,
        status="completed",
        target_names=results.target_names,
        total_tasks=len(results.task_ids) * len(results.target_names),
        completed_tasks=len(results.task_ids) * len(results.target_names),
        file_path=file_path,
        completed_at=datetime.utcnow(),
    )

    db_results = []
    for target_name, tasks in results.results.items():
        for task_id, task_result in tasks.items():
            db_result = task_result_to_db_eval_result(
                eval_run_id=results.run_id,
                task_result=task_result,
            )
            db_results.append(db_result)

    return db_eval_run, db_results

"""Async data store for PicoAgents persistence.

PicoStore uses SQLModel + SQLAlchemy async engine for the DB index,
and writes full run data to JSON files on disk. The DB stores only
queryable metadata; JSON files contain complete trajectories, messages,
and tool call details.

Default backend is SQLite via aiosqlite. Swappable to PostgreSQL
via connection_string parameter.

Usage:
    store = PicoStore()
    await store.initialize()

    # From Agent.run(persist=True):
    await store.save_agent_run(agent, response)

    # From EvalRunner.run(persist=True):
    await store.save_eval_run(results, file_path)
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Dict,
    List,
    Optional,
    Sequence,
    Union,
)

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from ._converters import (
    agent_response_to_db_run,
    dataset_to_db,
    db_to_dataset,
    eval_results_to_db,
    orchestration_response_to_db_run,
    task_result_to_db_eval_result,
)
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
    from ..eval._results import EvalResults, TaskResult
    from ..orchestration._base import BaseOrchestrator
    from ..types import AgentResponse, OrchestrationResponse

logger = logging.getLogger(__name__)

DEFAULT_DB_DIR = Path.home() / ".picoagents"


class PicoStore:
    """Async data store with swappable backends.

    Stores indexed metadata in a database and full run data in JSON files.

    Args:
        connection_string: SQLAlchemy async connection string.
            Defaults to sqlite+aiosqlite:///~/.picoagents/picoagents.db
        runs_dir: Directory for agent/orchestrator run JSON files.
            Defaults to ~/.picoagents/runs/
        eval_dir: Directory for eval result JSON files.
            Defaults to ~/.picoagents/eval/
    """

    def __init__(
        self,
        connection_string: Optional[str] = None,
        runs_dir: Optional[str] = None,
        eval_dir: Optional[str] = None,
    ) -> None:
        if connection_string is None:
            db_dir = DEFAULT_DB_DIR
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = db_dir / "picoagents.db"
            connection_string = f"sqlite+aiosqlite:///{db_path}"

        self._connection_string = connection_string
        self._engine: Optional[AsyncEngine] = None
        self._initialized = False

        self._runs_dir = Path(runs_dir) if runs_dir else DEFAULT_DB_DIR / "runs"
        self._eval_dir = Path(eval_dir) if eval_dir else DEFAULT_DB_DIR / "eval"

    async def initialize(self) -> None:
        """Create engine and tables. Idempotent."""
        if self._initialized:
            return
        self._engine = create_async_engine(
            self._connection_string,
            echo=False,
        )
        async with self._engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        self._runs_dir.mkdir(parents=True, exist_ok=True)
        self._eval_dir.mkdir(parents=True, exist_ok=True)
        self._initialized = True
        logger.info(f"PicoStore initialized: {self._connection_string}")

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            await self.initialize()

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Async context manager for database sessions."""
        await self._ensure_initialized()
        assert self._engine is not None
        async with AsyncSession(self._engine) as sess:
            yield sess

    # -----------------------------------------------------------------------
    # Runs CRUD
    # -----------------------------------------------------------------------

    async def save_agent_run(
        self,
        agent: BaseAgent,
        response: AgentResponse,
        trace_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Persist an agent run: write JSON file + insert DB row.

        Returns the run_id.
        """
        await self._ensure_initialized()  # creates runs_dir before we write into it
        db_run = agent_response_to_db_run(agent, response, trace_id, tags)
        run_id = db_run.id  # capture before session expiry

        # Write JSON file
        json_data = {
            "run_id": run_id,
            "run_type": "agent",
            "agent_name": agent.name,
            "model": db_run.model,
            "finish_reason": response.finish_reason,
            "created_at": response.timestamp.isoformat()
            if response.timestamp
            else datetime.utcnow().isoformat(),
            "response": response.model_dump(mode="json"),
        }
        file_path = self._runs_dir / f"run_{run_id}.json"
        file_path.write_text(
            json.dumps(json_data, indent=2, default=str)
        )
        db_run.file_path = str(file_path)

        async with self.session() as sess:
            sess.add(db_run)
            await sess.commit()

        logger.info(f"Saved agent run {run_id} → {file_path}")
        return run_id

    async def save_orchestrator_run(
        self,
        orchestrator: BaseOrchestrator,
        response: OrchestrationResponse,
        trace_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Persist an orchestrator run: write JSON file + insert DB row."""
        await self._ensure_initialized()  # creates runs_dir before we write into it
        db_run = orchestration_response_to_db_run(
            orchestrator, response, trace_id, tags
        )
        run_id = db_run.id  # capture before session expiry

        json_data = {
            "run_id": run_id,
            "run_type": "orchestrator",
            "agent_name": db_run.agent_name,
            "finish_reason": db_run.finish_reason,
            "created_at": datetime.utcnow().isoformat(),
            "response": response.model_dump(mode="json"),
        }
        file_path = self._runs_dir / f"run_{run_id}.json"
        file_path.write_text(
            json.dumps(json_data, indent=2, default=str)
        )
        db_run.file_path = str(file_path)

        async with self.session() as sess:
            sess.add(db_run)
            await sess.commit()

        logger.info(f"Saved orchestrator run {run_id} → {file_path}")
        return run_id

    async def list_runs(
        self,
        run_type: Optional[str] = None,
        agent_name: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List persisted runs, newest first."""
        async with self.session() as sess:
            stmt = select(DBRun).order_by(col(DBRun.created_at).desc())
            if run_type:
                stmt = stmt.where(DBRun.run_type == run_type)
            if agent_name:
                stmt = stmt.where(DBRun.agent_name == agent_name)
            stmt = stmt.offset(offset).limit(limit)

            result = await sess.exec(stmt)
            runs = result.all()
            return [_model_to_dict(r) for r in runs]

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get run metadata from DB."""
        async with self.session() as sess:
            run = await sess.get(DBRun, run_id)
            return _model_to_dict(run) if run else None

    async def get_run_data(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Read full run data from JSON file."""
        async with self.session() as sess:
            run = await sess.get(DBRun, run_id)
            if not run or not run.file_path:
                return None

        file_path = Path(run.file_path)
        if not file_path.exists():
            return None

        return json.loads(file_path.read_text())

    async def delete_run(self, run_id: str) -> bool:
        """Delete run DB row + JSON file."""
        async with self.session() as sess:
            run = await sess.get(DBRun, run_id)
            if not run:
                return False

            # Delete JSON file
            if run.file_path:
                file_path = Path(run.file_path)
                if file_path.exists():
                    file_path.unlink()

            await sess.delete(run)
            await sess.commit()
            return True

    # -----------------------------------------------------------------------
    # Datasets CRUD
    # -----------------------------------------------------------------------

    async def create_dataset(
        self,
        name: str,
        tasks: List[Dict[str, Any]],
        version: str = "1.0.0",
        description: str = "",
        source: str = "user",
        categories: Optional[List[str]] = None,
        default_eval_criteria: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a dataset with tasks."""
        db_dataset = DBDataset(
            name=name,
            version=version,
            description=description,
            source=source,
            categories=categories or [],
            default_eval_criteria=default_eval_criteria or ["task_completion"],
            task_count=len(tasks),
        )

        db_tasks = []
        for task_data in tasks:
            db_task = DBTask(
                dataset_id=db_dataset.id,
                name=task_data.get("name", ""),
                input=task_data.get("input", ""),
                expected_output=task_data.get("expected_output"),
                category=task_data.get("category", "general"),
                eval_criteria=task_data.get("eval_criteria"),
                rubric=task_data.get("rubric"),
                metadata_json=task_data.get("metadata"),
            )
            db_tasks.append(db_task)

        async with self.session() as sess:
            sess.add(db_dataset)
            for t in db_tasks:
                sess.add(t)
            await sess.commit()
            await sess.refresh(db_dataset)
            for t in db_tasks:
                await sess.refresh(t)
            result = _model_to_dict(db_dataset)
            result["tasks"] = [_model_to_dict(t) for t in db_tasks]
        return result

    async def list_datasets(self) -> List[Dict[str, Any]]:
        """List all datasets."""
        async with self.session() as sess:
            result = await sess.exec(
                select(DBDataset).order_by(col(DBDataset.created_at).desc())
            )
            return [_model_to_dict(d) for d in result.all()]

    async def get_dataset(
        self, dataset_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get dataset with all its tasks."""
        async with self.session() as sess:
            dataset = await sess.get(DBDataset, dataset_id)
            if not dataset:
                return None

            result = await sess.exec(
                select(DBTask).where(DBTask.dataset_id == dataset_id)
            )
            tasks = result.all()

            d = _model_to_dict(dataset)
            d["tasks"] = [_model_to_dict(t) for t in tasks]
            return d

    async def delete_dataset(self, dataset_id: str) -> bool:
        """Delete dataset and all its tasks."""
        async with self.session() as sess:
            dataset = await sess.get(DBDataset, dataset_id)
            if not dataset:
                return False

            # Delete tasks
            result = await sess.exec(
                select(DBTask).where(DBTask.dataset_id == dataset_id)
            )
            for task in result.all():
                await sess.delete(task)

            await sess.delete(dataset)
            await sess.commit()
            return True

    async def import_builtin_dataset(self, name: str) -> Dict[str, Any]:
        """Import a built-in dataset from eval/datasets/."""
        from ..eval._dataset import load_builtin_dataset

        dataset = load_builtin_dataset(name)
        db_dataset, db_tasks = dataset_to_db(dataset)
        db_dataset.source = "builtin"

        async with self.session() as sess:
            sess.add(db_dataset)
            for t in db_tasks:
                sess.add(t)
            await sess.commit()
            await sess.refresh(db_dataset)
            for t in db_tasks:
                await sess.refresh(t)
            result = _model_to_dict(db_dataset)
            result["tasks"] = [_model_to_dict(t) for t in db_tasks]
        return result

    async def add_task(
        self, dataset_id: str, task_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Add a task to an existing dataset."""
        async with self.session() as sess:
            dataset = await sess.get(DBDataset, dataset_id)
            if not dataset:
                return None

            db_task = DBTask(
                dataset_id=dataset_id,
                name=task_data.get("name", ""),
                input=task_data.get("input", ""),
                expected_output=task_data.get("expected_output"),
                category=task_data.get("category", "general"),
                eval_criteria=task_data.get("eval_criteria"),
                rubric=task_data.get("rubric"),
                metadata_json=task_data.get("metadata"),
            )
            sess.add(db_task)

            dataset.task_count += 1
            dataset.updated_at = datetime.utcnow()
            sess.add(dataset)

            await sess.commit()
            await sess.refresh(db_task)
            return _model_to_dict(db_task)

    async def update_task(
        self, task_id: str, updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a task's fields."""
        async with self.session() as sess:
            task = await sess.get(DBTask, task_id)
            if not task:
                return None

            for key, value in updates.items():
                if key == "metadata":
                    setattr(task, "metadata_json", value)
                elif hasattr(task, key):
                    setattr(task, key, value)

            task.updated_at = datetime.utcnow()
            sess.add(task)
            await sess.commit()
            await sess.refresh(task)
            return _model_to_dict(task)

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task and update dataset count."""
        async with self.session() as sess:
            task = await sess.get(DBTask, task_id)
            if not task:
                return False

            dataset = await sess.get(DBDataset, task.dataset_id)
            if dataset:
                dataset.task_count = max(0, dataset.task_count - 1)
                dataset.updated_at = datetime.utcnow()
                sess.add(dataset)

            await sess.delete(task)
            await sess.commit()
            return True

    # -----------------------------------------------------------------------
    # Target Configs CRUD
    # -----------------------------------------------------------------------

    async def create_target_config(
        self,
        name: str,
        target_type: str = "picoagent",
        config: Optional[Dict[str, Any]] = None,
        entity_id: Optional[str] = None,
        description: str = "",
    ) -> Dict[str, Any]:
        """Create a target configuration."""
        db_config = DBTargetConfig(
            name=name,
            target_type=target_type,
            config=config,
            entity_id=entity_id,
            description=description,
        )
        async with self.session() as sess:
            sess.add(db_config)
            await sess.commit()
            await sess.refresh(db_config)
            return _model_to_dict(db_config)

    async def list_target_configs(self) -> List[Dict[str, Any]]:
        """List all target configurations."""
        async with self.session() as sess:
            result = await sess.exec(
                select(DBTargetConfig).order_by(
                    col(DBTargetConfig.created_at).desc()
                )
            )
            return [_model_to_dict(c) for c in result.all()]

    async def get_target_config(
        self, config_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get a target configuration."""
        async with self.session() as sess:
            config = await sess.get(DBTargetConfig, config_id)
            return _model_to_dict(config) if config else None

    async def delete_target_config(self, config_id: str) -> bool:
        """Delete a target configuration."""
        async with self.session() as sess:
            config = await sess.get(DBTargetConfig, config_id)
            if not config:
                return False
            await sess.delete(config)
            await sess.commit()
            return True

    # -----------------------------------------------------------------------
    # Eval Runs CRUD
    # -----------------------------------------------------------------------

    async def create_eval_run(
        self,
        dataset_id: str,
        dataset_name: str,
        target_ids: List[str],
        target_names: List[str],
        total_tasks: int,
        judge_type: Optional[str] = None,
        judge_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create an eval run record."""
        db_run = DBEvalRun(
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            status="pending",
            target_ids=target_ids,
            target_names=target_names,
            judge_type=judge_type,
            judge_config=judge_config,
            total_tasks=total_tasks,
        )
        async with self.session() as sess:
            sess.add(db_run)
            await sess.commit()
            await sess.refresh(db_run)
            return _model_to_dict(db_run)

    async def list_eval_runs(self) -> List[Dict[str, Any]]:
        """List all eval runs."""
        async with self.session() as sess:
            result = await sess.exec(
                select(DBEvalRun).order_by(col(DBEvalRun.created_at).desc())
            )
            return [_model_to_dict(r) for r in result.all()]

    async def get_eval_run(
        self, eval_run_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get eval run with progress info."""
        async with self.session() as sess:
            run = await sess.get(DBEvalRun, eval_run_id)
            return _model_to_dict(run) if run else None

    async def update_eval_run_progress(
        self,
        eval_run_id: str,
        completed_tasks: Optional[int] = None,
        current_target: Optional[str] = None,
        current_task: Optional[str] = None,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
        file_path: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> None:
        """Update eval run progress fields."""
        async with self.session() as sess:
            run = await sess.get(DBEvalRun, eval_run_id)
            if not run:
                return

            if completed_tasks is not None:
                run.completed_tasks = completed_tasks
            if current_target is not None:
                run.current_target = current_target
            if current_task is not None:
                run.current_task = current_task
            if status is not None:
                run.status = status
            if error_message is not None:
                run.error_message = error_message
            if file_path is not None:
                run.file_path = file_path
            if started_at is not None:
                run.started_at = started_at
            if completed_at is not None:
                run.completed_at = completed_at

            sess.add(run)
            await sess.commit()

    async def save_eval_run_from_results(
        self,
        results: EvalResults,
        file_path: Optional[Union[str, Path]] = None,
    ) -> str:
        """Persist eval results: insert eval_run + eval_results rows.

        Called by EvalRunner.run(persist=True) after results.save().
        """
        # The column is a string; coerce so a Path from a caller cannot
        # blow up the INSERT (it silently lost every eval run before).
        db_eval_run, db_results = eval_results_to_db(
            results, str(file_path) if file_path is not None else None
        )
        eval_run_id = db_eval_run.id  # capture before session expiry
        result_count = len(db_results)

        async with self.session() as sess:
            sess.add(db_eval_run)
            for r in db_results:
                sess.add(r)
            await sess.commit()

        logger.info(
            f"Saved eval run {eval_run_id} with "
            f"{result_count} results"
        )
        return eval_run_id

    # -----------------------------------------------------------------------
    # Eval Results CRUD
    # -----------------------------------------------------------------------

    async def save_eval_result(
        self,
        eval_run_id: str,
        task_result: TaskResult,
        run_id: Optional[str] = None,
    ) -> str:
        """Save a single eval result row."""
        db_result = task_result_to_db_eval_result(
            eval_run_id, task_result, run_id
        )
        result_id = db_result.id  # capture before session expiry
        async with self.session() as sess:
            sess.add(db_result)
            await sess.commit()
        return result_id

    async def get_eval_results(
        self, eval_run_id: str
    ) -> List[Dict[str, Any]]:
        """Get all results for an eval run."""
        async with self.session() as sess:
            result = await sess.exec(
                select(DBEvalResult).where(
                    DBEvalResult.eval_run_id == eval_run_id
                )
            )
            return [_model_to_dict(r) for r in result.all()]

    async def get_eval_result(
        self, result_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get a single eval result."""
        async with self.session() as sess:
            result = await sess.get(DBEvalResult, result_id)
            return _model_to_dict(result) if result else None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_default_store: Optional[PicoStore] = None


def get_default_store() -> PicoStore:
    """Get or create the default PicoStore singleton.

    Uses SQLite at ~/.picoagents/picoagents.db.
    Initialization is lazy — the DB is created on first async call.
    """
    global _default_store
    if _default_store is None:
        _default_store = PicoStore()
    return _default_store


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _model_to_dict(model: Optional[SQLModel]) -> Dict[str, Any]:
    """Convert a SQLModel instance to a dict, handling datetime serialization."""
    if model is None:
        return {}
    data = {}
    for key, value in model.model_dump().items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()
        else:
            data[key] = value
    return data

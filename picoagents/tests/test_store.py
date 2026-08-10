"""
Tests for the persistence store.

The store shipped with no tests and three of its bugs were only visible
against a *fresh* store or a *second* dataset, so every test here builds
its own temp store rather than reusing a session-scoped one.
"""

import pathlib
import tempfile

import pytest

pytest.importorskip("sqlmodel", reason="persistence extra not installed")

from sqlmodel import select  # noqa: E402

from picoagents.messages import AssistantMessage  # noqa: E402
from picoagents.store._converters import (  # noqa: E402
    dataset_to_db,
    db_to_dataset,
)
from picoagents.store._models import DBTask  # noqa: E402
from picoagents.store._store import PicoStore  # noqa: E402
from picoagents.types import AgentResponse, Task, Usage  # noqa: E402

USAGE = Usage(
    duration_ms=1,
    llm_calls=1,
    tokens_input=1,
    tokens_output=1,
    tool_calls=0,
    memory_operations=0,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def store():
    """A store rooted in an empty directory - nothing created yet."""
    tmp = pathlib.Path(tempfile.mkdtemp())
    return PicoStore(
        connection_string=f"sqlite+aiosqlite:///{tmp}/t.db",
        runs_dir=str(tmp / "runs"),
        eval_dir=str(tmp / "eval"),
    )


class _StubAgent:
    name = "stub"
    description = "d"
    model_client = None


def _dataset(name: str) -> "object":
    """Two datasets built this way share the dataset-local task id 'task-1'."""
    from picoagents.eval._dataset import Dataset

    return Dataset(
        name=name,
        version="1.0.0",
        description="",
        tasks=[Task(id="task-1", name="t1", input="x")],
        default_eval_criteria=["task_completion"],
    )


@pytest.mark.anyio
async def test_first_run_persists_on_a_fresh_store(store):
    """The runs directory is created before anything is written into it."""
    response = AgentResponse(
        source="stub",
        messages=[AssistantMessage(content="hi", source="stub")],
        usage=USAGE,
        finish_reason="stop",
    )

    run_id = await store.save_agent_run(_StubAgent(), response)

    assert run_id
    assert (store._runs_dir / f"run_{run_id}.json").exists()


@pytest.mark.anyio
async def test_two_datasets_may_share_task_ids(store):
    """Task ids are dataset-local, so they cannot be the global primary key."""
    await store.initialize()

    for name in ("alpha", "beta"):
        db_dataset, db_tasks = dataset_to_db(_dataset(name))
        async with store.session() as session:
            session.add(db_dataset)
            for db_task in db_tasks:
                session.add(db_task)
            await session.commit()

    async with store.session() as session:
        rows = (await session.exec(select(DBTask))).all()

    assert len(rows) == 2
    assert len({row.id for row in rows}) == 2  # distinct primary keys
    assert {row.task_key for row in rows} == {"task-1"}  # same local id
    assert len({row.dataset_id for row in rows}) == 2


def test_dataset_round_trip_preserves_local_task_ids():
    db_dataset, db_tasks = dataset_to_db(_dataset("alpha"))
    restored = db_to_dataset(db_dataset, db_tasks)
    assert [t.id for t in restored.tasks] == ["task-1"]


@pytest.mark.anyio
async def test_eval_run_accepts_a_path_for_file_path(store):
    """The runner passes a Path. Binding one to the VARCHAR column raised, and
    the runner swallowed it, so every persisted eval run was silently lost."""
    from picoagents.eval._results import EvalResults

    await store.initialize()
    results = EvalResults(dataset_name="d", dataset_version="1.0.0")

    eval_run_id = await store.save_eval_run_from_results(
        results, file_path=store._eval_dir / "x.json"  # a Path, deliberately
    )

    assert eval_run_id

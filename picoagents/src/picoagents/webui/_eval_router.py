"""Eval API router — datasets, targets, eval runs, results.

Provides REST endpoints for the Evaluate tab in the WebUI:
- Datasets CRUD + built-in import
- Target configs CRUD
- Eval runs: launch (background), progress polling, cancel
- Eval results: per-run listing and drill-down
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/eval", tags=["eval"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateDatasetRequest(BaseModel):
    name: str
    tasks: List[Dict[str, Any]]
    version: str = "1.0.0"
    description: str = ""
    source: str = "user"
    categories: Optional[List[str]] = None
    default_eval_criteria: Optional[List[str]] = None


class ImportBuiltinRequest(BaseModel):
    name: str


class CreateTaskRequest(BaseModel):
    name: str = ""
    input: str = ""
    expected_output: Optional[str] = None
    category: str = "general"
    eval_criteria: Optional[List[str]] = None
    rubric: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class UpdateTaskRequest(BaseModel):
    name: Optional[str] = None
    input: Optional[str] = None
    expected_output: Optional[str] = None
    category: Optional[str] = None
    eval_criteria: Optional[List[str]] = None
    rubric: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class CreateTargetRequest(BaseModel):
    name: str
    target_type: str = "picoagent"
    config: Optional[Dict[str, Any]] = None
    entity_id: Optional[str] = None
    description: str = ""


class StartEvalRunRequest(BaseModel):
    dataset_id: str
    target_ids: List[str]
    judge_config: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_store(request: Request):
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="Persistence not available — install picoagents[persist]",
        )
    return store


def _get_eval_jobs(request: Request):
    jobs = getattr(request.app.state, "eval_jobs", None)
    if jobs is None:
        raise HTTPException(
            status_code=503,
            detail="Eval job manager not available",
        )
    return jobs


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


@router.get("/datasets")
async def list_datasets(request: Request):
    store = _get_store(request)
    return await store.list_datasets()


@router.post("/datasets")
async def create_dataset(request: Request, body: CreateDatasetRequest):
    store = _get_store(request)
    return await store.create_dataset(
        name=body.name,
        tasks=body.tasks,
        version=body.version,
        description=body.description,
        source=body.source,
        categories=body.categories,
        default_eval_criteria=body.default_eval_criteria,
    )


@router.post("/datasets/import")
async def import_builtin(request: Request, body: ImportBuiltinRequest):
    store = _get_store(request)
    try:
        return await store.import_builtin_dataset(body.name)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/builtin-datasets")
async def list_builtins(request: Request):
    """List available built-in datasets."""
    from ..eval._dataset import list_builtin_datasets

    return list_builtin_datasets()


@router.get("/datasets/{dataset_id}")
async def get_dataset(request: Request, dataset_id: str):
    store = _get_store(request)
    data = await store.get_dataset(dataset_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return data


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(request: Request, dataset_id: str):
    store = _get_store(request)
    deleted = await store.delete_dataset(dataset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"status": "deleted", "dataset_id": dataset_id}


# --- Tasks within datasets ---


@router.post("/datasets/{dataset_id}/tasks")
async def add_task(
    request: Request, dataset_id: str, body: CreateTaskRequest,
):
    store = _get_store(request)
    result = await store.add_task(
        dataset_id, body.model_dump(exclude_none=True)
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return result


@router.put("/datasets/{dataset_id}/tasks/{task_id}")
async def update_task(
    request: Request,
    dataset_id: str,
    task_id: str,
    body: UpdateTaskRequest,
):
    store = _get_store(request)
    updates = body.model_dump(exclude_none=True)
    result = await store.update_task(task_id, updates)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.delete("/datasets/{dataset_id}/tasks/{task_id}")
async def delete_task(
    request: Request, dataset_id: str, task_id: str,
):
    store = _get_store(request)
    deleted = await store.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "deleted", "task_id": task_id}


# ---------------------------------------------------------------------------
# Target Configs
# ---------------------------------------------------------------------------


@router.get("/targets")
async def list_targets(request: Request):
    store = _get_store(request)
    return await store.list_target_configs()


@router.post("/targets")
async def create_target(request: Request, body: CreateTargetRequest):
    store = _get_store(request)
    return await store.create_target_config(
        name=body.name,
        target_type=body.target_type,
        config=body.config,
        entity_id=body.entity_id,
        description=body.description,
    )


@router.get("/targets/{target_id}")
async def get_target(request: Request, target_id: str):
    store = _get_store(request)
    data = await store.get_target_config(target_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Target not found")
    return data


@router.delete("/targets/{target_id}")
async def delete_target(request: Request, target_id: str):
    store = _get_store(request)
    deleted = await store.delete_target_config(target_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Target not found")
    return {"status": "deleted", "target_id": target_id}


# ---------------------------------------------------------------------------
# Eval Runs
# ---------------------------------------------------------------------------


@router.get("/runs")
async def list_eval_runs(request: Request):
    store = _get_store(request)
    return await store.list_eval_runs()


@router.post("/runs")
async def start_eval_run(request: Request, body: StartEvalRunRequest):
    """Start a background eval run."""
    store = _get_store(request)
    eval_jobs = _get_eval_jobs(request)

    # Look up dataset for metadata
    dataset_data = await store.get_dataset(body.dataset_id)
    if not dataset_data:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Look up targets for metadata
    target_names = []
    for tid in body.target_ids:
        tc = await store.get_target_config(tid)
        target_names.append(tc["name"] if tc else tid)

    total_tasks = dataset_data.get("task_count", 0) * len(body.target_ids)

    # Create DB record
    eval_run = await store.create_eval_run(
        dataset_id=body.dataset_id,
        dataset_name=dataset_data.get("name", ""),
        target_ids=body.target_ids,
        target_names=target_names,
        total_tasks=total_tasks,
        judge_type=body.judge_config.get("type") if body.judge_config else None,
        judge_config=body.judge_config,
    )

    # Launch background job
    await eval_jobs.start_eval_run(
        eval_run_id=eval_run["id"],
        dataset_id=body.dataset_id,
        target_ids=body.target_ids,
        judge_config=body.judge_config,
    )

    return eval_run


@router.get("/runs/{eval_run_id}")
async def get_eval_run(request: Request, eval_run_id: str):
    store = _get_store(request)
    data = await store.get_eval_run(eval_run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Eval run not found")
    return data


@router.get("/runs/{eval_run_id}/results")
async def get_eval_results(request: Request, eval_run_id: str):
    store = _get_store(request)
    return await store.get_eval_results(eval_run_id)


@router.get("/runs/{eval_run_id}/results/{result_id}")
async def get_eval_result(request: Request, eval_run_id: str, result_id: str):
    store = _get_store(request)
    data = await store.get_eval_result(result_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return data


@router.post("/runs/{eval_run_id}/cancel")
async def cancel_eval_run(request: Request, eval_run_id: str):
    eval_jobs = _get_eval_jobs(request)
    cancelled = await eval_jobs.cancel_eval_run(eval_run_id)
    if not cancelled:
        raise HTTPException(
            status_code=404,
            detail="Eval run not found or not running",
        )
    return {"status": "cancelled", "eval_run_id": eval_run_id}


@router.get("/runs/{eval_run_id}/export")
async def export_eval_run(request: Request, eval_run_id: str):
    """Export eval run data as JSON (reads the full JSON file)."""
    store = _get_store(request)
    run_data = await store.get_eval_run(eval_run_id)
    if not run_data:
        raise HTTPException(status_code=404, detail="Eval run not found")

    file_path = run_data.get("file_path")
    if not file_path:
        raise HTTPException(
            status_code=404, detail="No export file available"
        )
    from pathlib import Path

    fp = Path(file_path)
    if not fp.exists():
        raise HTTPException(
            status_code=404, detail="Export file not found on disk"
        )

    from fastapi.responses import Response

    return Response(
        content=fp.read_text(),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="eval_{eval_run_id}.json"'
        },
    )

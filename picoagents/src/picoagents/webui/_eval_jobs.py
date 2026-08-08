"""Background eval job manager.

Manages asyncio tasks for long-running eval runs, with progress
tracking and cancellation support via CancellationToken.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .._cancellation_token import CancellationToken

if TYPE_CHECKING:
    from ..store._store import PicoStore

logger = logging.getLogger(__name__)


class EvalJobManager:
    """Spawn and manage background eval runs."""

    def __init__(self, store: PicoStore) -> None:
        self._store = store
        self._active_jobs: Dict[str, asyncio.Task] = {}  # type: ignore[type-arg]
        self._cancellation_tokens: Dict[str, CancellationToken] = {}

    async def start_eval_run(
        self,
        eval_run_id: str,
        dataset_id: str,
        target_ids: List[str],
        judge_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Spawn an asyncio task that runs the evaluation."""
        token = CancellationToken()
        self._cancellation_tokens[eval_run_id] = token

        task = asyncio.create_task(
            self._execute(eval_run_id, dataset_id, target_ids, judge_config, token)
        )
        self._active_jobs[eval_run_id] = task

        # Cleanup reference when done
        task.add_done_callback(lambda _: self._cleanup(eval_run_id))

    async def cancel_eval_run(self, eval_run_id: str) -> bool:
        """Cancel a running eval via its CancellationToken."""
        token = self._cancellation_tokens.get(eval_run_id)
        if token is None:
            return False
        token.cancel()

        # Update DB status
        await self._store.update_eval_run_progress(
            eval_run_id, status="cancelled", completed_at=datetime.now(timezone.utc)
        )
        return True

    def _cleanup(self, eval_run_id: str) -> None:
        self._active_jobs.pop(eval_run_id, None)
        self._cancellation_tokens.pop(eval_run_id, None)

    async def _execute(
        self,
        eval_run_id: str,
        dataset_id: str,
        target_ids: List[str],
        judge_config: Optional[Dict[str, Any]],
        cancellation_token: CancellationToken,
    ) -> None:
        """Run the full evaluation in the background."""
        try:
            # Mark as running
            await self._store.update_eval_run_progress(
                eval_run_id, status="running", started_at=datetime.now(timezone.utc)
            )

            # Load dataset from DB → domain Dataset
            dataset_data = await self._store.get_dataset(dataset_id)
            if not dataset_data:
                raise ValueError(f"Dataset {dataset_id} not found")

            from ..eval._dataset import Dataset
            from ..types import Task

            tasks = []
            for t in dataset_data.get("tasks", []):
                tasks.append(
                    Task(
                        id=t.get("id", t.get("name", "")),
                        name=t.get("name", ""),
                        input=t.get("input", ""),
                        expected_output=t.get("expected_output"),
                        category=t.get("category", "general"),
                        eval_criteria=t.get("eval_criteria") or [],
                    )
                )

            dataset = Dataset(
                name=dataset_data.get("name", ""),
                version=dataset_data.get("version", "1.0.0"),
                description=dataset_data.get("description", ""),
                tasks=tasks,
                default_eval_criteria=dataset_data.get(
                    "default_eval_criteria", ["task_completion"]
                ),
            )

            # Load target configs from DB → Target instances
            from ..eval._config import AgentConfig
            from ..eval._targets import PicoAgentTarget

            targets = []
            for tid in target_ids:
                tc_data = await self._store.get_target_config(tid)
                if not tc_data:
                    logger.warning(f"Target config {tid} not found, skipping")
                    continue

                if tc_data.get("target_type") == "picoagent":
                    config_dict = tc_data.get("config", {})
                    if config_dict:
                        agent_config = AgentConfig.from_dict(config_dict)
                        targets.append(PicoAgentTarget(agent_config))
                    else:
                        logger.warning(
                            f"Target {tid} has no config, skipping"
                        )

            if not targets:
                raise ValueError("No valid targets found")

            # Create judge
            judge = self._create_judge(judge_config)

            # Run evaluation task-by-task for progress tracking
            from ..eval._runner import EvalRunner

            runner = EvalRunner(judge=judge)
            completed = 0

            from ..eval._results import EvalResults

            results = EvalResults(
                dataset_name=dataset.name,
                dataset_version=dataset.version,
            )

            for target in targets:
                if cancellation_token.is_cancelled():
                    break

                await self._store.update_eval_run_progress(
                    eval_run_id, current_target=target.name
                )

                for task in dataset.tasks:
                    if cancellation_token.is_cancelled():
                        break

                    await self._store.update_eval_run_progress(
                        eval_run_id, current_task=task.name
                    )

                    task_result = await runner._run_single_task(
                        target, task, dataset, cancellation_token
                    )
                    results.add_result(task_result)

                    # Save individual result
                    await self._store.save_eval_result(
                        eval_run_id, task_result
                    )

                    completed += 1
                    await self._store.update_eval_run_progress(
                        eval_run_id, completed_tasks=completed
                    )

            if cancellation_token.is_cancelled():
                # Idempotent with cancel_eval_run; also covers shutdown(),
                # which cancels tokens without writing the DB status.
                await self._store.update_eval_run_progress(
                    eval_run_id,
                    status="cancelled",
                    completed_at=datetime.now(timezone.utc),
                )
                return

            # Save full JSON file
            saved_path = results.save()

            # Mark complete
            await self._store.update_eval_run_progress(
                eval_run_id,
                status="completed",
                file_path=str(saved_path),
                completed_at=datetime.now(timezone.utc),
            )

        except asyncio.CancelledError:
            await self._store.update_eval_run_progress(
                eval_run_id,
                status="cancelled",
                completed_at=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.exception(f"Eval run {eval_run_id} failed")
            await self._store.update_eval_run_progress(
                eval_run_id,
                status="error",
                error_message=str(e),
                completed_at=datetime.now(timezone.utc),
            )

    async def shutdown(self) -> None:
        """Cancel all active eval jobs and wait for their tasks to finish."""
        for token in list(self._cancellation_tokens.values()):
            token.cancel()
        tasks = list(self._active_jobs.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _create_judge(self, judge_config: Optional[Dict[str, Any]]):
        """Create a judge from config dict."""
        from ..eval.judges import LLMEvalJudge

        if not judge_config:
            # Default: use a basic LLM judge
            from ..eval._config import AgentConfig

            config = AgentConfig(name="judge")
            model_client = config._create_model_client()
            return LLMEvalJudge(client=model_client)

        judge_type = judge_config.get("type", "llm")
        if judge_type == "llm":
            from ..eval._config import AgentConfig

            model_config = judge_config.get("model", {})
            config = AgentConfig(name="judge", **model_config)
            model_client = config._create_model_client()
            criteria = judge_config.get("criteria")
            return LLMEvalJudge(
                client=model_client,
                default_criteria=criteria,
            )

        raise ValueError(f"Unknown judge type: {judge_type}")

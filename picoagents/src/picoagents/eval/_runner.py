"""
Evaluation runner - orchestrates evaluation execution.

This module provides EvalRunner which executes tasks against targets,
scores results with judges, and collects metrics.
"""

import asyncio
import copy
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Union

from ..agents._base import BaseAgent
from .._cancellation_token import CancellationToken
from ..types import EvalScore, RunTrajectory, Task, Usage
from ._base import EvalJudge, Target
from ._config import AgentConfig
from ._dataset import Dataset
from ._middleware import RunMiddleware
from ._results import EvalResults, TaskResult
from ._targets import AgentEvalTarget, PicoAgentTarget

#: Anything that can be passed to ``EvalRunner.run()`` as a target.
#: - ``Target``: used as-is
#: - ``AgentConfig``: wrapped in ``PicoAgentTarget`` (fresh agent per task)
#: - ``BaseAgent``: wrapped in ``AgentEvalTarget`` (reuses instance)
Runnable = Union[Target, AgentConfig, BaseAgent]


logger = logging.getLogger(__name__)


class EvalRunner:
    """Runs evaluation tasks against targets and scores the results.

    Supports two modes:
    - Simple: evaluate(target, tasks) -> List[EvalScore]
    - Full: run(dataset, targets) -> EvalResults

    ``run()`` accepts any mix of Target, AgentConfig, or BaseAgent
    instances — they are auto-resolved to the appropriate Target wrapper.

    Example:
        >>> runner = EvalRunner(judge=my_judge)
        >>> results = await runner.run(
        ...     dataset=my_dataset,
        ...     targets=[agent, config, custom_target],
        ... )
    """

    def __init__(
        self,
        judge: EvalJudge,
        parallel_tasks: bool = False,
        parallel_targets: bool = False,
        max_concurrency: Optional[int] = 8,
    ):
        """Initialize evaluation runner.

        Args:
            judge: Judge to score task outputs
            parallel_tasks: Run tasks in parallel (default: False for fair comparison)
            parallel_targets: Run targets in parallel (default: False)
            max_concurrency: Cap on tasks in flight when parallel_tasks is set.
                Unbounded parallelism trips provider rate limits, and a rate-limited
                judge call returns a neutral score rather than an error, which
                silently corrupts results. None disables the cap.
        """
        self.judge = judge
        self.parallel_tasks = parallel_tasks
        self.parallel_targets = parallel_targets
        self.max_concurrency = max_concurrency

    def _new_gate(self):
        """A fresh semaphore for one gather, or None when uncapped.

        Must be created per call: a semaphore is bound to the event loop that
        created it, and this runner is reused across loops (the GEPA adapter
        drives it with asyncio.run from a worker thread).
        """
        return asyncio.Semaphore(self.max_concurrency) if self.max_concurrency else None

    @staticmethod
    async def _bounded(gate, coro_fn):
        if gate is None:
            return await coro_fn()
        async with gate:
            return await coro_fn()

    # --- Simple mode (backward compatible) ---

    async def evaluate(
        self,
        target: Target,
        tasks: List[Task],
        criteria: Optional[List[str]] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> List[EvalScore]:
        """Evaluate a target on multiple tasks (simple mode).

        Args:
            target: The evaluation target to test
            tasks: List of tasks to evaluate
            criteria: Optional evaluation criteria
            cancellation_token: Optional token to cancel evaluation

        Returns:
            List of evaluation scores, one per task
        """
        if self.parallel_tasks:
            gate = self._new_gate()
            eval_tasks = [
                self._bounded(
                    gate,
                    lambda t=task: self._evaluate_single(
                        target, t, criteria, cancellation_token))
                for task in tasks
            ]
            return await asyncio.gather(*eval_tasks)
        else:
            scores = []
            for task in tasks:
                if cancellation_token and cancellation_token.is_cancelled():
                    break
                score = await self._evaluate_single(
                    target, task, criteria, cancellation_token
                )
                scores.append(score)
            return scores

    async def _evaluate_single(
        self,
        target: Target,
        task: Task,
        criteria: Optional[List[str]] = None,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> EvalScore:
        """Evaluate a single task (simple mode)."""
        try:
            trajectory = await target.run(task, cancellation_token)
            score = await self.judge.score(trajectory, criteria, cancellation_token)
            return score

        except Exception as e:
            failed_trajectory = RunTrajectory(
                task=task,
                messages=[],
                success=False,
                error=str(e),
                usage=Usage(
                    duration_ms=0, llm_calls=0, tokens_input=0, tokens_output=0
                ),
                metadata={"error": str(e)},
            )

            return EvalScore(
                overall=0.0,
                dimensions={dim: 0.0 for dim in (criteria or ["accuracy"])},
                reasoning={
                    dim: f"Execution failed: {str(e)}"
                    for dim in (criteria or ["accuracy"])
                },
                trajectory=failed_trajectory,
                metadata={"error": str(e), "judge": self.judge.name},
            )

    # --- Full mode (dataset + multiple targets -> EvalResults) ---

    @staticmethod
    def _resolve_target(item: Runnable) -> Target:
        """Convert a Runnable to a Target.

        - Target: returned as-is
        - AgentConfig: wrapped in PicoAgentTarget (fresh agent per task)
        - BaseAgent: wrapped in AgentEvalTarget (reuses instance)
        """
        if isinstance(item, Target):
            return item
        if isinstance(item, AgentConfig):
            return PicoAgentTarget(item)
        if isinstance(item, BaseAgent):
            return AgentEvalTarget(item)
        raise TypeError(
            f"Expected Target, AgentConfig, or BaseAgent, got {type(item).__name__}"
        )

    async def run(
        self,
        dataset: Dataset,
        targets: Sequence[Runnable],
        task_filter: Optional[Callable[[Task], bool]] = None,
        cancellation_token: Optional[CancellationToken] = None,
        persist: bool = False,
    ) -> EvalResults:
        """Execute full evaluation of dataset against multiple targets.

        Each task runs in an isolated temp directory so targets don't
        share filesystem state.

        Args:
            dataset: Dataset of tasks to run
            targets: Targets to evaluate — accepts any mix of
                Target, AgentConfig, or BaseAgent instances
            task_filter: Optional filter to select subset of tasks
            cancellation_token: For cancellation support
            persist: If True, save results to ~/.picoagents/ (DB
                index + JSON file with full eval data)

        Returns:
            EvalResults with full results matrix
        """
        resolved_targets = [self._resolve_target(t) for t in targets]
        tasks = list(dataset.tasks)
        if task_filter:
            tasks = [t for t in tasks if task_filter(t)]

        results = EvalResults(
            dataset_name=dataset.name,
            dataset_version=dataset.version,
        )

        if self.parallel_targets:
            target_coros = [
                self._run_target(target, tasks, dataset, cancellation_token)
                for target in resolved_targets
            ]
            target_results = await asyncio.gather(*target_coros, return_exceptions=True)

            for target, target_result in zip(resolved_targets, target_results):
                if isinstance(target_result, Exception):
                    continue
                for task_result in target_result:
                    results.add_result(task_result)
        else:
            for target in resolved_targets:
                if cancellation_token and cancellation_token.is_cancelled():
                    break

                task_results = await self._run_target(
                    target, tasks, dataset, cancellation_token
                )
                for task_result in task_results:
                    results.add_result(task_result)

        if persist:
            try:
                # Save JSON file via existing method
                file_path = results.save()

                # Index in DB
                from ..store import get_default_store

                store = get_default_store()
                await store.save_eval_run_from_results(
                    results, file_path=str(file_path)
                )
            except Exception as e:
                import logging

                logging.getLogger(__name__).error(
                    f"Failed to persist eval results: {e}", exc_info=True
                )

        return results

    async def _run_target(
        self,
        target: Target,
        tasks: List[Task],
        dataset: Dataset,
        cancellation_token: Optional[CancellationToken],
    ) -> List[TaskResult]:
        """Run all tasks for a single target."""
        results = []

        if self.parallel_tasks:
            gate = self._new_gate()
            task_coroutines = [
                self._bounded(
                    gate,
                    lambda t=task: self._run_single_task(
                        target, t, dataset, cancellation_token))
                for task in tasks
            ]
            gathered = await asyncio.gather(*task_coroutines, return_exceptions=True)
            # A crashed task must stay in the matrix as a failure. Dropping it
            # let a target that errored on half its work outscore one that
            # completed everything.
            results = []
            for task, outcome in zip(tasks, gathered):
                if isinstance(outcome, TaskResult):
                    results.append(outcome)
                elif isinstance(outcome, BaseException):
                    logger.error(
                        f"Task {task.id or task.name!r} failed on target "
                        f"{target.name!r}: {outcome}",
                        exc_info=outcome,
                    )
                    results.append(self._failed_task_result(target, task, outcome))
        else:
            for task in tasks:
                if cancellation_token and cancellation_token.is_cancelled():
                    break

                result = await self._run_single_task(
                    target, task, dataset, cancellation_token
                )
                results.append(result)

        return results

    def _failed_task_result(
        self, target: Any, task: Any, error: BaseException
    ) -> TaskResult:
        """A crashed task recorded as a scored failure, not silently dropped."""
        message = f"{type(error).__name__}: {error}"
        trajectory = RunTrajectory(
            task=task, messages=[], success=False, error=message
        )
        return TaskResult(
            task_id=task.id or task.name,
            target_name=target.name,
            trajectory=trajectory,
            score=EvalScore(
                overall=0.0,
                dimensions={},
                reasoning={"error": message},
                trajectory=trajectory,
                metadata={"task_failed": True},
            ),
        )

    async def _run_single_task(
        self,
        target: Target,
        task: Task,
        dataset: Dataset,
        cancellation_token: Optional[CancellationToken],
    ) -> TaskResult:
        """Run a single task and score it.

        When a PicoAgentTarget has no explicit workspace, an isolated temp
        directory is created per task so targets don't share filesystem
        state.  When the config already specifies a workspace, it is
        respected as-is (no temp dir, no mutation).
        """
        middleware = RunMiddleware()
        task_id = task.id or task.name

        # Only create a temp workspace when the target has none set
        needs_temp = (
            isinstance(target, PicoAgentTarget)
            and target.config.workspace is None
        )
        task_workspace = None
        if needs_temp:
            task_workspace = Path(tempfile.mkdtemp(
                prefix=f"eval_{target.name}_{task_id}_"
            ))

        try:
            if isinstance(target, PicoAgentTarget):
                if needs_temp:
                    # Copy config with temp workspace (parallel-safe,
                    # never mutates the original target)
                    task_config = copy.copy(target.config)
                    task_config.workspace = str(task_workspace)
                    task_target = PicoAgentTarget(
                        task_config,
                        middlewares=target.middlewares,
                    )
                else:
                    task_target = target

                trajectory = await task_target.run(
                    task,
                    cancellation_token=cancellation_token,
                    middlewares=[middleware],
                )
            elif isinstance(target, AgentEvalTarget):
                # Inject middleware for metrics collection
                target.agent.middleware_chain.add(middleware)
                try:
                    trajectory = await target.run(
                        task,
                        cancellation_token=cancellation_token,
                    )
                finally:
                    target.agent.middleware_chain.middlewares.remove(middleware)
            else:
                trajectory = await target.run(
                    task,
                    cancellation_token=cancellation_token,
                )
        finally:
            if task_workspace is not None:
                shutil.rmtree(task_workspace, ignore_errors=True)

        # Score with judge
        criteria = task.eval_criteria or dataset.default_eval_criteria
        score = await self._score_trajectory(trajectory, criteria, cancellation_token)

        # Get metrics from middleware
        metrics = middleware.get_metrics()

        # Build task result
        return TaskResult(
            task_id=task_id,
            target_name=target.name,
            trajectory=trajectory,
            score=score,
            files_read=metrics.get("file_reads", {}),
            unique_files=metrics.get("unique_files", 0),
            duplicate_reads=metrics.get("duplicate_reads", 0),
            compaction_events=metrics.get("compaction_events", 0),
            tokens_saved=metrics.get("tokens_saved", 0),
            metrics=metrics,
        )

    async def _score_trajectory(
        self,
        trajectory: RunTrajectory,
        criteria: List[str],
        cancellation_token: Optional[CancellationToken],
    ) -> EvalScore:
        """Score trajectory with judge."""
        try:
            return await self.judge.score(
                trajectory,
                criteria=criteria,
                cancellation_token=cancellation_token,
            )
        except Exception as e:
            return EvalScore(
                overall=0.0,
                dimensions={c: 0.0 for c in criteria},
                reasoning={c: f"Judge error: {str(e)}" for c in criteria},
                trajectory=trajectory,
                metadata={"judge_error": str(e)},
            )

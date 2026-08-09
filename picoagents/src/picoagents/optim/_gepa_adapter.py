"""Run the real GEPA library against picoagents, with faithful cost tracking.

Unlike ``ReflectiveParetoOptimizer`` (a teaching distillation), this drives the
actual ``gepa`` package (Agrawal et al., arXiv:2507.19457) so we can observe and
measure its real behaviour: minibatch subsampling, Pareto tracking, round-robin
component selection, merge/crossover, and budget/stall stopping.

Cost is tracked across all three sources into a single ``CostLog``:
- agent + judge: accumulated inside ``PicoGepaAdapter.evaluate`` (we run the
  picoagents agent and our judge there, exactly like ``BaseOptimizer._eval``).
- reflection: accumulated in a wrapper around the reflection LM we hand to GEPA.

``gepa`` is an OPTIONAL dependency. Importing this module never fails if it is
absent; ``optimize_with_gepa`` raises a clear error only when actually called.
gepa is synchronous, so we run it in a worker thread and drive picoagents' async
calls with ``asyncio.run`` inside that thread.
"""

import asyncio
from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional

from ..eval import AgentConfig, Dataset, EvalRunner, PicoAgentTarget
from ..llm import BaseChatCompletionClient
from ..messages import UserMessage
from ..types import Task, Usage
from ._base import CostLog
from ._spec import Edit, InstructionTunable, Operation, OptimizationSpec

try:  # gepa is an optional dependency
    import gepa as _gepa

    GEPA_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in the no-gepa environment
    _gepa = None
    GEPA_AVAILABLE = False


def _require_gepa() -> None:
    if not GEPA_AVAILABLE:
        raise ImportError(
            "The 'gepa' package is required for optimize_with_gepa(). "
            "Install it with `pip install gepa` (or `pip install -e` a local clone). "
            "The rest of picoagents.optim works without it."
        )


class _CostTrackingReflectionLM:
    """Wraps a picoagents client as a GEPA reflection LM, counting tokens.

    GEPA calls this synchronously as ``lm(prompt) -> str``. We drive the async
    client with ``asyncio.run`` (safe: GEPA runs in a worker thread with no loop)
    and accumulate usage into ``cost.reflection``. The ``total_cost`` attribute
    stops GEPA from re-wrapping this in its own TrackingLM.
    """

    total_cost = 0.0

    def __init__(self, client: BaseChatCompletionClient, cost: CostLog):
        self._client = client
        self._cost = cost

    def __call__(self, prompt: Any) -> str:
        if isinstance(prompt, str):
            messages = [UserMessage(content=prompt, source="gepa")]
        else:  # list of {role, content} dicts
            messages = [UserMessage(content=m.get("content", ""), source="gepa") for m in prompt]
        result = asyncio.run(self._client.create(messages))
        if result.usage is not None:
            self._cost.reflection = self._cost.reflection + result.usage
        return result.message.content or ""


class PicoGepaAdapter:
    """GEPA adapter that executes picoagents ``AgentConfig`` candidates.

    A GEPA candidate is a ``dict[str, str]`` of component name -> text. We map it
    back onto the base config via REWRITE edits through the OptimizationSpec, run
    each task with the picoagents agent + judge, and return per-example scores and
    trajectories for GEPA's reflection step.
    """

    # GEPA's default proposer checks ``adapter.propose_new_texts is not None``;
    # setting it None routes GEPA through its reflection_lm + make_reflective_dataset.
    propose_new_texts = None

    def __init__(
        self,
        base_config: AgentConfig,
        spec: OptimizationSpec,
        runner: EvalRunner,
        cost: CostLog,
    ):
        self.base_config = base_config
        self.spec = spec
        self.runner = runner
        self.cost = cost
        self.eval_count = 0  # task rollouts - same unit as BaseOptimizer.eval_count
        self.history: List[Dict[str, Any]] = []  # per-evaluate record for analysis
        # component name -> kind, so we can apply text back with the right tunable
        self._kind_by_name = {c.name: c.kind for c in spec.read(base_config)}

    def config_from_candidate(self, candidate: Dict[str, str]) -> AgentConfig:
        edits = [
            Edit(Operation.REWRITE, self._kind_by_name.get(name, "instructions"), name, value=text)
            for name, text in candidate.items()
        ]
        cfg = self.spec.apply(self.base_config, edits)
        return replace(cfg, name=f"gepa-{abs(hash(tuple(sorted(candidate.items())))) % 100000}")

    def evaluate(self, batch: List[Task], candidate: Dict[str, str], capture_traces: bool = False):
        from gepa.core.adapter import EvaluationBatch

        cfg = self.config_from_candidate(candidate)
        self.eval_count += len(batch)
        scores = asyncio.run(self.runner.evaluate(PicoAgentTarget(cfg), list(batch)))

        outputs: List[str] = []
        score_vals: List[float] = []
        trajectories: Optional[List[Dict[str, Any]]] = [] if capture_traces else None
        per_task: List[Dict[str, Any]] = []
        for task, s in zip(batch, scores):
            # cost: agent rollout + judge, same accounting as BaseOptimizer._eval
            if s.trajectory and s.trajectory.usage:
                self.cost.agent = self.cost.agent + s.trajectory.usage
            ju = s.metadata.get("judge_usage")
            if isinstance(ju, Usage):
                self.cost.judge = self.cost.judge + ju

            outputs.append(s.get_final_response())
            score_vals.append(s.overall)
            feedback = "; ".join(f"{k}: {v}" for k, v in s.reasoning.items()) or f"score {s.overall}"
            if trajectories is not None:
                trajectories.append({
                    "input": task.input, "output": s.get_final_response(), "feedback": feedback,
                })
            per_task.append({
                "task_id": task.id or task.name, "input": task.input,
                "response": s.get_final_response(), "overall": s.overall,
                "dimensions": s.dimensions, "reasoning": s.reasoning,
            })
        # record what GEPA evaluated, for analysis
        self.history.append({"candidate": dict(candidate), "capture_traces": capture_traces,
                             "per_task": per_task})
        return EvaluationBatch(outputs=outputs, scores=score_vals, trajectories=trajectories)

    def make_reflective_dataset(
        self, candidate: Dict[str, str], eval_batch, components_to_update: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        items = [
            {"Inputs": t["input"], "Generated Outputs": t["output"], "Feedback": t["feedback"]}
            for t in (eval_batch.trajectories or [])
        ]
        return {comp: items for comp in components_to_update}


@dataclass
class GepaRunResult:
    """Result of a real-GEPA run over picoagents."""

    best: AgentConfig
    cost: CostLog
    eval_count: int  # task rollouts spent - same unit as OptimizationResult.eval_count
    num_candidates: int
    history: List[Dict[str, Any]]  # per-evaluate records (candidate + per-task responses/scores)
    raw: Any  # the underlying gepa GEPAResult


async def optimize_with_gepa(
    base_config: AgentConfig,
    dataset: Dataset,
    reflection_client: BaseChatCompletionClient,
    runner: EvalRunner,
    *,
    spec: Optional[OptimizationSpec] = None,
    budget: int = 60,
    candidate_selection_strategy: str = "pareto",
    module_selector: str = "round_robin",
    use_merge: bool = False,
    max_merge_invocations: int = 5,
    reflection_minibatch_size: int = 3,
    perfect_score: float = 10.0,
    **gepa_kwargs: Any,
) -> GepaRunResult:
    """Optimize a picoagents agent with the real GEPA library.

    Args mirror GEPA's knobs so its design choices can be ablated: candidate
    selection (pareto vs current_best vs ...), component selection, merge on/off,
    minibatch size, and the metric-call budget. Cost lands in the returned CostLog.
    """
    _require_gepa()
    spec = spec or OptimizationSpec([InstructionTunable()])
    tasks = list(dataset.tasks)

    cost = CostLog()
    reflection_lm = _CostTrackingReflectionLM(reflection_client, cost)
    adapter = PicoGepaAdapter(base_config, spec, runner, cost)

    seed_candidate = {c.name: c.value for c in spec.read(base_config)}

    result = await asyncio.to_thread(
        _gepa.optimize,
        seed_candidate=seed_candidate,
        trainset=tasks,
        valset=tasks,
        adapter=adapter,
        reflection_lm=reflection_lm,
        max_metric_calls=budget,
        candidate_selection_strategy=candidate_selection_strategy,
        module_selector=module_selector,
        use_merge=use_merge,
        max_merge_invocations=max_merge_invocations,
        reflection_minibatch_size=reflection_minibatch_size,
        perfect_score=perfect_score,
        **gepa_kwargs,
    )

    best = adapter.config_from_candidate(
        result.best_candidate if isinstance(result.best_candidate, dict)
        else {next(iter(seed_candidate)): result.best_candidate}
    )
    return GepaRunResult(
        best=best, cost=cost, eval_count=adapter.eval_count,
        num_candidates=result.num_candidates, history=adapter.history, raw=result,
    )

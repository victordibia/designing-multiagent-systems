"""The universal optimization loop.

Every optimizer here is the same skeleton - propose -> run -> evaluate -> select -
differing only in three overridable knobs:

- ``propose``        : what to mutate and what signal drives it
- ``select``         : how candidates are kept (greedy / Pareto / ...)
- ``select_parents`` : which candidate(s) to mutate next

Evaluation reuses the picoagents ``eval`` module unchanged: every proposed
candidate is *executed* on the tasks and scored by the judge. Optimization is
active/online - you cannot know a candidate is better without running it.

Cost control follows GEPA's two-stage evaluation: an optional cheap minibatch
acceptance gate, with a full evaluation only on candidates that clear it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..eval import AgentConfig, Dataset, EvalRunner, PicoAgentTarget
from ..types import EvalScore, Task, Usage
from ._spec import OptimizationSpec


def _task_key(score: EvalScore) -> str:
    """Stable per-task identifier from a scored trajectory."""
    if score.trajectory and score.trajectory.task:
        t = score.trajectory.task
        return t.id or t.name
    return ""


def _zero_usage() -> Usage:
    return Usage(duration_ms=0, llm_calls=0, tokens_input=0, tokens_output=0)


@dataclass
class CostLog:
    """Token (and USD, when available) cost of an optimization run, by source.

    The three sources of LLM cost in an optimization job:
    - ``agent``: running the agent on tasks (rollouts) - usually the dominant cost.
    - ``judge``: scoring each run with the eval judge - recurring, paid every eval.
    - ``reflection``: the proposer/reflector calls that generate candidates - cheap,
      one call per proposal.
    """

    agent: Usage = field(default_factory=_zero_usage)
    judge: Usage = field(default_factory=_zero_usage)
    reflection: Usage = field(default_factory=_zero_usage)

    @property
    def total(self) -> Usage:
        return self.agent + self.judge + self.reflection

    def to_dict(self) -> Dict[str, Dict[str, Optional[float]]]:
        def row(u: Usage) -> Dict[str, Optional[float]]:
            return {
                "tokens_input": u.tokens_input,
                "tokens_output": u.tokens_output,
                "tokens_total": u.tokens_input + u.tokens_output,
                "llm_calls": u.llm_calls,
                "usd": u.cost_estimate,
            }
        out = {
            "agent": row(self.agent),
            "judge": row(self.judge),
            "reflection": row(self.reflection),
            "total": row(self.total),
        }
        # Tokens are the complete metric; USD is best-effort (some clients don't
        # estimate cost). Report a total USD only if every source that actually
        # ran provided one - otherwise the total would silently understate cost.
        # A source that made no calls contributes $0, not "unknown".
        def source_usd(u: Usage) -> Optional[float]:
            if u.cost_estimate is not None:
                return u.cost_estimate
            return 0.0 if u.llm_calls == 0 else None  # no work -> $0; worked but unknown -> None
        per_source_usd = [source_usd(self.agent), source_usd(self.judge), source_usd(self.reflection)]
        out["total"]["usd"] = (
            sum(v for v in per_source_usd if v is not None)
            if all(v is not None for v in per_source_usd)
            else None
        )
        return out

    def summary(self) -> str:
        d = self.to_dict()
        lines = [f"{'source':12s} {'tokens':>12s} {'llm_calls':>10s} {'usd':>10s}"]
        for src in ("agent", "judge", "reflection", "total"):
            r = d[src]
            usd = f"${r['usd']:.4f}" if r["usd"] is not None else "-"
            lines.append(f"{src:12s} {r['tokens_total']:12,d} {r['llm_calls']:10d} {usd:>10s}")
        return "\n".join(lines)


@dataclass
class Candidate:
    """One configuration under optimization, with its full-eval scores."""

    config: AgentConfig
    scores: List[EvalScore] = field(default_factory=list)  # one per task (full eval)
    parent: Optional[str] = None
    rationale: str = ""

    @property
    def avg(self) -> float:
        return sum(s.overall for s in self.scores) / len(self.scores) if self.scores else 0.0

    @property
    def task_scores(self) -> Dict[str, float]:
        return {_task_key(s): s.overall for s in self.scores if _task_key(s)}


@dataclass
class OptimizationResult:
    """Outcome of an optimization run."""

    best: AgentConfig
    pool: List[Candidate]
    rounds: int
    eval_count: int  # total task rollouts spent (the cost story)
    cost: "CostLog" = field(default_factory=lambda: CostLog())  # tokens/USD by source

    @property
    def best_candidate(self) -> Candidate:
        return max(self.pool, key=lambda c: c.avg)


class BaseOptimizer(ABC):
    """Template-method optimizer. Subclasses override ``propose`` (and optionally
    ``select`` / ``select_parents``)."""

    def __init__(
        self,
        runner: EvalRunner,
        dataset: Dataset,
        spec: Optional[OptimizationSpec] = None,
        *,
        rounds: int = 5,
        candidates_per_round: int = 1,
        minibatch: Optional[int] = None,
        beam: int = 4,
        budget: Optional[int] = None,
    ):
        """
        Args:
            runner: Eval runner (carries the judge). Reused verbatim for scoring.
            dataset: Tasks to optimize against.
            spec: Optimizable surface. Defaults to instructions-only.
            rounds: Number of propose/evaluate rounds.
            candidates_per_round: Proposals generated per round.
            minibatch: If set, gate candidates on a cheap minibatch of this many
                tasks before paying for a full eval (GEPA-style). None = full eval
                every candidate (simplest baseline).
            beam: Max candidates kept by the default greedy ``select``.
            budget: Optional cap on total task rollouts. Optimization stops once
                ``eval_count`` reaches it. Use to compare methods under an equal
                cost budget (the fair way to compare optimizers).
        """
        self.runner = runner
        self.dataset = dataset
        self.tasks: List[Task] = list(dataset.tasks)
        self.spec = spec or OptimizationSpec()
        self.rounds = rounds
        self.candidates_per_round = candidates_per_round
        self.minibatch = minibatch
        self.beam = beam
        self.budget = budget
        self.eval_count = 0  # task rollouts spent across the run
        self.cost = CostLog()  # tokens/USD by source (agent / judge / reflection)

    async def optimize(self, seed: AgentConfig) -> OptimizationResult:
        seed_cand = Candidate(seed, await self._eval_full(seed), parent=None, rationale="seed")
        pool: List[Candidate] = [seed_cand]

        for _ in range(self.rounds):
            if self._budget_exhausted():
                break
            parents = self.select_parents(pool)
            proposals = await self.propose(parents, pool)
            for cfg, rationale in proposals:
                if self._budget_exhausted():
                    break
                parent = parents[0]
                if self._is_noop(parent.config, cfg):
                    continue  # proposed edits fell outside the spec - skip, don't pay to eval
                if not await self._passes_gate(parent, cfg):
                    continue
                cand = Candidate(
                    cfg, await self._eval_full(cfg), parent=parent.config.name, rationale=rationale
                )
                pool.append(cand)
            pool = self.select(pool)

        return OptimizationResult(
            best=max(pool, key=lambda c: c.avg).config,
            pool=pool,
            rounds=self.rounds,
            eval_count=self.eval_count,
            cost=self.cost,
        )

    # --- evaluation (reuses eval module; this is where cost is spent) ---

    async def _eval(self, config: AgentConfig, tasks: List[Task]) -> List[EvalScore]:
        scores = await self.runner.evaluate(PicoAgentTarget(config), tasks)
        self.eval_count += len(tasks)
        for s in scores:
            if s.trajectory and s.trajectory.usage:
                self.cost.agent = self.cost.agent + s.trajectory.usage  # rollout cost
            judge_usage = s.metadata.get("judge_usage")
            if isinstance(judge_usage, Usage):
                self.cost.judge = self.cost.judge + judge_usage  # eval cost
        return scores

    def _track_reflection(self, usage: Optional[Usage]) -> None:
        """Subclasses call this after each proposer/reflector LLM call."""
        if usage is not None:
            self.cost.reflection = self.cost.reflection + usage

    def _budget_exhausted(self) -> bool:
        """True once the rollout budget (if any) is spent."""
        return self.budget is not None and self.eval_count >= self.budget

    async def _eval_full(self, config: AgentConfig) -> List[EvalScore]:
        return await self._eval(config, self.tasks)

    @staticmethod
    def _is_noop(parent_cfg: AgentConfig, cfg: AgentConfig) -> bool:
        """True when a proposal changed nothing (e.g. edits fell outside the spec)."""
        a, b = parent_cfg.to_dict(), cfg.to_dict()
        a.pop("name", None)
        b.pop("name", None)
        return a == b

    async def _passes_gate(self, parent: Candidate, cfg: AgentConfig) -> bool:
        """Cheap minibatch acceptance gate. True when no gate is configured."""
        if not self.minibatch or self.minibatch >= len(self.tasks):
            return True
        mb = self.tasks[: self.minibatch]
        cand_scores = await self._eval(cfg, mb)
        cand_sum = sum(s.overall for s in cand_scores)
        parent_lookup = parent.task_scores
        parent_sum = sum(parent_lookup.get(t.id or t.name, 0.0) for t in mb)
        return cand_sum > parent_sum

    # --- the three knobs (override in subclasses) ---

    @abstractmethod
    async def propose(
        self, parents: List[Candidate], pool: List[Candidate]
    ) -> List[Tuple[AgentConfig, str]]:
        """Return a list of ``(AgentConfig, rationale)`` proposals."""
        ...

    def select(self, pool: List[Candidate]) -> List[Candidate]:
        """Default: greedy top-``beam`` by average score."""
        return sorted(pool, key=lambda c: c.avg, reverse=True)[: self.beam]

    def select_parents(self, pool: List[Candidate]) -> List[Candidate]:
        """Default: mutate the best candidate so far."""
        return [max(pool, key=lambda c: c.avg)]

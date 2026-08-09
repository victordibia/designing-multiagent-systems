"""Offline tests for the agent optimization module (no network/LLM).

The optimization loop is exercised with a stub that overrides ``_eval`` to return
synthetic scores, so the loop mechanics (improvement, eval_count, no-op skipping,
budget stop, cost log) are tested deterministically without any LLM calls.
"""

import dataclasses

import pytest

from picoagents.eval import AgentConfig, Dataset
from picoagents.optim import (
    BaseOptimizer,
    CatalogEntry,
    CostLog,
    Edit,
    InstructionTunable,
    Operation,
    OptimizationSpec,
    ReflectiveParetoOptimizer,
    SkillTunable,
    ToolSelectionTunable,
    pareto_frontier,
)
from picoagents.optim._base import Candidate
from picoagents.types import EvalScore, RunTrajectory, Task, Usage


# --- helpers ---------------------------------------------------------------


def _tasks(n):
    return [Task(name=f"t{i}", input=f"task {i}", id=f"t{i}") for i in range(n)]


def _score(task, value, tokens=10):
    traj = RunTrajectory(
        task=task, messages=[], success=True,
        usage=Usage(duration_ms=1, llm_calls=1, tokens_input=tokens, tokens_output=tokens),
    )
    # carry a judge_usage so cost accumulation has both agent and judge buckets
    return EvalScore(
        overall=value, dimensions={}, reasoning={}, trajectory=traj,
        metadata={"judge_usage": Usage(duration_ms=1, llm_calls=1,
                                       tokens_input=tokens, tokens_output=tokens)},
    )


class StubOptimizer(BaseOptimizer):
    """Scores a config by a synthetic function; propose appends to the prompt."""

    def __init__(self, *a, score_fn=None, **k):
        super().__init__(*a, **k)
        self._n = 0
        self._score_fn = score_fn or (lambda cfg, t: 5.0)

    async def _eval(self, config, tasks):
        self.eval_count += len(tasks)
        scores = [_score(t, self._score_fn(config, t)) for t in tasks]
        for s in scores:  # mirror BaseOptimizer._eval cost accumulation
            self.cost.agent = self.cost.agent + s.trajectory.usage
            self.cost.judge = self.cost.judge + s.metadata["judge_usage"]
        return scores

    async def propose(self, parents, pool):
        self._n += 1
        cfg = dataclasses.replace(
            parents[0].config, name=f"c{self._n}", system_prompt="x" * self._n
        )
        return [(cfg, "stub")]


class NoopOptimizer(StubOptimizer):
    async def propose(self, parents, pool):
        self._n += 1
        # only the name changes -> _is_noop should skip it
        cfg = dataclasses.replace(parents[0].config, name=f"c{self._n}")
        return [(cfg, "noop")]


# --- spec / tunables -------------------------------------------------------


def test_instruction_tunable_rewrite():
    cfg = AgentConfig(name="c", system_prompt="old")
    spec = OptimizationSpec([InstructionTunable()])
    new = spec.apply(cfg, [Edit(Operation.REWRITE, "instructions", "instructions", value="new")])
    assert new.system_prompt == "new"
    assert cfg.system_prompt == "old"  # original untouched


def test_skill_tunable_add_and_remove():
    cfg = AgentConfig(name="c", skills={"a": "body-a"})
    spec = OptimizationSpec([SkillTunable()])
    added = spec.apply(cfg, [Edit(Operation.ADD, "skill", "skill:b", value="body-b")])
    assert set(added.skills) == {"a", "b"}
    removed = spec.apply(added, [Edit(Operation.REMOVE, "skill", "skill:a")])
    assert set(removed.skills) == {"b"}


def test_tool_selection_rejects_off_catalog():
    cfg = AgentConfig(name="c", tools=["core"])
    catalog = [CatalogEntry("calculator", "math"), CatalogEntry("datetime", "time")]
    spec = OptimizationSpec([ToolSelectionTunable(catalog)])
    new = spec.apply(cfg, [
        Edit(Operation.ADD, "tool", "tools", value="calculator"),
        Edit(Operation.ADD, "tool", "tools", value="not_a_real_tool"),  # rejected
    ])
    assert "calculator" in new.tools
    assert "not_a_real_tool" not in new.tools


# --- pareto ----------------------------------------------------------------


def _cand(name, scores):
    c = Candidate(AgentConfig(name=name, system_prompt=name))
    c.scores = [_score(Task(name=f"t{i}", input="", id=f"t{i}"), s) for i, s in enumerate(scores)]
    return c


def test_pareto_excludes_dominated():
    a, b, dom = _cand("A", [10, 0, 5]), _cand("B", [0, 10, 5]), _cand("C", [1, 1, 1])
    front = {c.config.name for c in pareto_frontier([a, b, dom])}
    assert front == {"A", "B"}


def test_pareto_keeps_task_winner():
    a, b, c = _cand("A", [10, 0, 0]), _cand("B", [0, 10, 0]), _cand("C", [1, 1, 1])
    front = {x.config.name for x in pareto_frontier([a, b, c])}
    assert front == {"A", "B", "C"}  # C wins task 2


# --- loop mechanics --------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_improves_and_counts_rollouts():
    ds = Dataset(name="d", tasks=_tasks(3))
    opt = StubOptimizer(object(), ds, rounds=3, score_fn=lambda c, t: 5.0 + len(c.system_prompt), beam=20)
    res = await opt.optimize(AgentConfig(name="seed", system_prompt=""))
    assert res.eval_count == 3 * 4  # seed + 3 rounds, 3 tasks each
    assert res.best_candidate.avg >= 5.0


@pytest.mark.asyncio
async def test_noop_proposals_skipped():
    ds = Dataset(name="d", tasks=_tasks(2))
    opt = NoopOptimizer(object(), ds, rounds=5, beam=20)
    res = await opt.optimize(AgentConfig(name="seed", system_prompt="s"))
    # only the seed is ever evaluated; no-op candidates are skipped
    assert res.eval_count == 2
    assert len(res.pool) == 1


@pytest.mark.asyncio
async def test_budget_caps_rollouts():
    ds = Dataset(name="d", tasks=_tasks(4))
    opt = StubOptimizer(object(), ds, rounds=100, budget=20,
                        score_fn=lambda c, t: len(c.system_prompt))
    res = await opt.optimize(AgentConfig(name="seed", system_prompt="s"))
    assert res.eval_count == 20  # capped well before 100 rounds (~404)


@pytest.mark.asyncio
async def test_cost_log_populated_by_source():
    ds = Dataset(name="d", tasks=_tasks(2))
    opt = StubOptimizer(object(), ds, rounds=2, beam=20,
                        score_fn=lambda c, t: len(c.system_prompt))
    res = await opt.optimize(AgentConfig(name="seed", system_prompt="s"))
    assert res.cost.agent.tokens_input > 0
    assert res.cost.judge.tokens_input > 0
    total = res.cost.to_dict()["total"]
    assert total["tokens_total"] == (
        res.cost.agent.tokens_input + res.cost.agent.tokens_output
        + res.cost.judge.tokens_input + res.cost.judge.tokens_output
    )


def test_costlog_partial_usd_total_none():
    cl = CostLog()
    cl.agent = Usage(duration_ms=0, llm_calls=1, tokens_input=10, tokens_output=5)  # no usd
    cl.judge = Usage(duration_ms=0, llm_calls=1, tokens_input=10, tokens_output=5, cost_estimate=0.1)
    # total USD must be None when any source lacks an estimate
    assert cl.to_dict()["total"]["usd"] is None
    # once every source has an estimate, total sums them
    cl.agent = Usage(duration_ms=0, llm_calls=1, tokens_input=10, tokens_output=5, cost_estimate=0.05)
    assert abs(cl.to_dict()["total"]["usd"] - 0.15) < 1e-9


@pytest.mark.asyncio
async def test_reflective_pareto_runs():
    ds = Dataset(name="d", tasks=_tasks(3))

    class StubRP(ReflectiveParetoOptimizer):
        _n = 0

        async def _eval(self, config, tasks):
            self.eval_count += len(tasks)
            return [_score(t, 5.0 + len(config.system_prompt)) for t in tasks]

        async def propose(self, parents, pool):
            self._n += 1
            return [(dataclasses.replace(parents[0].config, name=f"c{self._n}",
                                         system_prompt="x" * self._n), "x")]

    opt = StubRP(object(), ds, rounds=3, reflector=None, seed=1)
    res = await opt.optimize(AgentConfig(name="seed", system_prompt="s"))
    assert res.best_candidate.avg >= 5.0
    assert res.eval_count > 0

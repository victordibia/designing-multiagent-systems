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


# --- trace -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_trace_records_gate_rejections_and_round_trips(tmp_path):
    """The trace keeps what the result drops: rejected proposals and gate scores."""
    from picoagents.optim import load_trace

    ds = Dataset(name="d", tasks=_tasks(4))
    # proposals get WORSE each round (longer prompt -> lower score) so the
    # minibatch gate rejects every one of them after the seed.
    opt = StubOptimizer(object(), ds, rounds=3, minibatch=2, beam=20,
                        score_fn=lambda c, t: 10.0 - len(c.system_prompt))
    res = await opt.optimize(AgentConfig(name="seed", system_prompt=""))

    assert len(res.pool) == 1  # every proposal rejected -> result knows nothing about them
    assert res.eval_count == 4 + 3 * 2  # seed full eval + 3 gate evals of 2 tasks

    tr = res.trace
    gates = list(tr.of_kind("gate"))
    assert [g["accepted"] for g in gates] == [False, False, False]
    assert gates[0]["task_ids"] == ["t0", "t1"]
    assert gates[0]["candidate_sum"] < gates[0]["parent_sum"]
    assert gates[0]["candidate"] == "c1" and gates[0]["parent"] == "seed"
    evals = list(tr.of_kind("eval"))
    assert [e["purpose"] for e in evals] == ["seed", "gate", "gate", "gate"]
    assert evals[0]["n_tasks"] == 4 and evals[1]["n_tasks"] == 2
    assert evals[0]["per_task"][0]["task_id"] == "t0"
    assert evals[0]["per_task"][0]["agent_usage"]["tokens_input"] == 10
    assert [e["round"] for e in tr.of_kind("select")] == [1, 2, 3]
    assert next(tr.of_kind("candidate"))["components"] == {"instructions": ""}

    # JSON round trip through save/load preserves every event
    path = tmp_path / "trace.json"
    tr.save(path)
    back = load_trace(path)
    assert back.events == tr.events
    assert res.trace.to_dict()["schema"] == 1


@pytest.mark.asyncio
async def test_trace_records_accepted_candidates_and_noops():
    ds = Dataset(name="d", tasks=_tasks(3))
    opt = StubOptimizer(object(), ds, rounds=2, minibatch=1, beam=20,
                        score_fn=lambda c, t: 5.0 + len(c.system_prompt))
    res = await opt.optimize(AgentConfig(name="seed", system_prompt=""))
    tr = res.trace
    assert [g["accepted"] for g in tr.of_kind("gate")] == [True, True]
    assert [e["purpose"] for e in tr.of_kind("eval")] == ["seed", "gate", "full", "gate", "full"]
    cands = list(tr.of_kind("candidate"))
    assert [(c["name"], c["parent"]) for c in cands] == [("seed", None), ("c1", "seed"), ("c2", "c1")]
    assert list(tr.of_kind("select"))[-1]["pool"][0] == "c2"  # greedy keeps the best first

    noop = NoopOptimizer(object(), ds, rounds=2, beam=20)
    res2 = await noop.optimize(AgentConfig(name="seed", system_prompt="s"))
    assert [n["candidate"] for n in res2.trace.of_kind("noop")] == ["c1", "c2"]
    assert not list(res2.trace.of_kind("gate"))


@pytest.mark.asyncio
async def test_trace_can_be_disabled_without_changing_the_run():
    ds = Dataset(name="d", tasks=_tasks(3))
    on = StubOptimizer(object(), ds, rounds=3, minibatch=1, score_fn=lambda c, t: 5.0 + len(c.system_prompt))
    off = StubOptimizer(object(), ds, rounds=3, minibatch=1, trace=False,
                        score_fn=lambda c, t: 5.0 + len(c.system_prompt))
    r_on = await on.optimize(AgentConfig(name="seed", system_prompt=""))
    r_off = await off.optimize(AgentConfig(name="seed", system_prompt=""))
    assert r_off.trace.events == []
    assert r_on.eval_count == r_off.eval_count
    assert r_on.best.system_prompt == r_off.best.system_prompt


@pytest.mark.asyncio
async def test_reflective_trace_keeps_prompt_and_structured_response():
    """The reflector's prompt, diagnosis and edits survive in the trace."""
    from picoagents.messages import AssistantMessage
    from picoagents.optim import ReflectiveOptimizer
    from picoagents.optim._reflective import _EditOut, _ReflectionOut
    from picoagents.types import ChatCompletionResult

    class FakeReflector:
        def __init__(self):
            self.calls = []

        async def create(self, messages, output_format=None, **kw):
            self.calls.append(messages)
            out = _ReflectionOut(
                diagnosis="replies lack the ticket reference",
                edits=[_EditOut(op="rewrite", kind="instructions", name="instructions",
                                value="Always include TKT-######.", rationale="judge asked for it")],
            )
            return ChatCompletionResult(
                message=AssistantMessage(content=out.model_dump_json(), source="fake"),
                usage=Usage(duration_ms=3, llm_calls=1, tokens_input=50, tokens_output=20),
                model="fake-model", finish_reason="stop", structured_output=out,
            )

    class StubReflective(ReflectiveOptimizer):
        async def _eval(self, config, tasks):
            self.eval_count += len(tasks)
            return [_score(t, 10.0 if "TKT" in config.system_prompt else 2.0) for t in tasks]

    ds = Dataset(name="d", tasks=_tasks(2))
    opt = StubReflective(object(), ds, rounds=1, reflector=FakeReflector())
    res = await opt.optimize(AgentConfig(name="seed", system_prompt="Help the customer."))

    assert res.best.system_prompt == "Always include TKT-######."
    props = list(res.trace.of_kind("proposal"))
    assert len(props) == 1
    p = props[0]
    assert p["stage"] == "reflect" and p["parent"] == "seed" and p["candidate"] == "seed#1"
    assert p["messages"][0]["role"] == "system"
    assert "Failing examples" in p["messages"][1]["content"]
    assert "Help the customer." in p["messages"][1]["content"]
    assert p["diagnosis"] == "replies lack the ticket reference"
    assert p["edits"][0]["value"] == "Always include TKT-######."
    assert p["edits"][0]["rationale"] == "judge asked for it"
    assert p["components"] == {"instructions": "Always include TKT-######."}
    assert p["usage"]["tokens_input"] == 50 and p["model"] == "fake-model"
    assert [s["task_id"] for s in p["shown"]] == ["t0", "t1"]
    assert res.cost.reflection.tokens_input == 50  # cost accounting unchanged
    # the whole thing serializes
    import json
    json.loads(res.trace.to_json())

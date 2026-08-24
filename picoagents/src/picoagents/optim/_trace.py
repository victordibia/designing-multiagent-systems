"""Optimization trace: a replayable record of everything an optimizer did.

An optimization run is a sequence of decisions - which candidate to mutate, what
the proposer was shown and what it wrote, which proposals the minibatch gate
rejected and why, what every evaluation scored on every task, and what survived
selection. ``OptimizationResult`` keeps only the survivors; the trace keeps the
decisions, so a run can be audited or replayed step by step after the fact.

The trace is strictly observational: recording it never changes the number of
evaluations, the proposals, or the selection. Every event is a JSON-safe dict
with a ``kind``, the ``round`` it happened in (0 = seed), and a monotonic ``seq``.

Event kinds emitted by ``BaseOptimizer`` and its subclasses:

- ``eval``      one evaluation of one config on a batch of tasks, with per-task
                records (``purpose`` is ``seed`` | ``gate`` | ``full``)
- ``parents``   which candidates were chosen to mutate this round
- ``proposal``  one proposer/reflector LLM call: the messages sent, the raw and
                structured response, and the candidate it produced
- ``noop``      a proposal that changed nothing and was skipped unpaid
- ``gate``      the minibatch acceptance decision, with both sides' scores
- ``candidate`` a candidate that cleared the gate and was fully evaluated
- ``select``    the pool after selection (for Pareto, the frontier)

The GEPA adapter emits ``gepa:*`` events mirroring the library's callback
protocol, plus a final ``gepa:result`` carrying ``GEPAResult.to_dict()``.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Union

from ..types import EvalScore, Usage

TRACE_SCHEMA = 1


def usage_dict(u: Optional[Usage]) -> Optional[Dict[str, Any]]:
    """JSON-safe view of a ``Usage``."""
    if u is None:
        return None
    return {
        "duration_ms": u.duration_ms,
        "llm_calls": u.llm_calls,
        "tokens_input": u.tokens_input,
        "tokens_output": u.tokens_output,
        "cost_estimate": u.cost_estimate,
    }


def serialize_messages(messages: Sequence[Any]) -> List[Dict[str, Any]]:
    """Compact JSON-safe view of a message sequence (type, content, tool calls)."""
    out: List[Dict[str, Any]] = []
    for msg in messages:
        row: Dict[str, Any] = {
            "type": type(msg).__name__,
            "content": getattr(msg, "content", None),
            "source": getattr(msg, "source", None),
        }
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            row["tool_calls"] = [
                {
                    "tool_name": getattr(tc, "tool_name", str(tc)),
                    "parameters": getattr(tc, "parameters", {}),
                    "call_id": getattr(tc, "call_id", None),
                }
                for tc in tool_calls
            ]
        for attr in ("tool_call_id", "tool_name", "success", "error"):
            if hasattr(msg, attr) and getattr(msg, attr) is not None:
                row[attr] = getattr(msg, attr)
        out.append(row)
    return out


def task_record(score: EvalScore, include_messages: bool = False) -> Dict[str, Any]:
    """Per-task record of one rollout + judgement, JSON-safe.

    Keeps the final response, the judge's per-criterion scores and reasoning, and
    both usages. ``judge_error`` is set when the judge failed (its ``overall`` is
    then a neutral placeholder, not a measurement). Full message transcripts are
    opt-in because they dominate file size.
    """
    traj = score.trajectory
    task = traj.task if traj else None
    judge_usage = score.metadata.get("judge_usage")
    rec: Dict[str, Any] = {
        "task_id": (task.id or task.name) if task else None,
        "input": task.input if task else None,
        "response": score.get_final_response() if traj else "",
        "overall": score.overall,
        "dimensions": dict(score.dimensions),
        "reasoning": dict(score.reasoning),
        "success": traj.success if traj else None,
        "error": traj.error if traj else None,
        "judge_error": score.metadata.get("error"),
        "agent_usage": usage_dict(traj.usage) if traj else None,
        "judge_usage": usage_dict(judge_usage) if isinstance(judge_usage, Usage) else None,
    }
    if include_messages and traj is not None:
        rec["messages"] = serialize_messages(traj.messages)
    return rec


def _no_events() -> List[Dict[str, Any]]:
    return []


@dataclass
class OptimizationTrace:
    """Ordered, JSON-serializable log of an optimization run's decisions."""

    events: List[Dict[str, Any]] = field(default_factory=_no_events)
    enabled: bool = True
    include_messages: bool = False

    def record(self, kind: str, round: int, **data: Any) -> Optional[Dict[str, Any]]:
        """Append one event. Returns the event, or None when tracing is off."""
        if not self.enabled:
            return None
        event: Dict[str, Any] = {"seq": len(self.events), "kind": kind, "round": round}
        event.update(data)
        self.events.append(event)
        return event

    def record_eval(
        self,
        round: int,
        purpose: str,
        candidate: str,
        scores: Sequence[EvalScore],
        **extra: Any,
    ) -> Optional[Dict[str, Any]]:
        """Record one evaluation of ``candidate`` with its per-task results."""
        if not self.enabled:
            return None
        per_task = [task_record(s, self.include_messages) for s in scores]
        n = len(per_task)
        avg = sum(r["overall"] for r in per_task) / n if n else 0.0
        return self.record(
            "eval", round, purpose=purpose, candidate=candidate, n_tasks=n, avg=avg,
            task_ids=[r["task_id"] for r in per_task], per_task=per_task, **extra,
        )

    def of_kind(self, kind: str) -> Iterator[Dict[str, Any]]:
        """Events of one kind, in order."""
        return (e for e in self.events if e["kind"] == kind)

    def to_dict(self) -> Dict[str, Any]:
        return {"schema": TRACE_SCHEMA, "n_events": len(self.events), "events": list(self.events)}

    def to_json(self, indent: Optional[int] = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def save(self, path: Union[str, Path]) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json())
        return p


def load_trace(path: Union[str, Path]) -> OptimizationTrace:
    """Load a trace written by ``OptimizationTrace.save``."""
    data = json.loads(Path(path).read_text())
    if data.get("schema") != TRACE_SCHEMA:
        raise ValueError(f"unsupported trace schema {data.get('schema')!r}, expected {TRACE_SCHEMA}")
    events: List[Dict[str, Any]] = [dict(e) for e in data["events"]]
    return OptimizationTrace(events=events)

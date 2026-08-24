"""Reflective optimizer - the basic reflection loop.

Diagnose the worst tasks by reading their traces and the judge's reasoning, then
ask a reflection model to propose edits to the optimizable components. This is the
skeleton GEPA extends (GEPA adds Pareto selection and richer trace feedback).

The reflector returns *structured edits* (validated against the spec), so it can
rewrite instructions, add/rewrite/remove skills, or pick tools from a catalog -
whatever the OptimizationSpec opened up.
"""

from dataclasses import replace
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from ..eval import AgentConfig
from ..llm import BaseChatCompletionClient
from ..messages import SystemMessage, UserMessage
from ..types import EvalScore
from ._base import BaseOptimizer, Candidate, task_key
from ._spec import Component, Edit, Operation, ProposalMode


class _EditOut(BaseModel):
    op: str = Field(description="One of: rewrite, add, remove")
    kind: str = Field(description="Component kind, e.g. instructions, skill, tool")
    name: str = Field(description="Component name to edit, e.g. instructions or skill:debug")
    value: str = Field(default="", description="New text (rewrite/add) or catalog name (tool)")
    rationale: str = Field(default="", description="Why this edit fixes observed failures")


class _ReflectionOut(BaseModel):
    diagnosis: str = Field(description="Brief root-cause analysis of the failures")
    edits: List[_EditOut] = Field(description="Edits to apply to the candidate")


REFLECTION_SYSTEM = (
    "You improve an AI agent's configuration. You are given the agent's current "
    "optimizable components and examples of tasks where it scored poorly, including "
    "the agent's output and the judge's reasoning. Diagnose the root cause, then "
    "propose minimal, targeted edits that would fix the failures. Only edit the "
    "components listed, and only use operations they allow. For CATALOG components "
    "choose strictly from the provided options by name."
)


class ReflectiveOptimizer(BaseOptimizer):
    """Single-parent reflection loop. Override of ``propose`` only."""

    def __init__(self, *args, reflector: BaseChatCompletionClient, weak_k: int = 3, **kwargs):
        super().__init__(*args, **kwargs)
        self.reflector = reflector
        self.weak_k = weak_k
        self._counter = 0

    async def propose(
        self, parents: List[Candidate], pool: List[Candidate]
    ) -> List[Tuple[AgentConfig, str]]:
        parent = parents[0]
        components = self.spec.read(parent.config)
        weak = sorted(parent.scores, key=lambda s: s.overall)[: self.weak_k]

        prompt = self._build_prompt(components, weak)
        result = await self.reflector.create(
            [SystemMessage(content=REFLECTION_SYSTEM, source="optim"),
             UserMessage(content=prompt, source="optim")],
            output_format=_ReflectionOut,
        )
        self._track_reflection(result.usage)
        reflection: Optional[_ReflectionOut] = result.structured_output  # type: ignore[assignment]
        messages = [
            {"role": "system", "content": REFLECTION_SYSTEM},
            {"role": "user", "content": prompt},
        ]
        shown = [
            {"task_id": task_key(s), "overall": s.overall} for s in weak
        ]  # which failing examples the reflector saw (full records are in the parent's eval)

        new_config: Optional[AgentConfig] = None
        edits: List[Edit] = []
        if reflection is not None and reflection.edits:
            edits = [e for e in (self._to_edit(e) for e in reflection.edits) if e is not None]
        if edits:
            new_config = self.spec.apply(parent.config, edits)
            new_config = replace(new_config, name=self._fresh_name(parent.config.name))

        self._record_proposal(
            parent=parent.config.name, messages=messages, response=result.message.content,
            candidate=new_config, usage=result.usage, model=result.model, stage="reflect",
            shown=shown,
            diagnosis=reflection.diagnosis if reflection else None,
            edits=[
                {"op": e.op.value, "kind": e.kind, "name": e.name, "value": e.value,
                 "rationale": e.rationale}
                for e in edits
            ],
        )
        if new_config is None or reflection is None:
            return []
        return [(new_config, reflection.diagnosis)]

    # --- helpers ---

    def _fresh_name(self, parent_name: str) -> str:
        self._counter += 1
        base = parent_name.split("#", 1)[0]
        return f"{base}#{self._counter}"

    @staticmethod
    def _to_edit(e: _EditOut):
        try:
            return Edit(
                op=Operation(e.op.strip().lower()),
                kind=e.kind.strip(),
                name=e.name.strip(),
                value=e.value,
                rationale=e.rationale,
            )
        except ValueError:
            return None  # unknown operation -> drop the edit

    def _build_prompt(self, components: List[Component], weak: List[EvalScore]) -> str:
        lines: List[str] = ["# Current optimizable components\n"]
        for c in components:
            ops = ", ".join(sorted(o.value for o in c.ops))
            lines.append(f"## {c.name}  (kind={c.kind}, mode={c.mode.value}, ops=[{ops}])")
            if c.mode is ProposalMode.CATALOG and c.catalog:
                lines.append("Choose from this catalog (by name):")
                for entry in c.catalog:
                    lines.append(f"- {entry.name}: {entry.description}")
                lines.append(f"Currently selected: {c.value or '(none)'}")
            else:
                lines.append("Current text:")
                lines.append(f"```\n{c.value}\n```")
            lines.append("")

        lines.append("# Failing examples (lowest scores)\n")
        for i, s in enumerate(weak, 1):
            task = s.trajectory.task if s.trajectory else None
            task_input = task.input if task else "(unknown)"
            reasoning = "; ".join(f"{k}: {v}" for k, v in s.reasoning.items())
            lines.append(f"## Example {i} (score {s.overall:.1f}/10)")
            lines.append(f"Task: {task_input}")
            lines.append(f"Agent output: {s.get_final_response()[:1200]}")
            lines.append(f"Judge reasoning: {reasoning[:1200]}")
            lines.append("")

        lines.append(
            "# Your task\nReturn a diagnosis and a list of edits. Prefer the smallest "
            "change that addresses the root cause across these failures."
        )
        return "\n".join(lines)

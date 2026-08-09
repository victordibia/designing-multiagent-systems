"""Optimizable surface for agent optimization.

A candidate is a base :class:`AgentConfig` plus a set of named text *components*
(instructions, skills, tool descriptions, ...). Optimizing means editing those
components. This mirrors how GEPA represents a candidate as a mapping of named
text components, generalized so each component declares what may be done to it.

Terminology follows GEPA (Agrawal et al., arXiv:2507.19457): a *component* is one
optimizable text artifact; a *candidate* is the full set. Two proposal modes:

- GENERATIVE: the proposer writes new text (instructions, skills). Maximum search
  breadth; candidates may fail to apply or fail at runtime.
- CATALOG: the proposer picks from a fixed set by name (tools, model). ``apply``
  rejects off-catalog values, so every candidate is always valid/executable.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Dict, List, Optional, Set

from ..eval import AgentConfig


class Operation(str, Enum):
    """What the optimizer may do to a component (or its group)."""

    REWRITE = "rewrite"  # change an existing artifact's text
    ADD = "add"  # propose a brand-new artifact (new skill, add a tool)
    REMOVE = "remove"  # drop one


class ProposalMode(str, Enum):
    GENERATIVE = "generative"  # reflector writes new text
    CATALOG = "catalog"  # reflector picks from a fixed set by name


@dataclass
class CatalogEntry:
    """One selectable option for a CATALOG component (e.g. an available tool)."""

    name: str
    description: str


@dataclass
class Component:
    """One optimizable text artifact within a candidate."""

    name: str  # "instructions", "skill:debugging", "tool:web_search"
    kind: str  # "instructions" | "skill" | "tool_description" | "tool" | "model"
    value: str  # current text the proposer reads
    ops: Set[Operation]  # allowed operations
    mode: ProposalMode = ProposalMode.GENERATIVE
    catalog: Optional[List[CatalogEntry]] = None  # populated when mode == CATALOG


@dataclass
class Edit:
    """A single change the proposer wants to make to a candidate."""

    op: Operation
    kind: str
    name: str
    value: str = ""  # new text (ADD/REWRITE) or catalog entry name (CATALOG)
    rationale: str = ""  # the proposer's diagnosis - useful for tracing


class Tunable(ABC):
    """Adapter mapping one slice of an AgentConfig to/from Components.

    Subclasses own a single ``kind``. ``read`` exposes the current artifacts as
    Components; ``apply`` validates a list of Edits and returns a new config.
    """

    kind: str
    ops: Set[Operation]
    mode: ProposalMode = ProposalMode.GENERATIVE

    @abstractmethod
    def read(self, config: AgentConfig) -> List[Component]: ...

    @abstractmethod
    def apply(self, config: AgentConfig, edits: List[Edit]) -> AgentConfig: ...


# --- Concrete tunables ------------------------------------------------------


class InstructionTunable(Tunable):
    """Rewrite the system prompt. Free-form, single component."""

    kind = "instructions"
    ops = {Operation.REWRITE}
    mode = ProposalMode.GENERATIVE

    def read(self, config: AgentConfig) -> List[Component]:
        return [Component("instructions", self.kind, config.system_prompt, self.ops, self.mode)]

    def apply(self, config: AgentConfig, edits: List[Edit]) -> AgentConfig:
        rewrites = [e for e in edits if e.op is Operation.REWRITE and e.value]
        if not rewrites:
            return config
        return replace(config, system_prompt=rewrites[-1].value)


class SkillTunable(Tunable):
    """Add / rewrite / remove named skills. Free-form (generative).

    A skill's value is the full ``SKILL.md`` text (YAML frontmatter + body). The
    frontmatter ``description``/``triggers`` drive JIT discovery (whether the agent
    loads the skill at all); the body is the content loaded on demand. Both are
    optimizable by editing this one text artifact. ``AgentConfig.to_agent``
    materializes these to a skills directory exposed via the SkillsTool.
    """

    kind = "skill"
    mode = ProposalMode.GENERATIVE

    def __init__(self, ops: Optional[Set[Operation]] = None):
        self.ops = ops or {Operation.ADD, Operation.REMOVE, Operation.REWRITE}

    def read(self, config: AgentConfig) -> List[Component]:
        return [
            Component(f"skill:{name}", self.kind, body, self.ops, self.mode)
            for name, body in config.skills.items()
        ]

    def apply(self, config: AgentConfig, edits: List[Edit]) -> AgentConfig:
        skills = dict(config.skills)
        for e in edits:
            if e.op not in self.ops:
                continue
            key = e.name.split("skill:", 1)[-1]
            if e.op is Operation.REMOVE:
                skills.pop(key, None)
            elif e.value:  # ADD or REWRITE
                skills[key] = e.value
        return replace(config, skills=skills)


class ToolDescriptionTunable(Tunable):
    """Rewrite the description text of tools. Free-form (generative)."""

    kind = "tool_description"
    ops = {Operation.REWRITE}
    mode = ProposalMode.GENERATIVE

    def read(self, config: AgentConfig) -> List[Component]:
        return [
            Component(f"tool_description:{name}", self.kind, desc, self.ops, self.mode)
            for name, desc in config.tool_descriptions.items()
        ]

    def apply(self, config: AgentConfig, edits: List[Edit]) -> AgentConfig:
        descs = dict(config.tool_descriptions)
        for e in edits:
            if e.op is Operation.REWRITE and e.value:
                descs[e.name.split("tool_description:", 1)[-1]] = e.value
        return replace(config, tool_descriptions=descs)


class ToolSelectionTunable(Tunable):
    """Add/remove tools chosen from a catalog. Constrained (catalog mode).

    The candidate's selection is ``config.tools``; ``apply`` rejects any value
    not present in the catalog, so candidates are always executable.
    """

    kind = "tool"
    ops = {Operation.ADD, Operation.REMOVE}
    mode = ProposalMode.CATALOG

    def __init__(self, catalog: List[CatalogEntry]):
        self.catalog = catalog

    def read(self, config: AgentConfig) -> List[Component]:
        return [
            Component(
                "tools",
                self.kind,
                ", ".join(config.tools),
                self.ops,
                self.mode,
                catalog=self.catalog,
            )
        ]

    def apply(self, config: AgentConfig, edits: List[Edit]) -> AgentConfig:
        valid = {c.name for c in self.catalog}
        tools = list(config.tools)
        for e in edits:
            if e.value not in valid:  # the constraint guarantee
                continue
            if e.op is Operation.ADD and e.value not in tools:
                tools.append(e.value)
            elif e.op is Operation.REMOVE and e.value in tools:
                tools.remove(e.value)
        return replace(config, tools=tools)


@dataclass
class OptimizationSpec:
    """Declares which properties of a candidate are open for optimization."""

    tunables: List[Tunable] = field(default_factory=lambda: [InstructionTunable()])

    def read(self, config: AgentConfig) -> List[Component]:
        return [c for t in self.tunables for c in t.read(config)]

    def apply(self, config: AgentConfig, edits: List[Edit]) -> AgentConfig:
        by_kind: Dict[str, List[Edit]] = {}
        for e in edits:
            by_kind.setdefault(e.kind, []).append(e)
        for t in self.tunables:
            kind_edits = by_kind.get(t.kind, [])
            if kind_edits:
                config = t.apply(config, kind_edits)
        return config

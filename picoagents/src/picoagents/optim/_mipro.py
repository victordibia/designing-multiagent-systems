"""MIPRO-style optimizer - propose from summaries, search by score.

A teaching implementation of the core idea in MIPRO/MIPROv2 (Opsahl-Ong et al.,
2024): instead of reflecting on individual failure traces, propose a *batch* of
instruction candidates grounded in a summary of the tasks plus a style tip, then
search over them by scalar score on a minibatch. The signal that drives the
proposal is the data summary, not a per-failure rationale - that is the structural
difference from the reflection loop.

Simplifications vs the real MIPROv2 (documented for honesty):
- Real MIPROv2 also bootstraps few-shot demonstrations and runs Bayesian search
  (Optuna TPE) over instruction x demo combinations. This version optimizes
  instructions only and does a flat minibatch search over the proposed candidates.
- It still fits the base loop: it only overrides ``propose`` (batch from summary)
  and ``select_parents`` (always propose from the seed, no iterative parent).
"""

from dataclasses import replace
from typing import Dict, List, Optional, Tuple

from ..eval import AgentConfig
from ..llm import BaseChatCompletionClient
from ..messages import SystemMessage, UserMessage
from ..types import Usage
from ._base import BaseOptimizer, Candidate

# Style tips, mirroring DSPy's tip-augmented instruction proposal.
TIPS = [
    "Be clear and direct.",
    "Be concise; prefer the shortest complete instruction.",
    "Spell out the rules and edge cases explicitly.",
    "Write it as a step-by-step procedure.",
    "Adopt the persona of a meticulous domain expert.",
    "Emphasize the required output format above all.",
]

SUMMARY_SYSTEM = (
    "You summarize a set of tasks so another model can write good instructions for "
    "an agent that must handle them. Be specific about what the agent must do and "
    "what good output looks like, in 2-4 sentences."
)

PROPOSE_SYSTEM = (
    "You write a system prompt (instruction) for an AI agent. You are given a summary "
    "of the tasks the agent must handle, the current instruction, and a style tip. "
    "Write a single improved instruction. Return only the instruction text."
)


class MIPROOptimizer(BaseOptimizer):
    """Propose instruction candidates from a data summary + tips, then search by score.

    Set ``minibatch`` to search candidates cheaply before the base loop full-evaluates
    those that clear the gate. Run with ``rounds=1``: all candidates are proposed at once.
    """

    def __init__(
        self,
        *args,
        proposer: BaseChatCompletionClient,
        num_candidates: int = 6,
        sample_tasks: int = 6,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.proposer = proposer
        self.num_candidates = num_candidates
        self.sample_tasks = sample_tasks
        self._summary: Optional[str] = None
        self._proposed = False
        self._last_proposal_call: Tuple[List[Dict[str, str]], Optional[str], Optional[Usage], Optional[str]] = ([], None, None, None)

    def select_parents(self, pool: List[Candidate]) -> List[Candidate]:
        # MIPRO proposes for the program from a summary, not by improving a parent.
        # Always propose from the seed (the first candidate in the pool).
        return [pool[0]]

    async def propose(
        self, parents: List[Candidate], pool: List[Candidate]
    ) -> List[Tuple[AgentConfig, str]]:
        if self._proposed:
            return []  # all candidates are proposed in a single batch
        self._proposed = True

        seed_cfg = parents[0].config
        self._summary = await self._summarize_tasks()

        proposals: List[Tuple[AgentConfig, str]] = []
        for i in range(self.num_candidates):
            tip = TIPS[i % len(TIPS)]
            instruction = await self._propose_instruction(seed_cfg.system_prompt, tip)
            cfg = replace(seed_cfg, name=f"mipro#{i + 1}", system_prompt=instruction)
            proposals.append((cfg, f"summary-grounded, tip: {tip}"))
            messages, response, usage, model = self._last_proposal_call
            self._record_proposal(
                parent=seed_cfg.name, stage="propose", messages=messages, response=response,
                candidate=cfg, usage=usage, model=model, tip=tip,
            )
        return proposals

    # --- helpers (data-aware proposal, no failure-trace reflection) ---

    async def _summarize_tasks(self) -> str:
        sample = self.tasks[: self.sample_tasks]
        lines = ["Tasks the agent must handle (with example expected outputs where available):\n"]
        for t in sample:
            crit = ", ".join(t.eval_criteria) if t.eval_criteria else "quality"
            lines.append(f"- input: {t.input}\n  judged on: {crit}")
            if t.expected_output:
                lines.append(f"  example good output: {t.expected_output}")
        prompt = "\n".join(lines) + "\n\nSummarize what the agent must do and what good output looks like."
        result = await self.proposer.create(
            [SystemMessage(content=SUMMARY_SYSTEM, source="mipro"),
             UserMessage(content=prompt, source="mipro")]
        )
        self._track_reflection(result.usage)
        self._record_proposal(
            parent=None, stage="summary",
            messages=[{"role": "system", "content": SUMMARY_SYSTEM},
                      {"role": "user", "content": prompt}],
            response=result.message.content, usage=result.usage, model=result.model,
            sampled_task_ids=[t.id or t.name for t in sample],
        )
        return result.message.content or ""

    async def _propose_instruction(self, current: str, tip: str) -> str:
        prompt = (
            f"Task summary:\n{self._summary}\n\n"
            f"Current instruction:\n{current}\n\n"
            f"Style tip: {tip}\n\n"
            "Write the improved instruction now."
        )
        result = await self.proposer.create(
            [SystemMessage(content=PROPOSE_SYSTEM, source="mipro"),
             UserMessage(content=prompt, source="mipro")]
        )
        self._track_reflection(result.usage)
        self._last_proposal_call = (
            [{"role": "system", "content": PROPOSE_SYSTEM}, {"role": "user", "content": prompt}],
            result.message.content, result.usage, result.model,
        )
        return (result.message.content or current).strip()

"""Reflective optimizer with Pareto-frontier selection.

This extends the reflection loop with a Pareto frontier: instead of keeping only the
single best-on-average candidate, it keeps candidates that are best on *some* task,
which preserves diversity across an evolutionary search. The only changes from
ReflectiveOptimizer are the two selection knobs - most optimizers are the same loop
with a different ``select``.

This captures two ideas popularized by GEPA (reflective prompt evolution + Pareto
selection; Agrawal et al., arXiv:2507.19457), but it is NOT GEPA: it omits the
genetic merge/crossover, round-robin component selection, and the subsampling /
budget / stall machinery that define the full algorithm. For real GEPA, use the
`gepa` library; this class is a teaching building block, named for what it does.
"""

import random
from typing import List

from ._base import Candidate
from ._reflective import ReflectiveOptimizer


def pareto_frontier(pool: List[Candidate]) -> List[Candidate]:
    """Candidates that achieve the best score on at least one task.

    Preserves diversity: a candidate strong on a few hard tasks survives even if
    its average trails the current leader.
    """
    if not pool:
        return []
    task_ids = {tid for c in pool for tid in c.task_scores}
    best_per_task = {
        tid: max(c.task_scores.get(tid, float("-inf")) for c in pool) for tid in task_ids
    }
    frontier = [
        c
        for c in pool
        if any(c.task_scores.get(tid, float("-inf")) >= best_per_task[tid] for tid in task_ids)
    ]
    return frontier or [max(pool, key=lambda c: c.avg)]


class ReflectiveParetoOptimizer(ReflectiveOptimizer):
    """Reflective optimizer with Pareto-frontier candidate selection."""

    def __init__(self, *args, seed: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self._rng = random.Random(seed)

    def select(self, pool: List[Candidate]) -> List[Candidate]:
        """Keep the Pareto frontier instead of the greedy top-k."""
        return pareto_frontier(pool)

    def select_parents(self, pool: List[Candidate]) -> List[Candidate]:
        """Sample a parent from the frontier, weighted by how many tasks it wins."""
        frontier = pareto_frontier(pool)
        weights = [self._tasks_won(c, frontier) + 1 for c in frontier]
        parent = self._rng.choices(frontier, weights=weights, k=1)[0]
        return [parent]

    @staticmethod
    def _tasks_won(cand: Candidate, frontier: List[Candidate]) -> int:
        won = 0
        for tid, score in cand.task_scores.items():
            if score >= max(c.task_scores.get(tid, float("-inf")) for c in frontier):
                won += 1
        return won

"""Head-to-head comparison of optimization algorithms, under an equal budget.

Every method gets the same train split to optimize on, the same held-out test split
to be judged on, the same fixed judge, and the same rollout budget. That last point
matters: an optimizer that "wins" by spending twice the rollouts has not won.

    python compare-optimizers.py Reflective 0
    python compare-optimizers.py GEPA 0 240

Methods:
  Reflective        reflect on failing traces, keep the best candidate
  ReflectivePareto  same, but keep a Pareto frontier (a core idea from GEPA)
  MIPRO             propose instructions from data summaries, search by score
  GEPA              the real gepa library (pip install gepa), driven through picoagents

Results (score, generalization gap, and cost split by agent/judge/reflection) are
written to results/.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from picoagents.eval import AgentConfig, EvalRunner, load_builtin_dataset
from picoagents.optim import (
    InstructionTunable,
    MIPROOptimizer,
    OptimizationSpec,
    ReflectiveOptimizer,
    ReflectiveParetoOptimizer,
    optimize_with_gepa,
)

sys.path.insert(0, str(Path(__file__).parent))
from generalization import (  # noqa: E402
    RuleAwareJudge,
    SEED_PROMPT,
    make_client,
    score_split,
)

RESULTS = Path(__file__).parent / "results"
MINIBATCH = 10
METHODS = ("Reflective", "ReflectivePareto", "MIPRO", "GEPA")


async def main(method: str, seed_n: int = 0, budget: int = 120,
               model: str = "gpt-4.1-mini") -> None:
    if method not in METHODS:
        raise SystemExit(f"unknown method {method!r}; choose from {', '.join(METHODS)}")

    os.environ["AZURE_OPENAI_DEPLOYMENT"] = model
    reflector = make_client(model, 0.8)
    judge = RuleAwareJudge(make_client("gpt-4.1-mini", 0.0))

    dataset = load_builtin_dataset("support")
    train = dataset.filter(lambda t: t.metadata.get("split") == "train")
    test = dataset.filter(lambda t: t.metadata.get("split") == "test")
    spec = OptimizationSpec([InstructionTunable()])
    seed = AgentConfig(name="seed", model_provider="azure", tools=[], max_iterations=3,
                       system_prompt=SEED_PROMPT)

    base_train, base_train_detail = await score_split(seed, train.tasks, judge)
    base_test, base_test_detail = await score_split(seed, test.tasks, judge)
    print(f"[{method}] baseline train={base_train:.2f} test={base_test:.2f}")

    runner = EvalRunner(judge=judge)
    shared = dict(rounds=60, budget=budget, beam=50, minibatch=MINIBATCH)

    if method == "Reflective":
        result = await ReflectiveOptimizer(runner, train, spec, reflector=reflector,
                                           **shared).optimize(seed)
    elif method == "ReflectivePareto":
        result = await ReflectiveParetoOptimizer(runner, train, spec, reflector=reflector,
                                                 seed=seed_n, **shared).optimize(seed)
    elif method == "MIPRO":
        result = await MIPROOptimizer(runner, train, spec, proposer=reflector,
                                      num_candidates=6, rounds=1, budget=budget,
                                      beam=50, minibatch=MINIBATCH).optimize(seed)
    else:  # GEPA - the real library
        result = await optimize_with_gepa(seed, train, reflection_client=reflector,
                                          runner=runner, budget=budget,
                                          reflection_minibatch_size=MINIBATCH, seed=seed_n)

    best, cost, rollouts = result.best, result.cost, result.eval_count
    best_train, best_train_detail = await score_split(best, train.tasks, judge)
    best_test, best_test_detail = await score_split(best, test.tasks, judge)

    print(f"[{method}] optimized train={best_train:.2f} test={best_test:.2f} "
          f"(test +{best_test - base_test:.2f}) in {rollouts} rollouts")
    print(cost.summary())

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{method}__seed{seed_n}__b{budget}.json").write_text(
        json.dumps({
            "meta": {"method": method, "seed": seed_n, "budget": budget, "model": model,
                     "rollouts": rollouts, "minibatch": MINIBATCH,
                     "baseline_train": base_train, "baseline_test": base_test,
                     "best_train": best_train, "best_test": best_test,
                     "train_gain": best_train - base_train,
                     "test_gain": best_test - base_test,
                     "gap": (best_train - base_train) - (best_test - base_test),
                     "cost": cost.to_dict()},
            "final_best_prompt": best.system_prompt,
            "baseline_train_detail": base_train_detail,
            "baseline_test_detail": base_test_detail,
            "best_train_detail": best_train_detail,
            "best_test_detail": best_test_detail,
        }, indent=2, default=str)
    )


if __name__ == "__main__":
    method = sys.argv[1] if len(sys.argv) > 1 else "Reflective"
    seed_n = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    budget = int(sys.argv[3]) if len(sys.argv) > 3 else 120
    asyncio.run(main(method, seed_n, budget))

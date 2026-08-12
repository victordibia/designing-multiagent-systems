"""Does optimization generalize, or does it just memorize your eval?

Optimizes on the TRAIN split only, then scores the winner on a HELD-OUT TEST split
whose tasks the optimizer never saw. Test tasks reuse the same house rules with new
customer contacts, so a rising test score means the agent learned the *rule*, not
the ticket.

    python generalization.py            # budget 120, seed 0
    python generalization.py 240 1      # budget 240, seed 1

Scoring uses a rule-aware judge: criteria that are objectively checkable (ticket
formats, arithmetic, "never echo a card number") are scored by regex for zero
variance, while genuinely subjective criteria (tone) still use the model judge.
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

from picoagents.eval import (
    AgentConfig,
    EvalRunner,
    LLMEvalJudge,
    PicoAgentTarget,
    load_builtin_dataset,
)
from picoagents.eval.judges import BaseEvalJudge
from picoagents.llm import AzureOpenAIChatCompletionClient
from picoagents.optim import InstructionTunable, OptimizationSpec, ReflectiveOptimizer

RESULTS = Path(__file__).parent / "results"
SEED_PROMPT = "You are a customer support agent. Help the customer."


def make_client(model: str, temperature: float = 0.0):
    # Some deployments reject an explicit temperature; only set it where supported.
    kwargs = {"temperature": temperature} if model.startswith("gpt-4") else {}
    return AzureOpenAIChatCompletionClient(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_deployment=model,
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        **kwargs,
    )


class RuleAwareJudge(BaseEvalJudge):
    """Model judge, with a deterministic regex override per objectively checkable criterion.

    A task opts in via metadata:
        "deterministic": {"criterion": "ticket_reference",
                          "pattern": "TKT-\\d{6}",
                          "must_match": true}
    Set must_match false for rules of the form "this must NOT appear" (e.g. PII).
    The override still writes a descriptive rationale, so the optimizer's reflection
    step has something to learn from.
    """

    def __init__(self, llm_client):
        super().__init__(name="rule_aware")
        self.llm = LLMEvalJudge(llm_client)

    async def score(self, trajectory, criteria=None, cancellation_token=None):
        score = await self.llm.score(trajectory, criteria, cancellation_token)
        task = trajectory.task if trajectory else None
        rule = (task.metadata or {}).get("deterministic") if task else None
        if not rule:
            return score

        criterion, pattern = rule["criterion"], rule["pattern"]
        must_match = rule.get("must_match", True)
        found = re.search(pattern, score.get_final_response() or "") is not None
        passed = found if must_match else not found

        dimensions = dict(score.dimensions)
        reasoning = dict(score.reasoning)
        dimensions[criterion] = 10.0 if passed else 0.0
        if must_match:
            reasoning[criterion] = (
                f"Deterministic check: reply matches the required pattern {pattern}."
                if passed
                else f"Deterministic check: reply is missing the required pattern {pattern}."
            )
        else:
            reasoning[criterion] = (
                f"Deterministic check: reply correctly avoids {pattern}."
                if passed
                else f"Deterministic check: reply repeats {pattern}, which must never be echoed back."
            )
        return type(score)(
            overall=sum(dimensions.values()) / len(dimensions),
            dimensions=dimensions,
            reasoning=reasoning,
            trajectory=score.trajectory,
            metadata=score.metadata,
        )


def detail(scores):
    return [
        {
            "task_id": s.trajectory.task.id if s.trajectory and s.trajectory.task else "?",
            "overall": s.overall,
            "response": s.get_final_response(),
            "reasoning": s.reasoning,
        }
        for s in scores
    ]


async def score_split(config, tasks, judge):
    scores = await EvalRunner(judge=judge).evaluate(PicoAgentTarget(config), list(tasks))
    return sum(s.overall for s in scores) / len(scores), detail(scores)


async def main(budget: int = 120, seed_n: int = 0, model: str = "gpt-4.1-mini") -> None:
    # The agent's deployment is resolved from this env var, so set it explicitly
    # rather than inheriting whatever the shell happens to have.
    os.environ["AZURE_OPENAI_DEPLOYMENT"] = model
    reflector = make_client(model, 0.8)
    judge = RuleAwareJudge(make_client("gpt-4.1-mini", 0.0))

    dataset = load_builtin_dataset("support")
    train = dataset.filter(lambda t: t.metadata.get("split") == "train")
    test = dataset.filter(lambda t: t.metadata.get("split") == "test")

    seed = AgentConfig(name="seed", model_provider="azure", tools=[], max_iterations=3,
                       system_prompt=SEED_PROMPT)

    base_train, base_train_detail = await score_split(seed, train.tasks, judge)
    base_test, base_test_detail = await score_split(seed, test.tasks, judge)
    print(f"baseline : train={base_train:.2f}  test={base_test:.2f}")

    optimizer = ReflectiveOptimizer(
        EvalRunner(judge=judge), train, OptimizationSpec([InstructionTunable()]),
        reflector=reflector, rounds=60, budget=budget, minibatch=10, beam=50,
    )
    result = await optimizer.optimize(seed)

    best_train, best_train_detail = await score_split(result.best, train.tasks, judge)
    best_test, best_test_detail = await score_split(result.best, test.tasks, judge)
    train_gain, test_gain = best_train - base_train, best_test - base_test

    print(f"optimized: train={best_train:.2f} (+{train_gain:.2f})  "
          f"test={best_test:.2f} (+{test_gain:.2f})")
    print(f"generalization gap (train gain - test gain): {train_gain - test_gain:+.2f}")
    print("  a negative gap means the held-out tasks improved at least as much as "
          "the ones optimized on: the agent learned rules, not answers.")

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"generalization__{model}__seed{seed_n}__b{budget}.json").write_text(
        json.dumps({
            "meta": {"model": model, "seed": seed_n, "budget": budget,
                     "rollouts": result.eval_count,
                     "train_size": len(train), "test_size": len(test),
                     "baseline_train": base_train, "baseline_test": base_test,
                     "best_train": best_train, "best_test": best_test,
                     "train_gain": train_gain, "test_gain": test_gain,
                     "gap": train_gain - test_gain, "cost": result.cost.to_dict()},
            "final_best_prompt": result.best.system_prompt,
            "baseline_train_detail": base_train_detail,
            "baseline_test_detail": base_test_detail,
            "best_train_detail": best_train_detail,
            "best_test_detail": best_test_detail,
        }, indent=2, default=str)
    )


if __name__ == "__main__":
    budget = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    seed_n = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    asyncio.run(main(budget, seed_n))

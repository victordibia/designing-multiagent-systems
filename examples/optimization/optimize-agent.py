"""Optimize an agent's instructions automatically from evaluation feedback.

The smallest complete example of the optimization loop: run the agent, score it,
let a model read the failures and propose a better instruction, test the proposal,
repeat. Nothing here is bespoke - it reuses the same EvalRunner and judge from the
evaluation chapter.

    python optimize-agent.py quick   # 5 tasks, budget 20  (~2 min)
    python optimize-agent.py full    # 30 tasks, budget 120 (~20 min)

Requires Azure OpenAI env vars (see .env.example):
AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT
"""

import asyncio
import os
import sys

from picoagents.eval import (
    AgentConfig,
    EvalRunner,
    LLMEvalJudge,
    load_builtin_dataset,
)
from picoagents.llm import AzureOpenAIChatCompletionClient
from picoagents.optim import InstructionTunable, OptimizationSpec, ReflectiveOptimizer

SEED_PROMPT = "You are a customer support agent. Help the customer."


def make_client(temperature: float = 0.0) -> AzureOpenAIChatCompletionClient:
    return AzureOpenAIChatCompletionClient(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        temperature=temperature,
    )


async def main(mode: str = "quick") -> None:
    quick = mode == "quick"
    budget = 20 if quick else 120

    # The agent under test, and the model that will reflect on its failures.
    client = make_client(0.0)
    reflector = make_client(0.8)  # some diversity in proposals

    # Tasks the agent must handle. House rules live in each task's rubric, so the
    # agent cannot know them up front - it has to learn them from feedback.
    dataset = load_builtin_dataset("support")
    train = dataset.filter(lambda t: t.metadata.get("split") == "train")
    if quick:
        train = train.filter_by_ids([t.id for t in train.tasks][:5])

    seed = AgentConfig(
        name="seed",
        model_provider="azure",
        tools=[],
        max_iterations=3,
        system_prompt=SEED_PROMPT,
    )

    # Declare what the optimizer may change. Instructions here; skills and tool
    # selection are also tunable (see compare-optimizers.py and the book).
    spec = OptimizationSpec([InstructionTunable()])

    optimizer = ReflectiveOptimizer(
        EvalRunner(judge=LLMEvalJudge(client)),
        train,
        spec,
        reflector=reflector,
        rounds=60,
        budget=budget,          # cap on agent rollouts - this is the real cost
        minibatch=min(10, len(train)),  # screen candidates cheaply before a full eval
        beam=50,
    )

    print(f"Optimizing on {len(train)} tasks with a budget of {budget} rollouts...\n")
    result = await optimizer.optimize(seed)

    seed_score = next(c for c in result.pool if c.config.name == "seed").avg
    print(f"seed score      : {seed_score:.2f}")
    print(f"optimized score : {result.best_candidate.avg:.2f}")
    print(f"rollouts spent  : {result.eval_count}\n")
    print("cost by source:")
    print(result.cost.summary())
    print("\noptimized instruction:\n")
    print(result.best.system_prompt)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "quick"))

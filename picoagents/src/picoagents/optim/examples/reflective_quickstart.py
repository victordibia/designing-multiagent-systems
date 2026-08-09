"""Quickstart: optimize an agent's instructions with the reflection loop.

Reuses the eval module to score candidates. Uses Azure OpenAI per the picoagents
convention. Run:

    python -m picoagents.optim.examples.reflective_quickstart
"""

import asyncio
import os

from picoagents.eval import AgentConfig, EvalRunner, LLMEvalJudge, load_builtin_dataset
from picoagents.llm import AzureOpenAIChatCompletionClient
from picoagents.optim import ReflectiveOptimizer, ReflectiveParetoOptimizer
from picoagents.optim import InstructionTunable, OptimizationSpec


def make_client() -> AzureOpenAIChatCompletionClient:
    return AzureOpenAIChatCompletionClient(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_deployment=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini"),
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    )


async def main() -> None:
    client = make_client()
    dataset = load_builtin_dataset("quick_v1")
    runner = EvalRunner(judge=LLMEvalJudge(client))

    seed = AgentConfig(
        name="seed",
        model_provider="azure",
        system_prompt="You are a helpful assistant.",
    )

    # Optimize instructions only (the simplest surface).
    spec = OptimizationSpec(tunables=[InstructionTunable()])

    opt = ReflectiveOptimizer(
        runner, dataset, spec, reflector=client, rounds=3, weak_k=2
    )
    result = await opt.optimize(seed)

    print(f"\nrollouts spent: {result.eval_count}")
    for c in sorted(result.pool, key=lambda c: c.avg, reverse=True):
        print(f"  {c.config.name:12s} avg={c.avg:5.2f}  parent={c.parent}")
    print(f"\nbest instructions:\n{result.best.system_prompt}")

    # Swap one knob to get Pareto-frontier selection - same loop, same seed.
    _ = ReflectiveParetoOptimizer  # identical call site, different select()


if __name__ == "__main__":
    asyncio.run(main())

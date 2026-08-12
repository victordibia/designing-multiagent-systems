# Agent Optimization

Automatically improving an agent's configuration from evaluation feedback, for
Chapter 11 of [Designing Multi-Agent Systems](https://buy.multiagentbook.com/?utm_source=github&utm_medium=readme-optimization).

Optimization is search over an agent's configuration against a metric. Every method
here is the same loop - run the agent, score it, propose a change, test the proposal,
repeat - and they differ only in what they mutate, what signal drives the proposal,
and what they keep. The implementation lives in
[`picoagents.optim`](../../picoagents/src/picoagents/optim/).

## Quick Start

```bash
cd picoagents && pip install -e ".[all]"
cp .env.example .env     # add your Azure OpenAI credentials

cd ../examples/optimization
python optimize-agent.py quick     # ~2 min: watch a score climb
```

Optimization is *active*: every candidate is executed on your tasks and scored,
because there is no other way to know if it is better. Budgets below are in agent
rollouts, which is where the money goes.

## Examples

| File | What it shows | Runtime |
|------|---------------|---------|
| `optimize-agent.py` | The core loop. Reflect on failures, rewrite the instruction, measure the gain. | quick ~2 min / full ~20 min |
| `generalization.py` | Optimize on a train split, score on held-out test. Did it learn rules, or memorize your eval? | ~20 min |
| `compare-optimizers.py` | Reflective vs ReflectivePareto vs MIPRO vs real GEPA under an equal budget. | ~20 min per method |

```bash
python optimize-agent.py full
python generalization.py 240 0            # budget 240, seed 0
python compare-optimizers.py GEPA 0 120   # method, seed, budget
```

Results are written to `results/` with the full detail behind every number: each
candidate tried, the agent's response on each task, and the judge's score and
reasoning. That is deliberate - a score you cannot trace back to a transcript is
not evidence.

## The dataset

All three scripts use the builtin `support` dataset (35 customer-support tasks):

```python
from picoagents.eval import load_builtin_dataset
dataset = load_builtin_dataset("support")
train = dataset.filter(lambda t: t.metadata.get("split") == "train")  # 30 tasks
test = dataset.filter(lambda t: t.metadata.get("split") == "test")    # 16 tasks
```

Design choices that matter if you build your own:

- **House rules live only in the rubric**, never in the agent's prompt. The agent
  cannot guess a 30-day return window or a `TKT-######` ticket format, so it has to
  learn them from feedback. That is the gap real optimization has to close.
- **Train and test share rule families but not tasks.** Test tasks apply the same
  policies to new customer contacts, like optimizing on last month's tickets and
  deploying on next month's. A rising test score means the rule transferred.
- **Paired tasks block degenerate policies.** For every "decline this refund" there
  is an "approve this one", so an agent that learns to refuse everything scores badly.
- **Deterministic scoring where the answer is objective** (formats, arithmetic, never
  echoing a card number) via `metadata.deterministic`, model judging only for genuinely
  subjective criteria like tone. Judge noise is the largest source of variance in these
  experiments, so it is worth removing wherever the rule is checkable.

## What to optimize

`OptimizationSpec` declares the surface an optimizer may change. Instructions are the
default, but anything you can represent and swap is fair game:

```python
from picoagents.optim import (
    OptimizationSpec, InstructionTunable, SkillTunable,
    ToolSelectionTunable, ToolDescriptionTunable, CatalogEntry,
)

spec = OptimizationSpec([
    InstructionTunable(),                       # rewrite the system prompt
    SkillTunable(),                             # add/rewrite/remove SKILL.md procedures
    ToolDescriptionTunable(),                   # rewrite tool descriptions
    ToolSelectionTunable([                      # add/remove tools, from a catalog
        CatalogEntry("calculator", "Evaluate arithmetic expressions exactly"),
    ]),
])
```

Generative tunables (instructions, skills) let the model write new text. Catalog
tunables (tools, model) make it choose from a fixed set, so every candidate is valid
by construction.

## Reading the cost

Every result carries a `CostLog` split by source, because the intuition about where
optimization spends money is usually wrong:

```python
print(result.cost.summary())
# source           tokens  llm_calls        usd
# agent            19,226         50          -
# judge            32,451         50    $1.0812
# reflection        3,402          3    $0.1365
```

Reflection - the "intelligence" of the loop - is typically a few percent of the bill.
Running and *judging* candidates is nearly all of it, and unlike the one-time
optimization run, evaluation cost recurs every time you measure.

# PicoAgents Examples

Runnable examples for the book [Designing Multi-Agent Systems](https://buy.multiagentbook.com/?utm_source=github&utm_medium=readme-examples) by Victor Dibia. Each example maps to a book chapter that explains the theory and design trade-offs behind it.

## Quick Start

```bash
cd picoagents
pip install -e ".[all]"
cp .env.example .env  # Add your OPENAI_API_KEY
cd ..
python examples/agents/basic-agent.py
```

## Examples by Chapter

| Chapter | Directory | What You'll Learn |
|---------|-----------|-------------------|
| Ch 4: Building Your First Agent | [`agents/`](agents/) | Tool use, memory, structured output, middleware |
| Ch 5: Workflows | [`workflows/`](workflows/) | Sequential, conditional, parallel execution patterns |
| Ch 6: Orchestration | [`orchestration/`](orchestration/) | Round-robin, AI-driven, and plan-based multi-agent coordination |
| Ch 8: Evaluation | [`evaluation/`](evaluation/) | LLM-as-judge, reference-based evaluation, metrics |

## All Examples

### agents/
Core agent patterns from Chapter 4.

| File | Description |
|------|-------------|
| `basic-agent.py` | Simple agent with weather and calculator tools |
| `memory.py` | Agent with conversation memory |
| `structured-output.py` | Agent returning Pydantic models |
| `middleware.py` | Request/response middleware pipeline |
| `computer_use.py` | Browser automation agent |
| `agent_as_tool.py` | Using an agent as a tool for another agent |
| `serialization.py` | Saving and loading agent state |

### workflows/
Explicit control patterns from Chapter 6.

| File | Description |
|------|-------------|
| `sequential.py` | Chain steps with typed inputs/outputs |
| `conditional.py` | Conditional branching and fan-in merge |
| `general.py` | Extended sequential pipeline with fluent API |
| `checkpoint_example.py` | Save and resume workflow state |
| `data_visualization/` | Complete data analysis workflow |
| `yc_analysis/` | Y Combinator startup analysis workflow |

### orchestration/
Autonomous coordination from Chapter 7.

| File | Description |
|------|-------------|
| `round-robin.py` | Agents take turns in sequence |
| `ai-driven.py` | LLM selects next speaker |
| `ai-driven-research.py` | Research team with AI coordination |
| `plan-based.py` | Orchestrator creates and follows a plan |

### evaluation/
Testing and metrics from Chapter 10.

| File | Description |
|------|-------------|
| `agent-evaluation.py` | LLM-as-judge evaluation |
| `reference-based-evaluation.py` | Compare against expected outputs |
| `comprehensive-evaluation.py` | Full evaluation suite |

### Other Examples

| Directory | Description |
|-----------|-------------|
| `tools/` | Tool definitions and approval patterns |
| `memory/` | Memory implementations (list, tool-based) |
| `mcp/` | Model Context Protocol integration |
| `otel/` | OpenTelemetry observability |
| `webui/` | Web UI examples |
| `app/` | Full-stack application example |
| `contextengineering/` | Context window management strategies |
| `frameworks/` | Same patterns in other frameworks (LangGraph, Google ADK, etc.) |

## Framework Comparisons

The [`frameworks/`](frameworks/) directory shows equivalent implementations across:

- **agent-framework/** - Microsoft Agent Framework
- **langgraph/** - LangChain LangGraph
- **google-adk/** - Google Agent Development Kit
- **claude-agent-sdk/** - Anthropic Claude Agent SDK

Each implements the same agent/workflow/orchestration patterns for comparison.

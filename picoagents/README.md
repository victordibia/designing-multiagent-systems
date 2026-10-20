# PicoAgents

![PicoAgents Web UI](https://raw.githubusercontent.com/victordibia/designing-multiagent-systems/main/docs/images/picoagents_screenshot.png)

**An educational multi-agent framework built to teach you how multi-agent systems work from first principles.**

Companion code for [**"Designing Multi-Agent Systems"**](https://buy.multiagentbook.com/?utm_source=github&utm_medium=readme-picoagents) by [Victor Dibia](https://victordibia.com). Every concept in the book is implemented here with clarity and best practices—so you can learn by reading the code and understanding exactly how it works.

> **Built for learning**: This framework prioritizes code clarity and pedagogical value over performance optimization.

## Installation

```bash
pip install picoagents
```

**Requirements:**

- Python 3.10+
- OpenAI API key (set `OPENAI_API_KEY` environment variable)

**Optional extras:**

```bash
pip install "picoagents[web]"      # Web UI, MCP playground, evaluation dashboard
pip install "picoagents[mcp]"      # MCP client (requires mcp>=2.0.0, protocol 2026-07-28)
pip install "picoagents[persist]"  # Run and eval persistence behind the History page
```

## Quick Start

```python
from picoagents import Agent, OpenAIChatCompletionClient

def get_weather(location: str) -> str:
    """Get current weather for a given location."""
    return f"The weather in {location} is sunny, 75°F"

# Create an agent
agent = Agent(
    name="assistant",
    instructions="You are helpful. Use tools when appropriate.",
    model_client=OpenAIChatCompletionClient(model="gpt-4.1-mini"),
    tools=[get_weather]
)

# Use the agent
response = await agent.run("What's the weather in Paris?")
print(response.messages[-1].content)
```

## What's Included

PicoAgents implements complete, working examples of:

- **Agents** - Reasoning loops, tool calling, memory, middleware, streaming
- **Workflows** - Type-safe DAG-based execution with parallel and conditional patterns
- **Orchestration** - Round-robin, AI-driven, and plan-based multi-agent coordination
- **Tools** - 15+ built-in tools (file ops, code execution, search, todos, skills)
- **MCP** - Client for the 2026-07-28 spec, plus a playground for testing servers with full wire visibility
- **Evaluation** - LLM-as-judge patterns, reference-based validation, datasets and batch runs
- **Web UI** - Auto-discovery, streaming chat, run history, MCP playground

## Project Structure

```
picoagents/
├── src/picoagents/
│   ├── agents/            # Agent implementations (Ch 4-5)
│   ├── workflow/          # Workflow orchestration (Ch 5)
│   ├── orchestration/     # Autonomous coordination (Ch 6)
│   ├── tools/             # Tool system and built-in tools
│   ├── eval/              # Evaluation framework (Ch 8)
│   ├── webui/             # Web interface with auto-discovery
│   ├── llm/               # LLM clients (OpenAI, Azure)
│   ├── memory/            # Memory implementations
│   └── termination/       # Termination conditions
└── tests/                 # Comprehensive test suite
```

## Web search

Install MCP support for free web search without a search account or API key:

```bash
pip install "picoagents[mcp]"
```

```python
from picoagents import Agent, OpenAIChatCompletionClient
from picoagents.tools import create_research_tools

agent = Agent(
    name="researcher",
    instructions="Search for current information and cite the source URLs.",
    model_client=OpenAIChatCompletionClient(model="gpt-4.1-mini"),
    tools=list(create_research_tools()),
)
response = await agent.run("What is new in Python's latest release?")
print(response.messages[-1].content)
```

Unconfigured `create_research_tools()` and `WebSearchTool()` now use
[Parallel Search MCP](https://docs.parallel.ai/integrations/mcp/search-mcp)
at `https://search.parallel.ai/mcp`. Anonymous search uses Fast mode and is
intended for exploration and light use, with service rate limits. Results keep
the existing `title`, `url`, and `snippet` fields. `max_results` limits the
returned list locally; domain allow/block rules also filter results locally.

Supplying `tavily_api_key` to the factory (or `api_key` to `WebSearchTool`)
keeps Tavily. A factory configured only with Google credentials stays Google-only.
Use `web_search_provider="parallel"` or `"tavily"` to select explicitly;
`web_search_provider="disabled"` omits `WebSearchTool`. Existing Google tools
remain available when configured. Explicit provider failures are reported without
switching services. For a single tool, import `WebSearchTool` from
`picoagents.tools._research_tools` and use `provider="parallel"` or `"tavily"`;
`timeout` bounds discovery and search (default 30 seconds).

To continue a conversation, pass `context=response.context` to the next
`agent.run()`. Parallel's opaque conversation ID is kept in context metadata,
separate from user identifiers. A fresh context or `context.reset()` starts a new
search conversation. Standalone `tool.execute()` calls each start a separate
research run. Agent tool approvals and cancellation still apply. Page fetching
continues to use the existing `WebFetchTool` HTTP implementation.

## Web UI

Launch the web interface with auto-discovery of agents and workflows:

```bash
picoagents ui
```

Features streaming responses, real-time debug events, and session management.

## Examples

See the [main repository](https://github.com/victordibia/designing-multiagent-systems) for 50+ runnable examples organized by book chapter:

- [`examples/agents/`](https://github.com/victordibia/designing-multiagent-systems/tree/main/examples/agents) - Basic agents, tools, memory, computer use (Ch 4-5)
- [`examples/workflows/`](https://github.com/victordibia/designing-multiagent-systems/tree/main/examples/workflows) - Workflow patterns and case studies (Ch 5)
- [`examples/orchestration/`](https://github.com/victordibia/designing-multiagent-systems/tree/main/examples/orchestration) - Multi-agent coordination (Ch 6)
- [`examples/evaluation/`](https://github.com/victordibia/designing-multiagent-systems/tree/main/examples/evaluation) - Evaluation patterns (Ch 8)

## Get the Book

<p align="center">
  <a href="https://buy.multiagentbook.com/?utm_source=github&utm_medium=readme-picoagents">
    <img src="https://raw.githubusercontent.com/victordibia/designing-multiagent-systems/main/docs/images/bookcover.png" alt="Designing Multi-Agent Systems Book Cover" width="100%">
  </a>
</p>

**[Designing Multi-Agent Systems: Principles, Patterns, and Implementation for AI Agents](https://buy.multiagentbook.com/?utm_source=github&utm_medium=readme-picoagents)**

This framework implements every concept from the book. The book provides:

- **Why and when** to use each pattern
- **Trade-off analysis** for design decisions
- **Real-world case studies** with complete implementations
- **Evaluation strategies** for measuring system performance

**[→ Buy Digital Edition](https://buy.multiagentbook.com/?utm_source=github&utm_medium=readme-picoagents)** | **[→ GitHub Repository](https://github.com/victordibia/designing-multiagent-systems)**

## Development

```bash
# Clone repository
git clone https://github.com/victordibia/designing-multiagent-systems.git
cd designing-multiagent-systems/picoagents

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest tests/

# Type checking
python -m mypy src/
python -m pyright src/

# Code formatting
python -m black src/ tests/
python -m isort src/ tests/
```

## Author

**Victor Dibia** - [Website](https://victordibia.com) | [LinkedIn](https://www.linkedin.com/in/dibiavictor/) | [GitHub](https://github.com/victordibia)

## Citation

```bibtex
@book{dibia2025multiagent,
  title={Designing Multi-Agent Systems: Principles, Patterns, and Implementation for AI Agents},
  author={Dibia, Victor},
  year={2025},
  url={https://buy.multiagentbook.com}
}
```

## License

MIT License - see LICENSE file for details.

---

**Learn more**: [Book Website](https://buy.multiagentbook.com/?utm_source=github&utm_medium=readme-picoagents) | [GitHub](https://github.com/victordibia/designing-multiagent-systems) | [Documentation](https://github.com/victordibia/designing-multiagent-systems#readme)

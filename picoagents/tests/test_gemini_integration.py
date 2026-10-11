"""Opt-in live Gemini checks: pytest -m integration tests/test_gemini_integration.py.

Requires python-dotenv (examples extra) and an AI Studio key in the environment
or picoagents/.env. These tests consume provider quota. GEMINI_TEST_MODEL can
select a model available to the project.
"""

import os
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import BaseModel

from picoagents import Agent, GeminiChatCompletionClient
from picoagents.llm import BaseChatCompletionClient
from picoagents.messages import AssistantMessage, ToolMessage, UserMessage
from picoagents.orchestration import (
    AIOrchestrator,
    PlanBasedOrchestrator,
    RoundRobinOrchestrator,
)
from picoagents.termination import MaxMessageTermination, TextMentionTermination
from picoagents.types import AgentResponse, ChatCompletionChunk

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def client():
    dotenv = pytest.importorskip("dotenv")
    dotenv.load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        pytest.skip("Gemini API key not configured")
    instance = GeminiChatCompletionClient(
        model=os.getenv("GEMINI_TEST_MODEL", "gemini-3.1-flash-lite"),
        timeout=45,
        max_retries=2,
    )
    try:
        yield instance
    finally:
        await instance.client.close()


class Fact(BaseModel):
    city: str
    country: str


async def test_chat_and_structured_output(client):
    result = await client.create(
        [UserMessage(content="Reply with the single word HELLO.", source="user")]
    )
    assert "HELLO" in result.message.content.upper()
    assert result.usage.tokens_input > 0
    assert result.usage.tokens_output > 0
    assert result.usage.cost_estimate is None
    structured = await client.create(
        [
            UserMessage(
                content="Give the city Paris and its country France.", source="user"
            )
        ],
        output_format=Fact,
    )
    assert structured.structured_output == Fact(city="Paris", country="France")


async def test_streaming(client):
    chunks = [
        chunk
        async for chunk in client.create_stream(
            [UserMessage(content="Reply with the single word HELLO.", source="user")]
        )
    ]
    assert "HELLO" in "".join(c.content for c in chunks).upper()
    assert sum(c.is_complete for c in chunks) == 1
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.tokens_input > 0


def add_numbers(a: int, b: int) -> int:
    """Add two integers and return their sum."""
    return a + b


@pytest.mark.parametrize("stream", [False, True])
async def test_agent_tool_round_trip(client, stream):
    agent = Agent(
        name="calculator",
        instructions="Always call add_numbers for arithmetic. Report its result.",
        model_client=client,
        tools=[add_numbers],
        max_iterations=3,
    )
    if stream:
        events = [
            event
            async for event in agent.run_stream(
                "Use add_numbers to calculate 17 + 25.", stream_tokens=True
            )
        ]
        results = [event for event in events if isinstance(event, AgentResponse)]
        assert results
        result = results[-1]
        assert result.finish_reason != "error", result.messages[-1].content
        assert any(isinstance(event, ChatCompletionChunk) for event in events)
    else:
        result = await agent.run("Use add_numbers to calculate 17 + 25.")
    tool_results = [m for m in result.messages if isinstance(m, ToolMessage)]
    assert tool_results and tool_results[0].success
    assert "42" in tool_results[0].content
    assert "42" in result.messages[-1].content
    assert result.usage.llm_calls >= 2


def team(client):
    return [
        Agent(
            name="writer",
            description="Writes a concise sentence.",
            instructions="Write one brief sentence answering the task.",
            model_client=client,
        ),
        Agent(
            name="reviewer",
            description="Reviews a sentence for clarity.",
            instructions="Review the previous sentence briefly for clarity.",
            model_client=client,
        ),
    ]


@pytest.mark.parametrize("stream", [False, True])
async def test_round_robin(client, stream):
    orchestrator = RoundRobinOrchestrator(
        team(client), MaxMessageTermination(3), max_iterations=2
    )
    if stream:
        events = [
            event
            async for event in orchestrator.run_stream(
                "Explain why testing software is useful in one sentence."
            )
        ]
        from picoagents.types import OrchestrationResponse

        results = [
            event for event in events if isinstance(event, OrchestrationResponse)
        ]
        assert results
        result = results[-1]
    else:
        result = await orchestrator.run(
            "Explain why testing software is useful in one sentence."
        )
    assistants = [m for m in result.messages if isinstance(m, AssistantMessage)]
    assert [m.source for m in assistants] == ["writer", "reviewer"]
    assert all(m.content for m in assistants)
    assert result.stop_message.source == "MaxMessageTermination"
    assert result.usage.llm_calls >= 2


async def test_text_termination(client):
    agent = Agent(
        name="finisher", instructions="Reply with exactly DONE.", model_client=client
    )
    result = await RoundRobinOrchestrator(
        [agent], TextMentionTermination("DONE"), max_iterations=2
    ).run("Finish this task.")
    assert result.stop_message.source == "TextMentionTermination"


async def test_ai_orchestrator(client):
    orchestrator = AIOrchestrator(
        team(client), MaxMessageTermination(3), client, max_iterations=2
    )
    result = await orchestrator.run(
        "Have the writer explain software testing, then have the reviewer review it."
    )
    assert len(orchestrator.selection_history) == 2
    assert all(
        item["selected_agent"] in {"writer", "reviewer"}
        for item in orchestrator.selection_history
    )
    assert all(
        "fallback" not in item["reasoning"].lower()
        for item in orchestrator.selection_history
    )
    assert result.stop_message.source == "MaxMessageTermination"


async def test_plan_orchestrator(client, capsys):
    orchestrator = PlanBasedOrchestrator(
        team(client),
        MaxMessageTermination(100),
        client,
        max_iterations=2,
        max_step_retries=0,
    )
    result = await orchestrator.run(
        "Create exactly two steps: writer writes one sentence about software testing; "
        "reviewer reviews that sentence."
    )
    assert orchestrator.execution_plan is not None
    assert len(orchestrator.execution_plan.steps) == 2
    assert [s.agent_name for s in orchestrator.execution_plan.steps] == [
        "writer",
        "reviewer",
    ]
    assert all(
        "fallback" not in s.reasoning.lower() for s in orchestrator.execution_plan.steps
    )
    assert result.usage.llm_calls >= 2
    assert orchestrator.current_step_index == 2
    assert len(orchestrator.step_results) == 2
    assert "Warning:" not in capsys.readouterr().out


async def test_serialized_client_live_call(client):
    loaded = BaseChatCompletionClient.load_component(client.dump_component())
    try:
        assert isinstance(loaded, GeminiChatCompletionClient)
        result = await loaded.create([UserMessage(content="Say HELLO.", source="user")])
        assert "HELLO" in result.message.content.upper()
    finally:
        await loaded.client.close()

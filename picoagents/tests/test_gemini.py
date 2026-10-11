"""Exercise Gemini's adapter through the actual SDK without using API quota."""

import json

import httpx
import pytest
from pydantic import BaseModel

from picoagents import GeminiChatCompletionClient
from picoagents import Agent
from picoagents.llm import AuthenticationError, BaseChatCompletionClient, RateLimitError
from picoagents.messages import ToolMessage, UserMessage


class Answer(BaseModel):
    answer: str


def make_client(handler):
    return GeminiChatCompletionClient(
        api_key="test-gemini-key",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def response(message):
    return {
        "id": "completion-1",
        "object": "chat.completion",
        "created": 0,
        "model": "gemini-3.1-flash-lite",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
    }


def test_credentials_and_serialization(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-use")
    with pytest.raises(ValueError, match="Gemini API key"):
        GeminiChatCompletionClient()
    monkeypatch.setenv("GOOGLE_API_KEY", "google-key")
    assert GeminiChatCompletionClient().client.api_key == "google-key"
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    client = GeminiChatCompletionClient(timeout=42)
    assert client.client.api_key == "gemini-key"
    assert client._to_config().api_key is None
    exported = client.dump_component()
    assert exported.provider == "picoagents.llm.GeminiChatCompletionClient"
    loaded = BaseChatCompletionClient.load_component(exported)
    assert isinstance(loaded, GeminiChatCompletionClient)
    assert loaded.client.api_key == "gemini-key"
    assert loaded.config["timeout"] == 42
    explicit = GeminiChatCompletionClient(api_key="explicit")
    assert explicit.client.api_key == "explicit"
    assert explicit._to_config().api_key == "explicit"


@pytest.mark.asyncio
async def test_structured_completion():
    def handler(request):
        assert str(request.url) == (
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        )
        assert request.headers["authorization"] == "Bearer test-gemini-key"
        body = json.loads(request.content)
        assert body["model"] == "gemini-3.1-flash-lite"
        assert body["messages"][0]["content"] == "Hello"
        assert body["temperature"] == 0.2
        assert body["response_format"]["type"] == "json_schema"
        return httpx.Response(
            200, json=response({"role": "assistant", "content": '{"answer":"hello"}'})
        )

    client = make_client(handler)
    try:
        result = await client.create(
            [UserMessage(content="Hello", source="user")],
            output_format=Answer,
            temperature=0.2,
        )
        assert result.structured_output == Answer(answer="hello")
        assert result.usage.tokens_input == 12
        assert result.usage.tokens_output == 5
        assert result.usage.cost_estimate is None
    finally:
        await client.client.close()


@pytest.mark.asyncio
async def test_function_call():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "weather",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    def handler(request):
        body = json.loads(request.content)
        assert body["tools"] == tools
        assert body["tool_choice"] == "auto"
        return httpx.Response(
            200,
            json=response(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "extra_content": {
                                "google": {"thought_signature": "signature-1"}
                            },
                            "function": {
                                "name": "weather",
                                "arguments": '{"city":"Paris"}',
                            },
                        }
                    ],
                }
            ),
        )

    client = make_client(handler)
    try:
        result = await client.create(
            [UserMessage(content="Weather?", source="user")], tools
        )
        assert result.message.tool_calls[0].parameters == {"city": "Paris"}
        assert result.message.tool_calls[0].call_id == "call-1"
        metadata = {"google": {"thought_signature": "signature-1"}}
        assert result.message.tool_calls[0].extra_content == metadata
        restored_message = type(result.message).model_validate_json(
            result.message.model_dump_json()
        )
        converted = client._convert_messages_to_api_format(
            [
                restored_message,
                ToolMessage(
                    content="Sunny",
                    source="tool",
                    tool_name="weather",
                    tool_call_id="call-1",
                    success=True,
                ),
            ]
        )
        assert converted[0]["tool_calls"][0]["extra_content"] == metadata
        assert converted[1]["name"] == "weather"
        assert result.usage.tool_calls == 1
    finally:
        await client.client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("usage_location", ["separate", "choice", "none"])
async def test_stream_completion_with_or_without_usage(usage_location):
    include_usage = usage_location != "none"
    events = [
        {
            "id": "c",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "gemini-3.1-flash-lite",
            "choices": [
                {"index": 0, "delta": {"content": "Hello"}, "finish_reason": None}
            ],
        },
        {
            "id": "c",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "gemini-3.1-flash-lite",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        },
    ]
    if usage_location == "choice":
        events[-1]["usage"] = {
            "prompt_tokens": 12,
            "completion_tokens": 5,
            "total_tokens": 17,
        }
    if usage_location == "separate":
        events.append(
            {
                "id": "c",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "gemini-3.1-flash-lite",
                "choices": [],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 5,
                    "total_tokens": 17,
                },
            }
        )
    payload = "".join(f"data: {json.dumps(event)}\n\n" for event in events)
    client = make_client(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=payload + "data: [DONE]\n\n",
        )
    )
    try:
        chunks = [
            chunk
            async for chunk in client.create_stream(
                [UserMessage(content="Hi", source="user")],
                stream_options={"include_usage": include_usage},
            )
        ]
        assert "".join(chunk.content for chunk in chunks) == "Hello"
        assert sum(chunk.is_complete for chunk in chunks) == 1
        if include_usage:
            assert chunks[-1].usage.tokens_input == 12
    finally:
        await client.client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,error", [(401, AuthenticationError), (429, RateLimitError)]
)
async def test_provider_errors(status, error):
    client = make_client(
        lambda request: httpx.Response(
            status, json={"error": {"message": "Provider failure", "type": "api_error"}}
        )
    )
    try:
        with pytest.raises(error):
            await client.create([UserMessage(content="Hi", source="user")])
    finally:
        await client.client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_agent_preserves_thought_signature(stream):
    metadata = {"google": {"thought_signature": "opaque-signature"}}
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "extra_content": metadata,
                        "function": {"name": "add", "arguments": '{"a":17,"b":25}'},
                    }
                ],
            }
        else:
            assistant = next(m for m in body["messages"] if m.get("tool_calls"))
            assert assistant["tool_calls"][0]["extra_content"] == metadata
            message = {"role": "assistant", "content": "42"}
        if not stream:
            return httpx.Response(200, json=response(message))
        delta = dict(message)
        if "tool_calls" in delta:
            delta["tool_calls"][0]["index"] = 0
        event = {
            "id": "c",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "gemini-3.1-flash-lite",
            "choices": [{"index": 0, "delta": delta, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17},
        }
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=f"data: {json.dumps(event)}\n\ndata: [DONE]\n\n",
        )

    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    client = make_client(handler)
    agent = Agent(
        name="calculator", instructions="Use add.", model_client=client, tools=[add]
    )
    try:
        if stream:
            from picoagents.types import AgentResponse

            events = [
                event async for event in agent.run_stream("17 + 25", stream_tokens=True)
            ]
            result = next(event for event in events if isinstance(event, AgentResponse))
        else:
            result = await agent.run("17 + 25")
        assert result.messages[-1].content == "42"
        assert len(requests) == 2
    finally:
        await client.client.close()

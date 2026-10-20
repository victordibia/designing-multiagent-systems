"""Exercise the research factory, agent dispatcher and real MCP HTTP transport.

The scripted model is deterministic; it does not test live model reasoning.
"""

import asyncio
import json
from uuid import UUID

import pytest

pytest.importorskip("mcp")

from mcp.shared import _httpx_utils

from picoagents import Agent
from picoagents.context import AgentContext
from picoagents.llm import BaseChatCompletionClient
from picoagents.messages import (
    AssistantMessage,
    ToolCallRequest,
    ToolMessage,
    UserMessage,
)
from picoagents.tools import ApprovalMode, create_research_tools
from picoagents.tools._research_tools import WebSearchTool
from picoagents.types import ChatCompletionResult, Usage


class SearchModel(BaseChatCompletionClient):
    """Request a search, then consume its result in a second model call."""

    def __init__(self):
        super().__init__(model="scripted-search-test")
        self.consumed = []

    async def create(self, messages, tools=None, **kwargs):
        if isinstance(messages[-1], ToolMessage):
            self.consumed.append(messages[-1])
            message = AssistantMessage(content=messages[-1].content, source="scripted")
        else:
            query = next(
                m.content for m in reversed(messages) if isinstance(m, UserMessage)
            )
            message = AssistantMessage(
                content="Searching",
                source="scripted",
                tool_calls=[
                    ToolCallRequest(
                        call_id="search",
                        tool_name="web_search",
                        parameters={"query": query},
                    )
                ],
            )
        return ChatCompletionResult(
            message=message,
            model=self.model,
            usage=Usage(duration_ms=0),
            finish_reason="stop",
        )

    async def create_stream(self, *args, **kwargs):
        raise NotImplementedError(
            "This fixture exercises non-token-streaming Agent.run"
        )
        yield  # pragma: no cover


def make_agent(tools=None):
    return Agent(
        name="researcher",
        instructions="Search and cite sources.",
        model_client=SearchModel(),
        tools=list(create_research_tools()) if tools is None else tools,
    )


@pytest.fixture
def wire(monkeypatch):
    # MCP 2.0 used httpx; newer SDKs use httpx2. Exercise the SDK's actual
    # HTTP implementation in either case, without adding another dependency.
    http = vars(_httpx_utils).get("httpx2") or vars(_httpx_utils)["httpx"]

    class Server:
        def __init__(self):
            self.requests = []
            self.calls = []
            self.mode = "normal"
            self.started = asyncio.Event()
            self.cancelled = False
            self.clients = []

        async def handle(self, request):
            payload = json.loads(request.content) if request.content else {}
            self.requests.append((request, payload))
            method = payload.get("method")
            response = {"jsonrpc": "2.0", "id": payload.get("id")}
            if method == "server/discover":
                response["error"] = {"code": -32601, "message": "Legacy server"}
            elif method == "initialize":
                response["result"] = {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fixture", "version": "1"},
                }
            elif method == "tools/list":
                response["result"] = {
                    "tools": [{"name": "web_search", "inputSchema": {"type": "object"}}]
                }
            elif method == "tools/call":
                self.calls.append(payload["params"])
                self.started.set()
                await asyncio.sleep(0)  # Allow concurrent conversations to interleave.
                if self.mode == "network":
                    raise http.ConnectError("offline", request=request)
                if self.mode == "block":
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        self.cancelled = True
                        raise
                data = {
                    "results": [
                        {
                            "title": "Python release",
                            "url": "https://docs.python.org:443/3/whatsnew/",
                            "excerpts": ["Release details", "Source excerpt"],
                        },
                        {
                            "title": "Blocked",
                            "url": "https://blocked.python.org/page",
                            "excerpts": ["blocked"],
                        },
                        {
                            "title": "Wrong scheme",
                            "url": "file:///etc/passwd",
                            "excerpts": ["invalid"],
                        },
                        {
                            "title": "Other",
                            "url": "https://example.net/page",
                            "excerpts": ["other"],
                        },
                    ]
                }
                if self.mode == "malformed":
                    data = {"unexpected": True}
                text = (
                    "Free anonymous quota exceeded"
                    if self.mode == "error"
                    else json.dumps(data)
                )
                response["result"] = {
                    "content": [{"type": "text", "text": text}],
                    "isError": self.mode == "error",
                }
                if self.mode not in ("text", "error"):
                    response["result"]["structuredContent"] = data
            elif method == "notifications/initialized":
                return http.Response(202)
            else:
                return http.Response(405)
            return http.Response(200, json=response)

        def client(self, headers=None, **kwargs):
            client = http.AsyncClient(
                headers=headers, transport=http.MockTransport(self.handle)
            )
            self.clients.append(client)
            return client

    server = Server()
    monkeypatch.setattr(_httpx_utils, "create_mcp_http_client", server.client)
    monkeypatch.setenv("TAVILY_API_KEY", "ambient-unused")
    monkeypatch.setenv("PARALLEL_API_KEY", "ambient-unused")
    return server


def selected(**kwargs):
    return [t for t in create_research_tools(**kwargs) if t.name == "web_search"]


def test_provider_resolution():
    assert selected()[0].provider == "parallel"
    assert selected(tavily_api_key="saved-key")[0].provider == "tavily"
    assert not selected(google_api_key="google", google_cse_id="cse")
    assert (
        selected(tavily_api_key="key", web_search_provider="parallel")[0].provider
        == "parallel"
    )
    assert selected(web_search_provider="tavily")[0].provider == "tavily"
    assert not selected(web_search_provider="disabled")
    assert not selected(tavily_api_key="key", web_search_provider="disabled")
    assert WebSearchTool(api_key="saved-key").provider == "tavily"
    with pytest.raises(ValueError):
        create_research_tools(web_search_provider="unknown")


@pytest.mark.asyncio
async def test_factory_agent_consumes_anonymous_search(wire):
    agent = make_agent()
    result = await agent.run("Python latest release details")
    assert result.finish_reason == "stop"
    assert "Release details" in result.messages[-1].content
    assert (
        "https://docs.python.org:443/3/whatsnew/"
        in agent.model_client.consumed[0].content
    )
    assert agent.model_client.consumed[0].success
    assert wire.calls[0]["name"] == "web_search"
    args = wire.calls[0]["arguments"]
    assert args["objective"] == "Python latest release details"
    assert args["search_queries"] == [args["objective"]]
    UUID(args["session_id"])
    assert (
        len(wire.requests) >= 3
    )  # Negotiation and search pass through real HTTP transport.
    for request, _ in wire.requests:
        assert str(request.url) == "https://search.parallel.ai/mcp"
        assert request.headers["user-agent"].startswith("picoagents (")
        assert "authorization" not in request.headers
    assert all(client.is_closed for client in wire.clients)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["normal", "text"])
async def test_result_contract_and_domain_rules(wire, mode):
    wire.mode = mode
    tool = WebSearchTool(
        allowed_domains=["python.org"], blocked_domains=["blocked.python.org"]
    )
    result = await tool.execute({"query": "Python release", "max_results": 1})
    assert result.success
    assert result.result == [
        {
            "title": "Python release",
            "url": "https://docs.python.org:443/3/whatsnew/",
            "snippet": "Release details\nSource excerpt",
        }
    ]
    assert result.metadata["filtered"] == 3
    assert not tool._is_domain_allowed("https://python.org.evil.com/page")
    assert not tool._is_domain_allowed("javascript:alert(1)")
    assert not tool._is_domain_allowed("missing-scheme")


@pytest.mark.asyncio
async def test_conversation_followups_retry_concurrency_and_reset(wire):
    agent = make_agent()  # One shared agent and tool instance for all conversations.
    first = await agent.run("first conversation")
    first_id = wire.calls[-1]["arguments"]["session_id"]
    wire.mode = "error"
    await agent.run("quota response", context=first.context)
    assert wire.calls[-1]["arguments"]["session_id"] == first_id
    wire.mode = "normal"
    followup = await agent.run("retry and follow up", context=first.context)
    assert wire.calls[-1]["arguments"]["session_id"] == first_id
    second = await agent.run("second conversation")
    second_id = wire.calls[-1]["arguments"]["session_id"]
    assert first_id != second_id
    await asyncio.gather(
        agent.run("first interleaved", context=followup.context),
        agent.run("second interleaved", context=second.context),
    )
    identities = {
        c["arguments"]["objective"]: c["arguments"]["session_id"] for c in wire.calls
    }
    assert identities["first interleaved"] == first_id
    assert identities["second interleaved"] == second_id
    first.context.reset()
    await agent.run("after reset", context=first.context)
    assert wire.calls[-1]["arguments"]["session_id"] not in (first_id, second_id)
    assert not agent.context.metadata  # No shared-instance mutation.


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["error", "malformed", "network"])
async def test_errors_reach_agent_without_fallback(wire, mode):
    wire.mode = mode
    agent = make_agent()
    await agent.run("failed search")
    assert not agent.model_client.consumed[-1].success
    assert "Parallel search failed" in agent.model_client.consumed[-1].content
    assert len(wire.calls) == 1
    assert all(client.is_closed for client in wire.clients)


@pytest.mark.asyncio
async def test_timeout_cancels_transport(wire):
    wire.mode = "block"
    agent = make_agent([WebSearchTool(timeout=0.2)])
    await agent.run("timeout")
    assert "timed out" in agent.model_client.consumed[-1].content
    assert wire.cancelled
    assert all(client.is_closed for client in wire.clients)


@pytest.mark.asyncio
async def test_agent_cancellation_interrupts_inflight_search(wire):
    from picoagents import CancellationToken

    wire.mode = "block"
    token = CancellationToken()
    task = asyncio.create_task(make_agent().run("cancel", cancellation_token=token))
    await asyncio.wait_for(wire.started.wait(), 5)
    token.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert wire.cancelled
    assert all(client.is_closed for client in wire.clients)


@pytest.mark.asyncio
async def test_approval_and_missing_tool_prevent_network(wire):
    tool = WebSearchTool()
    tool.approval_mode = ApprovalMode.ALWAYS
    agent = make_agent([tool])
    paused = await agent.run("approval required")
    assert paused.needs_approval
    assert not wire.requests
    request = paused.approval_requests[0]
    paused.context.add_approval_response(request.create_response(approved=False))
    await agent.run(context=paused.context)
    assert not wire.requests
    await make_agent([]).run("search disabled")
    assert not wire.requests


@pytest.mark.asyncio
async def test_tavily_credentials_and_explicit_missing_key_do_not_fallback(
    wire, monkeypatch
):
    import httpx

    seen = []

    async def handle(request):
        seen.append(request)
        return httpx.Response(401, json={"error": "bad key"})

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda: original(transport=httpx.MockTransport(handle))
    )
    agent = make_agent(list(create_research_tools(tavily_api_key="configured-key")))
    await agent.run("configured search")
    assert not agent.model_client.consumed[-1].success
    assert str(seen[0].url) == "https://api.tavily.com/search"
    assert json.loads(seen[0].content)["api_key"] == "configured-key"
    assert not wire.requests
    result = await WebSearchTool(provider="tavily").execute({"query": "missing key"})
    assert not result.success and "Tavily API key" in result.error
    assert not wire.requests


@pytest.mark.asyncio
async def test_approved_search_runs_and_standalone_ids_are_distinct(wire):
    tool = WebSearchTool()
    tool.approval_mode = ApprovalMode.ALWAYS
    agent = make_agent([tool])
    paused = await agent.run("approve search")
    paused.context.add_approval_response(
        paused.approval_requests[0].create_response(approved=True)
    )
    await agent.run(context=paused.context)
    assert wire.calls
    await tool.execute({"query": "standalone first"})
    first = wire.calls[-1]["arguments"]["session_id"]
    await tool.execute({"query": "standalone second"})
    assert wire.calls[-1]["arguments"]["session_id"] != first


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, True, "five"])
async def test_invalid_result_limit_does_not_send_request(wire, limit):
    result = await WebSearchTool().execute({"query": "test", "max_results": limit})
    assert not result.success
    assert not wire.requests


@pytest.mark.asyncio
async def test_configured_tavily_success_keeps_result_contract(wire, monkeypatch):
    import httpx

    async def handle(request):
        assert str(request.url) == "https://api.tavily.com/search"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Existing",
                        "url": "https://example.com",
                        "content": "Tavily snippet",
                    }
                ]
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda: original(transport=httpx.MockTransport(handle))
    )
    tool = selected(tavily_api_key="saved-key")[0]
    result = await tool.execute({"query": "configured search"})
    assert result.success
    assert result.result == [
        {"title": "Existing", "url": "https://example.com", "snippet": "Tavily snippet"}
    ]
    assert not wire.requests


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_anonymous_factory_agent():
    """Opt-in live transport + scripted model; no LLM API credential required."""
    agent = make_agent()
    await agent.run("Python official latest release documentation")
    consumed = agent.model_client.consumed[-1]
    assert consumed.success, consumed.error
    assert "https://" in consumed.content

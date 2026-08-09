"""
Tests for the MCP SDK 2.0 integration (protocol 2026-07-28).

Covers the migrated MCPClientManager against the lab servers in
examples/mcp_lab/, across three layers:

1. In-memory transport - fast matrix: discovery, tool calls, structured
   output, wire tap, MRTR (elicitation) round trips
2. stdio transport - subprocess reality using the actual lab server files
3. Streamable HTTP transport - network reality against a spawned server

The lab servers double as WebUI playground presets; these tests are the
proof that the presets work.
"""

import importlib.util
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="MCP not installed, skipping MCP tests")

import mcp.types  # noqa: E402

if not hasattr(mcp.types, "DiscoverRequest"):
    pytest.skip("mcp SDK 2.0 required", allow_module_level=True)

from mcp.types import ElicitResult  # noqa: E402

from picoagents.tools import (  # noqa: E402
    HTTPServerConfig,
    InMemoryServerConfig,
    MCPClientManager,
    StdioServerConfig,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LAB_DIR = REPO_ROOT / "examples" / "mcp_lab"


def load_lab_server(filename: str):
    """Import a lab server module and return its `server` instance."""
    path = LAB_DIR / filename
    spec = importlib.util.spec_from_file_location(f"lab_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.server


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ============================================================================
# In-memory: discovery, server info, tools
# ============================================================================


@pytest.mark.anyio
async def test_connect_discovers_tools_statelessly():
    manager = MCPClientManager()
    manager.add_server(
        InMemoryServerConfig(server_id="lab", server=load_lab_server("basic_server.py"))
    )
    await manager.connect("lab")
    try:
        assert manager.is_connected("lab")

        info = manager.get_server_info("lab")
        assert info["protocol_version"] == "2026-07-28"
        assert info["server_info"]["name"] == "pico-lab-basic"

        names = [t.name for t in manager.get_tools("lab")]
        assert names == ["mcp_lab_add", "mcp_lab_word_stats", "mcp_lab_slow_echo"]
    finally:
        await manager.disconnect_all()

    assert not manager.is_connected("lab")


@pytest.mark.anyio
async def test_tool_execution_and_structured_output():
    manager = MCPClientManager()
    manager.add_server(
        InMemoryServerConfig(server_id="lab", server=load_lab_server("basic_server.py"))
    )
    async with manager.managed_connection("lab"):
        tools = {t.mcp_tool_name: t for t in manager.get_tools("lab")}

        result = await tools["add"].execute({"a": 2, "b": 40})
        assert result.success is True
        assert result.result == {"result": 42.0}

        result = await tools["word_stats"].execute({"text": "hello brave new world"})
        assert result.success is True
        assert result.result["words"] == 4
        assert result.result["longest_word"] == "hello"


@pytest.mark.anyio
async def test_tool_llm_format_exposes_mcp_schema():
    manager = MCPClientManager()
    manager.add_server(
        InMemoryServerConfig(server_id="lab", server=load_lab_server("basic_server.py"))
    )
    async with manager.managed_connection("lab"):
        tool = next(
            t for t in manager.get_tools("lab") if t.mcp_tool_name == "add"
        )
        llm_format = tool.to_llm_format()
        params = llm_format["function"]["parameters"]
        assert set(params["properties"].keys()) == {"a", "b"}
        assert llm_format["function"]["name"] == "mcp_lab_add"


# ============================================================================
# Wire tap: the stateless flow is visible on the wire
# ============================================================================


@pytest.mark.anyio
async def test_wire_tap_records_stateless_flow():
    frames_seen = []
    manager = MCPClientManager(
        enable_wire_tap=True,
        on_frame=lambda sid, frame: frames_seen.append((sid, frame)),
    )
    manager.add_server(
        InMemoryServerConfig(server_id="lab", server=load_lab_server("basic_server.py"))
    )
    async with manager.managed_connection("lab"):
        tools = {t.mcp_tool_name: t for t in manager.get_tools("lab")}
        await tools["add"].execute({"a": 1, "b": 2})

        frames = manager.get_wire_frames("lab")
        assert len(frames) >= 6  # discover, tools/list, tools/call + responses
        methods = [f["message"].get("method") for f in frames if f["direction"] == "out"]

        # 2026-07-28: negotiation is server/discover; no initialize handshake
        assert methods[0] == "server/discover"
        assert "initialize" not in methods
        assert "tools/call" in methods

        for frame in frames:
            assert frame["direction"] in ("in", "out")
            assert isinstance(frame["timestamp"], float)

    # on_frame observer saw the same traffic
    assert len(frames_seen) == len(frames)


# ============================================================================
# MRTR: mid-call input via elicitation
# ============================================================================


@pytest.mark.anyio
async def test_mrtr_confirmation_accepted():
    asked = {}

    async def handler(server_id, params):
        asked["server_id"] = server_id
        asked["message"] = params.message
        return ElicitResult(action="accept", content={"confirm": True})

    manager = MCPClientManager(elicitation_handler=handler)
    manager.add_server(
        InMemoryServerConfig(server_id="mrtr", server=load_lab_server("mrtr_server.py"))
    )
    async with manager.managed_connection("mrtr"):
        tool = manager.get_tools("mrtr")[0]
        result = await tool.execute({"pattern": "temp_*"})

        assert result.success is True
        assert "Deleted 3 records" in result.result["result"]
        assert asked["server_id"] == "mrtr"
        assert "temp_*" in asked["message"]


@pytest.mark.anyio
async def test_mrtr_confirmation_denied_aborts():
    async def handler(server_id, params):
        return ElicitResult(action="accept", content={"confirm": False})

    manager = MCPClientManager(elicitation_handler=handler)
    manager.add_server(
        InMemoryServerConfig(server_id="mrtr", server=load_lab_server("mrtr_server.py"))
    )
    async with manager.managed_connection("mrtr"):
        tool = manager.get_tools("mrtr")[0]
        result = await tool.execute({"pattern": "temp_*"})

        assert result.success is True
        assert "Aborted" in result.result["result"]


@pytest.mark.anyio
async def test_mrtr_decline_without_handler_fails_cleanly():
    manager = MCPClientManager()  # no elicitation handler
    manager.add_server(
        InMemoryServerConfig(server_id="mrtr", server=load_lab_server("mrtr_server.py"))
    )
    async with manager.managed_connection("mrtr"):
        tool = manager.get_tools("mrtr")[0]
        result = await tool.execute({"pattern": "temp_*"})

        # The call must not hang or raise - it fails as a clean ToolResult
        assert result.success is False


# ============================================================================
# Lifecycle
# ============================================================================


@pytest.mark.anyio
async def test_remove_server_requires_disconnect():
    manager = MCPClientManager()
    manager.add_server(
        InMemoryServerConfig(server_id="lab", server=load_lab_server("basic_server.py"))
    )
    await manager.connect("lab")
    with pytest.raises(ValueError, match="disconnect first"):
        manager.remove_server("lab")
    await manager.disconnect("lab")
    manager.remove_server("lab")
    assert manager.list_servers() == []


@pytest.mark.anyio
async def test_connect_failure_raises_connection_error():
    manager = MCPClientManager()
    manager.add_server(
        StdioServerConfig(server_id="bad", command=sys.executable, args=["-c", "exit(1)"])
    )
    with pytest.raises(ConnectionError):
        await manager.connect("bad")
    assert not manager.is_connected("bad")


# ============================================================================
# stdio transport: subprocess reality
# ============================================================================


@pytest.mark.anyio
async def test_stdio_transport_against_lab_server():
    manager = MCPClientManager(enable_wire_tap=True)
    manager.add_server(
        StdioServerConfig(
            server_id="stdio_lab",
            command=sys.executable,
            args=[str(LAB_DIR / "basic_server.py")],
        )
    )
    async with manager.managed_connection("stdio_lab"):
        info = manager.get_server_info("stdio_lab")
        assert info["protocol_version"] == "2026-07-28"

        tools = {t.mcp_tool_name: t for t in manager.get_tools("stdio_lab")}
        result = await tools["add"].execute({"a": 20, "b": 22})
        assert result.success is True
        assert result.result == {"result": 42.0}

        methods = [
            f["message"].get("method")
            for f in manager.get_wire_frames("stdio_lab")
            if f["direction"] == "out"
        ]
        assert methods[0] == "server/discover"


# ============================================================================
# Streamable HTTP transport: network reality
# ============================================================================


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 15.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"server on port {port} did not come up")


@pytest.fixture
def http_lab_server():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(LAB_DIR / "basic_server.py"), "--http", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(port)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.mark.anyio
async def test_streamable_http_transport_against_lab_server(http_lab_server):
    manager = MCPClientManager()
    manager.add_server(
        HTTPServerConfig(server_id="http_lab", url=http_lab_server)
    )
    async with manager.managed_connection("http_lab"):
        info = manager.get_server_info("http_lab")
        assert info["protocol_version"] == "2026-07-28"

        tools = {t.mcp_tool_name: t for t in manager.get_tools("http_lab")}
        result = await tools["word_stats"].execute({"text": "streamable http works"})
        assert result.success is True
        assert result.result["words"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ============================================================================
# MCP Apps (io.modelcontextprotocol/ui)
# ============================================================================


@pytest.mark.anyio
async def test_mcp_app_is_advertised_discovered_and_readable():
    """The SDK has no client-side Apps support: advertising the extension is
    what makes a server annotate its tools, and the caller reads the resource."""
    from picoagents.tools._mcp._client import app_resource_uri

    manager = MCPClientManager()
    manager.add_server(
        InMemoryServerConfig(server_id="apps", server=load_lab_server("apps_server.py"))
    )
    async with manager.managed_connection("apps"):
        client = await manager.get_client("apps")
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert "sales_dashboard" in tools

        uri = app_resource_uri(getattr(tools["sales_dashboard"], "meta", None))
        assert uri == "ui://sales/app.html"

        html = await manager.read_app_resource("apps", uri)
        assert html is not None
        # The app speaks the ext-apps bridge: handshake then tools/call
        assert "ui/initialize" in html
        assert "tools/call" in html


@pytest.mark.anyio
async def test_app_bridge_tool_is_callable_by_the_host():
    """The app calls query_sales over the bridge; the host proxies it here."""
    manager = MCPClientManager()
    manager.add_server(
        InMemoryServerConfig(server_id="apps", server=load_lab_server("apps_server.py"))
    )
    async with manager.managed_connection("apps"):
        client = await manager.get_client("apps")
        result = await client.call_tool(
            "query_sales", arguments={"region": "europe", "metric": "units"}
        )
        # MCPServer wraps a dict return under "result"
        payload = result.structured_content["result"]
        assert payload["region"] == "europe"
        assert payload["metric"] == "units"
        assert len(payload["values"]) == len(payload["months"])
        assert payload["total"] == sum(payload["values"])


@pytest.mark.anyio
async def test_tool_without_an_app_has_no_resource_uri():
    from picoagents.tools._mcp._client import app_resource_uri

    manager = MCPClientManager()
    manager.add_server(
        InMemoryServerConfig(server_id="lab", server=load_lab_server("basic_server.py"))
    )
    async with manager.managed_connection("lab"):
        client = await manager.get_client("lab")
        tool = next(t for t in (await client.list_tools()).tools if t.name == "add")
        assert app_resource_uri(getattr(tool, "meta", None)) is None


# ============================================================================
# Authorization: OAuth 2.0 protected resource
# ============================================================================


@pytest.fixture
def http_auth_server():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(LAB_DIR / "auth_server.py"), "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_port(port)
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_unauthenticated_request_gets_a_challenge(http_auth_server):
    """The 2026 spec models servers as OAuth resource servers: refuse, and say
    where the metadata lives."""
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        f"{http_auth_server}/mcp",
        method="POST",
        data=b'{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{}}',
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        urllib.request.urlopen(request)
        pytest.fail("expected 401")
    except urllib.error.HTTPError as e:
        assert e.code == 401
        challenge = e.headers.get("WWW-Authenticate", "")
        assert "Bearer" in challenge
        assert "resource_metadata=" in challenge

    # RFC 9728 document is mounted automatically
    with urllib.request.urlopen(
        f"{http_auth_server}/.well-known/oauth-protected-resource"
    ) as response:
        metadata = json.loads(response.read())
    assert metadata["scopes_supported"] == ["sales:read"]
    assert metadata["authorization_servers"]


@pytest.mark.anyio
async def test_bearer_token_is_accepted(http_auth_server):
    manager = MCPClientManager()
    manager.add_server(
        HTTPServerConfig(
            server_id="auth",
            url=f"{http_auth_server}/mcp",
            headers={"Authorization": "Bearer pico-lab-token"},
        )
    )
    async with manager.managed_connection("auth"):
        tools = {t.mcp_tool_name: t for t in manager.get_tools("auth")}
        result = await tools["whoami"].execute({})
        assert "lab-user" in result.result["result"]


@pytest.mark.anyio
async def test_missing_token_surfaces_a_readable_error(http_auth_server):
    """A TaskGroup's own message says nothing; the cause must reach the caller."""
    manager = MCPClientManager()
    manager.add_server(
        HTTPServerConfig(server_id="auth", url=f"{http_auth_server}/mcp")
    )
    with pytest.raises(ConnectionError) as excinfo:
        await manager.connect("auth")
    message = str(excinfo.value)
    assert "unhandled errors in a TaskGroup" not in message
    assert "auth" in message

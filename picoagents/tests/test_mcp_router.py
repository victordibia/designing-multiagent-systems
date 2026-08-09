"""
Tests for the WebUI MCP playground router (/api/mcp).

Uses FastAPI's TestClient against the real WebUI app, with the lab servers
from examples/mcp_lab/ spawned over stdio - the same path the UI exercises.
"""

import sys
import threading
import time

import pytest

pytest.importorskip("mcp", reason="MCP not installed, skipping MCP tests")
pytest.importorskip("fastapi", reason="FastAPI not installed, skipping WebUI tests")

import mcp.types  # noqa: E402

if not hasattr(mcp.types, "DiscoverRequest"):
    pytest.skip("mcp SDK 2.0 required", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from picoagents.webui._server import PicoAgentsWebUIServer  # noqa: E402

from picoagents.webui.mcp.servers import SERVERS_DIR as LAB_DIR  # noqa: E402


@pytest.fixture
def client():
    server = PicoAgentsWebUIServer(entities_dir=None)
    app = server.create_app()
    with TestClient(app) as test_client:
        yield test_client


def _add_lab_server(client: TestClient, server_id: str, filename: str) -> None:
    response = client.post(
        "/api/mcp/servers",
        json={
            "server_id": server_id,
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(LAB_DIR / filename)],
        },
    )
    assert response.status_code == 200, response.text


# ============================================================================
# Support matrix + presets
# ============================================================================


def test_spec_support_is_probed_from_the_installed_sdk(client):
    """Support is derived from the installed package, never a curated table."""
    data = client.get("/api/mcp/support").json()
    assert data["sdk"] == "python"
    assert data["protocol_version"] == "2026-07-28"
    assert data["version"] != "unknown"

    features = {f["key"]: f for f in data["features"]}
    # Every feature carries display copy so the UI needs no second source
    assert all(f["label"] and f["description"] for f in features.values())

    # What SDK 2.0 verifiably ships today
    assert features["stateless-core"]["status"] == "shipped"
    assert features["mrtr"]["status"] == "shipped"
    assert features["tasks-types"]["status"] == "shipped"
    # The honest gap: wire types exist, the client runtime does not
    assert features["tasks"]["status"] == "missing"


def test_presets_include_lab_servers(client):
    presets = {p["server_id"]: p for p in client.get("/api/mcp/presets").json()}
    assert set(presets) >= {"basic", "mrtr", "notify", "apps", "auth"}

    # stdio presets are self-launching: command + args are enough
    assert all(presets[k]["command"] for k in ("basic", "mrtr", "notify", "apps"))

    # auth is HTTP-only (bearer auth is meaningless over stdio) and must be
    # started separately, so it carries a url and an instruction note
    assert presets["auth"]["transport"] == "streamable-http"
    assert presets["auth"]["url"].endswith("/mcp")
    assert "Start it first" in presets["auth"]["note"]


# ============================================================================
# Server lifecycle
# ============================================================================


def test_add_connect_call_disconnect_remove(client):
    _add_lab_server(client, "lab", "basic_server.py")

    servers = client.get("/api/mcp/servers").json()
    assert servers[0]["server_id"] == "lab"
    assert servers[0]["status"] == "disconnected"

    info = client.post("/api/mcp/servers/lab/connect").json()
    assert info["protocol_version"] == "2026-07-28"
    assert info["server_info"]["name"] == "pico-lab-basic"
    assert [t["name"] for t in info["tools"]] == ["add", "word_stats", "slow_echo"]

    tools = client.get("/api/mcp/servers/lab/tools").json()
    add_tool = next(t for t in tools if t["name"] == "add")
    assert set(add_tool["input_schema"]["properties"].keys()) == {"a", "b"}

    result = client.post(
        "/api/mcp/servers/lab/tools/add/call", json={"arguments": {"a": 20, "b": 22}}
    ).json()
    assert result["is_error"] is False
    assert result["structured_content"] == {"result": 42.0}

    frames = client.get("/api/mcp/servers/lab/wire").json()
    out_methods = [f["message"].get("method") for f in frames if f["direction"] == "out"]
    assert out_methods[0] == "server/discover"
    assert "tools/call" in out_methods

    assert client.post("/api/mcp/servers/lab/disconnect").json()["status"] == "disconnected"
    assert client.delete("/api/mcp/servers/lab").json()["status"] == "removed"
    assert client.get("/api/mcp/servers").json() == []


def test_error_paths(client):
    # unknown server
    assert client.post("/api/mcp/servers/nope/connect").status_code == 404
    assert client.get("/api/mcp/servers/nope/wire").status_code == 404

    # bad transport / missing fields
    response = client.post(
        "/api/mcp/servers", json={"server_id": "x", "transport": "carrier-pigeon"}
    )
    assert response.status_code == 400
    response = client.post("/api/mcp/servers", json={"server_id": "x", "transport": "stdio"})
    assert response.status_code == 400

    # calls against a registered but disconnected server
    _add_lab_server(client, "lab", "basic_server.py")
    assert client.get("/api/mcp/servers/lab/tools").status_code == 409

    # duplicate registration
    response = client.post(
        "/api/mcp/servers",
        json={
            "server_id": "lab",
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(LAB_DIR / "basic_server.py")],
        },
    )
    assert response.status_code == 409

    # connect failure surfaces as 502
    client.post(
        "/api/mcp/servers",
        json={
            "server_id": "bad",
            "transport": "stdio",
            "command": sys.executable,
            "args": ["-c", "exit(1)"],
        },
    )
    assert client.post("/api/mcp/servers/bad/connect").status_code == 502


# ============================================================================
# MRTR: park -> pending input -> reply -> resumed call
# ============================================================================


def test_mrtr_park_and_reply_flow(client):
    _add_lab_server(client, "mrtr", "mrtr_server.py")
    assert client.post("/api/mcp/servers/mrtr/connect").status_code == 200

    call_result = {}

    def invoke():
        call_result["response"] = client.post(
            "/api/mcp/servers/mrtr/tools/delete_records/call",
            json={"arguments": {"pattern": "temp_*"}},
        ).json()

    call_thread = threading.Thread(target=invoke)
    call_thread.start()

    # The call parks: a pending input appears
    pending = []
    deadline = time.time() + 10
    while time.time() < deadline:
        pending = client.get("/api/mcp/inputs").json()
        if pending:
            break
        time.sleep(0.1)
    assert pending, "expected a pending MRTR input"
    assert pending[0]["server_id"] == "mrtr"
    assert "temp_*" in pending[0]["message"]
    assert pending[0]["requested_schema"] is not None

    # Reply confirms; the parked call resumes and completes
    reply = client.post(
        f"/api/mcp/inputs/{pending[0]['input_id']}/reply",
        json={"action": "accept", "content": {"confirm": True}},
    )
    assert reply.status_code == 200

    call_thread.join(timeout=10)
    assert not call_thread.is_alive()
    response = call_result["response"]
    assert response["is_error"] is False
    assert "Deleted 3 records" in response["structured_content"]["result"]

    # replying again to the same input is a 404
    assert (
        client.post(
            f"/api/mcp/inputs/{pending[0]['input_id']}/reply", json={"action": "accept"}
        ).status_code
        == 404
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

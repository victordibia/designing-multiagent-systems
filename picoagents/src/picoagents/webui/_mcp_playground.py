"""
MCP playground state for the WebUI.

Holds the playground's MCPClientManager, bridges MRTR input requests to the
UI (park a future, emit an SSE event, resolve on reply), fans out wire
frames and notifications to SSE subscribers, and builds the SDK support
matrix (static data merged with live introspection of the installed SDK).
"""

import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

INPUT_TIMEOUT_SECONDS = 180.0


class PendingInput:
    """A parked MRTR input request awaiting a UI reply."""

    def __init__(self, input_id: str, server_id: str, params: Any):
        self.input_id = input_id
        self.server_id = server_id
        self.message: str = getattr(params, "message", "")
        schema = getattr(params, "requested_schema", None)
        self.requested_schema: Optional[Dict[str, Any]] = None
        if schema is not None:
            try:
                self.requested_schema = (
                    schema if isinstance(schema, dict) else schema.model_dump(by_alias=True)
                )
            except Exception:
                self.requested_schema = None
        self.future: "asyncio.Future[Any]" = asyncio.get_running_loop().create_future()


class McpPlayground:
    """Server-side state for the MCP playground (one per WebUI process)."""

    def __init__(self) -> None:
        from picoagents.tools import MCPClientManager

        self.manager = MCPClientManager(
            elicitation_handler=self._handle_elicitation,
            enable_wire_tap=True,
            on_frame=self._on_wire_frame,
        )
        self.pending_inputs: Dict[str, PendingInput] = {}
        self._subscribers: List["asyncio.Queue[Dict[str, Any]]"] = []

    # ------------------------------------------------------------------
    # Events (SSE fan-out)
    # ------------------------------------------------------------------

    def subscribe(self) -> "asyncio.Queue[Dict[str, Any]]":
        queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=500)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: "asyncio.Queue[Dict[str, Any]]") -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def _publish(self, event: Dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.debug("Dropping playground event for slow SSE consumer")

    def _on_wire_frame(self, server_id: str, frame: Dict[str, Any]) -> None:
        self._publish({"type": "wire_frame", "server_id": server_id, "frame": frame})

    # ------------------------------------------------------------------
    # MRTR bridging
    # ------------------------------------------------------------------

    async def _handle_elicitation(self, server_id: str, params: Any) -> Any:
        from mcp.types import ElicitResult

        pending = PendingInput(uuid.uuid4().hex[:12], server_id, params)
        self.pending_inputs[pending.input_id] = pending
        self._publish(
            {
                "type": "input_required",
                "server_id": server_id,
                "input_id": pending.input_id,
                "message": pending.message,
                "requested_schema": pending.requested_schema,
            }
        )
        try:
            reply = await asyncio.wait_for(pending.future, timeout=INPUT_TIMEOUT_SECONDS)
            return ElicitResult(
                action=reply.get("action", "decline"),
                content=reply.get("content"),
            )
        except asyncio.TimeoutError:
            logger.warning(f"MRTR input {pending.input_id} timed out; declining")
            return ElicitResult(action="decline")
        finally:
            self.pending_inputs.pop(pending.input_id, None)
            self._publish(
                {
                    "type": "input_resolved",
                    "server_id": server_id,
                    "input_id": pending.input_id,
                }
            )

    def resolve_input(self, input_id: str, action: str, content: Optional[Dict[str, Any]]) -> bool:
        pending = self.pending_inputs.get(input_id)
        if pending is None or pending.future.done():
            return False
        pending.future.set_result({"action": action, "content": content})
        return True

    async def shutdown(self) -> None:
        for pending in list(self.pending_inputs.values()):
            if not pending.future.done():
                pending.future.cancel()
        await self.manager.disconnect_all()


# ----------------------------------------------------------------------
# Lab server presets
# ----------------------------------------------------------------------


def _find_lab_dir() -> Optional[Path]:
    # webui/ -> picoagents pkg -> src -> picoagents project -> repo root
    candidate = Path(__file__).resolve().parents[4] / "examples" / "mcp_lab"
    if not candidate.is_dir():
        logger.info("MCP lab servers not found (source checkout only); no presets")
        return None
    return candidate


def get_presets() -> List[Dict[str, Any]]:
    """One-click stdio configs for the lab servers, when available."""
    lab_dir = _find_lab_dir()
    if lab_dir is None:
        return []
    presets = []
    for name, description in [
        ("basic_server", "Plain tools, structured output, progress"),
        ("mrtr_server", "Mid-call input (MRTR) via elicitation"),
        ("notify_server", "Runtime tool registry changes"),
    ]:
        path = lab_dir / f"{name}.py"
        if path.exists():
            presets.append(
                {
                    "server_id": name.replace("_server", ""),
                    "description": description,
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": [str(path)],
                }
            )
    return presets


# ----------------------------------------------------------------------
# SDK support matrix
# ----------------------------------------------------------------------


def introspect_python_sdk() -> Dict[str, Any]:
    """
    Live feature check of the installed `mcp` package.

    This is the self-verifying column of the support matrix: statuses are
    derived from what the package actually exposes, not from documentation.
    """
    checks: Dict[str, Dict[str, Any]] = {}

    def check(feature: str, probe: Any, note: str) -> None:
        try:
            status = "shipped" if probe() else "missing"
        except Exception:
            status = "missing"
        checks[feature] = {"status": status, "note": note}

    import importlib

    def has_module(name: str) -> bool:
        try:
            importlib.import_module(name)
            return True
        except ImportError:
            return False

    import mcp.types as t

    check(
        "stateless-core",
        lambda: hasattr(t, "DiscoverRequest") and t.LATEST_PROTOCOL_VERSION >= "2026-07-28",
        "server/discover + per-request _meta",
    )
    check(
        "mrtr",
        lambda: hasattr(t, "InputRequiredResult"),
        "InputRequiredResult + elicitation callback",
    )
    check(
        "tasks-types",
        lambda: hasattr(t, "GetTaskRequest"),
        "Tasks wire types in mcp.types",
    )

    def tasks_runtime_probe() -> bool:
        from mcp.client import Client

        return any("task" in n.lower() for n in dir(Client))

    check(
        "tasks",
        tasks_runtime_probe,
        "Client-side Tasks runtime (polling, tasks/get)",
    )
    check(
        "extensions",
        lambda: has_module("mcp.client.extension"),
        "Extension negotiation framework",
    )
    check("apps", lambda: has_module("mcp.server.apps"), "MCP Apps (server-side)")
    check("auth", lambda: has_module("mcp.client.auth"), "OAuth resource-server model")
    check(
        "subscriptions",
        lambda: has_module("mcp.client.subscriptions"),
        "subscriptions/listen stream",
    )

    try:
        import importlib.metadata

        version = importlib.metadata.version("mcp")
    except Exception:
        version = "unknown"

    return {"sdk": "python", "version": version, "source": "introspected", "features": checks}


def get_support_matrix() -> Dict[str, Any]:
    """Static per-SDK matrix merged with live Python introspection."""
    matrix_path = Path(__file__).with_name("mcp_support_matrix.json")
    data: Dict[str, Any] = json.loads(matrix_path.read_text())
    python_live = introspect_python_sdk()
    for sdk in data.get("sdks", []):
        if sdk.get("sdk") == "python":
            sdk["version"] = python_live["version"]
            sdk["source"] = "introspected"
            # live probe wins over static claims
            for feature, result in python_live["features"].items():
                if feature in sdk.get("features", {}):
                    sdk["features"][feature]["status"] = result["status"]
                else:
                    sdk.setdefault("features", {})[feature] = result
            break
    data["protocol_version"] = "2026-07-28"
    return data

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


def get_spec_support() -> Dict[str, Any]:
    """
    What the installed mcp package supports, probed live.

    Every status is derived from what the package actually exposes, so this
    cannot drift from reality the way a hand-maintained table would.
    """
    import importlib

    import mcp.types as t

    features: List[Dict[str, Any]] = []

    def check(key: str, label: str, description: str, probe: Any) -> None:
        try:
            supported = bool(probe())
        except Exception:
            supported = False
        features.append(
            {
                "key": key,
                "label": label,
                "description": description,
                "status": "shipped" if supported else "missing",
            }
        )

    def has_module(name: str) -> bool:
        try:
            importlib.import_module(name)
            return True
        except ImportError:
            return False

    def tasks_runtime() -> bool:
        from mcp.client import Client

        return any("task" in n.lower() for n in dir(Client))

    check(
        "stateless-core",
        "Stateless core",
        "server/discover with per-request version and capabilities; no initialize handshake",
        lambda: hasattr(t, "DiscoverRequest")
        and t.LATEST_PROTOCOL_VERSION >= "2026-07-28",
    )
    check(
        "mrtr",
        "Multi Round-Trip Requests",
        "Mid-call input without holding a connection open",
        lambda: hasattr(t, "InputRequiredResult"),
    )
    check(
        "tasks-types",
        "Tasks wire types",
        "Task request and result types are defined",
        lambda: hasattr(t, "GetTaskRequest"),
    )
    check(
        "tasks",
        "Tasks runtime",
        "Client-side durable task handling: tasks/get polling, tasks/update",
        tasks_runtime,
    )
    check(
        "extensions",
        "Extensions",
        "Opt-in extension negotiation framework",
        lambda: has_module("mcp.client.extension"),
    )
    check(
        "apps",
        "MCP Apps",
        "Interactive UI extension (server side)",
        lambda: has_module("mcp.server.apps"),
    )
    check(
        "auth",
        "Authorization",
        "OAuth 2.0 resource-server model",
        lambda: has_module("mcp.client.auth"),
    )
    check(
        "subscriptions",
        "Subscriptions",
        "subscriptions/listen change notifications",
        lambda: has_module("mcp.client.subscriptions"),
    )

    try:
        import importlib.metadata

        version = importlib.metadata.version("mcp")
    except Exception:
        version = "unknown"

    return {
        "sdk": "python",
        "version": version,
        "protocol_version": getattr(t, "LATEST_PROTOCOL_VERSION", "unknown"),
        "features": features,
    }

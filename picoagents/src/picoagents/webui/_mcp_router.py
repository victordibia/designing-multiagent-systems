"""MCP playground API router.

REST + SSE surface for the WebUI MCP playground:
- Server configs: list/add/remove, connect/disconnect
- Discovery: capabilities and tools
- Invocation: direct tool calls, MRTR input replies
- Observability: wire frames, SSE event stream
- SDK support matrix
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class AddServerRequest(BaseModel):
    server_id: str
    transport: str = Field(description="stdio | streamable-http | sse")
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None


class CallToolRequest(BaseModel):
    arguments: Dict[str, Any] = Field(default_factory=dict)


class InputReplyRequest(BaseModel):
    action: str = Field(default="accept", description="accept | decline | cancel")
    content: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# State access
# ---------------------------------------------------------------------------


def get_playground(request: Request) -> Any:
    playground = getattr(request.app.state, "mcp_playground", None)
    if playground is None:
        raise HTTPException(
            status_code=503, detail="MCP playground not initialized (mcp not installed?)"
        )
    return playground


def _config_summary(config: Any, connected: bool, tool_count: int) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "server_id": config.server_id,
        "transport": config.transport,
        "status": "connected" if connected else "disconnected",
        "tool_count": tool_count,
    }
    for attr in ("command", "args", "url"):
        value = getattr(config, attr, None)
        if value is not None:
            summary[attr] = value
    return summary


# ---------------------------------------------------------------------------
# Support matrix + presets
# ---------------------------------------------------------------------------


@router.get("/support")
async def support_matrix() -> Dict[str, Any]:
    from ._mcp_playground import get_support_matrix

    return get_support_matrix()


@router.get("/presets")
async def presets() -> List[Dict[str, Any]]:
    from ._mcp_playground import get_presets

    return get_presets()


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


@router.get("/servers")
async def list_servers(request: Request) -> List[Dict[str, Any]]:
    playground = get_playground(request)
    manager = playground.manager
    return [
        _config_summary(
            manager.get_config(server_id),
            manager.is_connected(server_id),
            len(manager.get_tools(server_id)),
        )
        for server_id in manager.list_servers()
    ]


@router.post("/servers")
async def add_server(request: Request, body: AddServerRequest) -> Dict[str, Any]:
    from picoagents.tools import HTTPServerConfig, StdioServerConfig

    playground = get_playground(request)

    if body.transport == "stdio":
        if not body.command:
            raise HTTPException(status_code=400, detail="stdio transport requires 'command'")
        config: Any = StdioServerConfig(
            server_id=body.server_id,
            command=body.command,
            args=body.args or [],
            env=body.env,
        )
    elif body.transport in ("streamable-http", "sse"):
        if not body.url:
            raise HTTPException(status_code=400, detail=f"{body.transport} transport requires 'url'")
        config = HTTPServerConfig(
            server_id=body.server_id,
            url=body.url,
            transport=body.transport,  # type: ignore[arg-type]
            headers=body.headers,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown transport: {body.transport}")

    try:
        playground.manager.add_server(config)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return _config_summary(config, False, 0)


@router.delete("/servers/{server_id}")
async def remove_server(request: Request, server_id: str) -> Dict[str, Any]:
    playground = get_playground(request)
    if playground.manager.get_config(server_id) is None:
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
    if playground.manager.is_connected(server_id):
        await playground.manager.disconnect(server_id)
    playground.manager.remove_server(server_id)
    return {"status": "removed", "server_id": server_id}


@router.post("/servers/{server_id}/connect")
async def connect_server(request: Request, server_id: str) -> Dict[str, Any]:
    playground = get_playground(request)
    manager = playground.manager
    if manager.get_config(server_id) is None:
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
    try:
        await manager.connect(server_id)
    except ConnectionError as e:
        raise HTTPException(status_code=502, detail=str(e))

    info = manager.get_server_info(server_id)
    info["tools"] = await _tool_listing(manager, server_id)
    return info


@router.post("/servers/{server_id}/disconnect")
async def disconnect_server(request: Request, server_id: str) -> Dict[str, Any]:
    playground = get_playground(request)
    if playground.manager.get_config(server_id) is None:
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
    await playground.manager.disconnect(server_id)
    return {"status": "disconnected", "server_id": server_id}


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _require_connected(playground: Any, server_id: str) -> Any:
    manager = playground.manager
    if manager.get_config(server_id) is None:
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
    if not manager.is_connected(server_id):
        raise HTTPException(status_code=409, detail=f"Server '{server_id}' is not connected")
    return manager


@router.get("/servers/{server_id}/capabilities")
async def capabilities(request: Request, server_id: str) -> Dict[str, Any]:
    playground = get_playground(request)
    manager = _require_connected(playground, server_id)
    return manager.get_server_info(server_id)


async def _tool_listing(manager: Any, server_id: str) -> List[Dict[str, Any]]:
    client = await manager.get_client(server_id)
    result = await client.list_tools()
    return [
        {
            "name": tool.name,
            "title": tool.title,
            "description": tool.description,
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
        }
        for tool in result.tools
    ]


@router.get("/servers/{server_id}/tools")
async def list_tools(request: Request, server_id: str) -> List[Dict[str, Any]]:
    playground = get_playground(request)
    manager = _require_connected(playground, server_id)
    return await _tool_listing(manager, server_id)


# ---------------------------------------------------------------------------
# Invocation
# ---------------------------------------------------------------------------


@router.post("/servers/{server_id}/tools/{tool_name}/call")
async def call_tool(
    request: Request, server_id: str, tool_name: str, body: CallToolRequest
) -> Dict[str, Any]:
    """
    Invoke a tool directly.

    If the server elicits mid-call input (MRTR), this request stays open
    while an `input_required` event goes out on the SSE stream; the reply
    endpoint resolves it and the call resumes.
    """
    playground = get_playground(request)
    manager = _require_connected(playground, server_id)
    client = await manager.get_client(server_id)

    try:
        result = await client.call_tool(tool_name, arguments=body.arguments)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Tool call failed: {e}")

    return {
        "is_error": bool(result.is_error),
        "content": [
            c.model_dump(by_alias=True, exclude_none=True, mode="json") for c in result.content
        ],
        "structured_content": result.structured_content,
    }


@router.post("/inputs/{input_id}/reply")
async def reply_input(request: Request, input_id: str, body: InputReplyRequest) -> Dict[str, Any]:
    playground = get_playground(request)
    if not playground.resolve_input(input_id, body.action, body.content):
        raise HTTPException(status_code=404, detail=f"No pending input '{input_id}'")
    return {"status": "resolved", "input_id": input_id}


@router.get("/inputs")
async def pending_inputs(request: Request) -> List[Dict[str, Any]]:
    playground = get_playground(request)
    return [
        {
            "input_id": p.input_id,
            "server_id": p.server_id,
            "message": p.message,
            "requested_schema": p.requested_schema,
        }
        for p in playground.pending_inputs.values()
    ]


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------


@router.get("/servers/{server_id}/wire")
async def wire_frames(request: Request, server_id: str) -> List[Dict[str, Any]]:
    playground = get_playground(request)
    manager = playground.manager
    if manager.get_config(server_id) is None:
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
    return manager.get_wire_frames(server_id)


@router.get("/events")
async def events(request: Request) -> StreamingResponse:
    """SSE stream of playground events: wire frames, MRTR input requests."""
    playground = get_playground(request)
    queue = playground.subscribe()

    async def generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            playground.unsubscribe(queue)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )

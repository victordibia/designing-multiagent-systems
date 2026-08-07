"""
WireTap - records raw JSON-RPC frames flowing through an MCP transport.

Wraps any Transport (async context manager yielding read/write streams) and
records each SessionMessage with direction and timestamp. Powers the wire
inspector in the WebUI playground without touching SDK internals.
"""

import time
from collections import deque
from typing import Any, Callable, Deque, Dict, Optional

WireFrame = Dict[str, Any]
"""A recorded frame: {direction, timestamp, message}."""

FrameCallback = Callable[[str, WireFrame], None]
"""Callback invoked as (server_id, frame) each time a frame is recorded."""


def _serialize_message(msg: Any) -> Dict[str, Any]:
    """Convert a SessionMessage (or stream error) to a JSON-safe dict."""
    if isinstance(msg, Exception):
        return {"error": f"{type(msg).__name__}: {msg}"}
    try:
        return msg.message.model_dump(by_alias=True, exclude_none=True, mode="json")
    except Exception:
        return {"raw": str(msg)}


class _TappedStream:
    """Proxy for a read or write stream that records passing messages.

    Implements the dunder protocols (context manager, async iteration)
    explicitly - the SDK uses streams via `async with` and `async for`,
    which bypass `__getattr__`.
    """

    def __init__(self, inner: Any, record: Callable[[Any], None]):
        self._inner = inner
        self._record = record

    async def receive(self) -> Any:
        msg = await self._inner.receive()
        self._record(msg)
        return msg

    async def send(self, msg: Any) -> None:
        self._record(msg)
        await self._inner.send(msg)

    async def __aenter__(self) -> "_TappedStream":
        await self._inner.__aenter__()
        return self

    async def __aexit__(self, *exc_info: Any) -> Any:
        return await self._inner.__aexit__(*exc_info)

    def __aiter__(self) -> "_TappedStream":
        return self

    async def __anext__(self) -> Any:
        import anyio

        try:
            return await self.receive()
        except anyio.EndOfStream:
            raise StopAsyncIteration from None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class WireTap:
    """
    Transport wrapper that records JSON-RPC frames in both directions.

    Example:
        ```python
        tap = WireTap(stdio_client(params), server_id="lab")
        async with Client(tap) as client:
            await client.list_tools()
        for frame in tap.frames:
            print(frame["direction"], frame["message"].get("method"))
        ```
    """

    def __init__(
        self,
        inner: Any,
        server_id: str = "",
        max_frames: int = 1000,
        on_frame: Optional[FrameCallback] = None,
    ):
        self._inner = inner
        self.server_id = server_id
        self.frames: Deque[WireFrame] = deque(maxlen=max_frames)
        self._on_frame = on_frame

    def _record(self, direction: str, msg: Any) -> None:
        frame: WireFrame = {
            "direction": direction,
            "timestamp": time.time(),
            "message": _serialize_message(msg),
        }
        self.frames.append(frame)
        if self._on_frame:
            try:
                self._on_frame(self.server_id, frame)
            except Exception:
                pass  # observers must never break the transport

    async def __aenter__(self) -> Any:
        read, write = await self._inner.__aenter__()
        tapped_read = _TappedStream(read, lambda m: self._record("in", m))
        tapped_write = _TappedStream(write, lambda m: self._record("out", m))
        return tapped_read, tapped_write

    async def __aexit__(self, *exc_info: Any) -> Any:
        return await self._inner.__aexit__(*exc_info)

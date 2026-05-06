from __future__ import annotations

import asyncio
import socket
import json
import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

try:
    import aiohttp
except ImportError:  # pragma: no cover - surfaced by check_requirements()
    aiohttp = None

logger = logging.getLogger(__name__)


Chat43EventHandler = Callable[[dict[str, Any]], Awaitable[None] | None]


@dataclass(frozen=True)
class Chat43SSEConfig:
    api_key: str
    base_url: str = "https://43chat.cn"
    reconnect_initial_s: float = 3.0
    reconnect_max_s: float = 30.0
    seen_cache_size: int = 2048


class SSEFrameParser:
    def __init__(self) -> None:
        self._buffer = ""
        self._event_id: str | None = None
        self._event_name: str | None = None
        self._data_lines: list[str] = []

    def feed(self, chunk: str) -> list[dict[str, str]]:
        self._buffer += chunk
        frames: list[dict[str, str]] = []
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.endswith("\r"):
                line = line[:-1]
            self._consume_line(line, frames)
        return frames

    def _consume_line(self, line: str, frames: list[dict[str, str]]) -> None:
        if line == "":
            self._flush(frames)
            return
        if line.startswith(":"):
            return

        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "id":
            self._event_id = value
        elif field == "event":
            self._event_name = value
        elif field == "data":
            self._data_lines.append(value)

    def _flush(self, frames: list[dict[str, str]]) -> None:
        if self._event_id is None and self._event_name is None and not self._data_lines:
            return
        frame: dict[str, str] = {}
        if self._event_id is not None:
            frame["id"] = self._event_id
        if self._event_name is not None:
            frame["event"] = self._event_name
        if self._data_lines:
            frame["data"] = "\n".join(self._data_lines)
        frames.append(frame)
        self._event_id = None
        self._event_name = None
        self._data_lines = []


class Chat43SSEClient:
    def __init__(self, config: Chat43SSEConfig):
        if aiohttp is None:
            raise RuntimeError("aiohttp is required: pip install aiohttp")
        self.config = config
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._seen: OrderedDict[str, None] = OrderedDict()

    def start(self, handler: Chat43EventHandler) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(handler), name="chat43-sse")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self, handler: Chat43EventHandler) -> None:
        delay = self.config.reconnect_initial_s
        while not self._stop.is_set():
            try:
                await self._connect_once(handler)
                delay = self.config.reconnect_initial_s
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("43Chat SSE connection failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                delay = min(delay * 2, self.config.reconnect_max_s)

    async def _connect_once(self, handler: Chat43EventHandler) -> None:
        url = self.config.base_url.rstrip("/") + "/open/events/stream"
        headers = {"Authorization": f"Bearer {self.config.api_key}", "Accept": "text/event-stream"}
        parser = SSEFrameParser()
        timeout = aiohttp.ClientTimeout(total=None, connect=20, sock_connect=20, sock_read=None)
        connector = aiohttp.TCPConnector(
            family=socket.AF_INET,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )

        async with aiohttp.ClientSession(timeout=timeout, connector=connector, trust_env=False) as session:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                logger.info("43Chat SSE connected: %s", response.status)
                async for raw in response.content.iter_chunked(4096):
                    if self._stop.is_set():
                        return
                    for frame in parser.feed(raw.decode("utf-8", errors="replace")):
                        event = self._parse_frame(frame)
                        if event is not None and self._remember_event(event):
                            result = handler(event)
                            if asyncio.iscoroutine(result):
                                await result

    def _parse_frame(self, frame: dict[str, str]) -> dict[str, Any] | None:
        data = frame.get("data")
        if not data:
            return None
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            logger.warning("Ignoring invalid 43Chat SSE JSON frame")
            return None
        if not isinstance(event, dict):
            return None
        if "event_type" not in event and frame.get("event"):
            event["event_type"] = frame["event"]
        if "id" not in event and frame.get("id"):
            event["id"] = frame["id"]
        return event

    def _remember_event(self, event: dict[str, Any]) -> bool:
        event_id = first_string(event, "id", "event_id")
        data = event.get("data")
        if event_id is None and isinstance(data, dict):
            event_id = first_string(data, "message_id", "msg_id", "id")
        if event_id is None:
            return True
        if event_id in self._seen:
            return False
        self._seen[event_id] = None
        if len(self._seen) > self.config.seen_cache_size:
            self._seen.popitem(last=False)
        return True


def first_string(mapping: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return str(value)
    return None

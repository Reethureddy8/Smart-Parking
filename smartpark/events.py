"""Server-sent events: every change pings connected dashboards so they refresh live."""
from __future__ import annotations

import asyncio
import json
import time


class Bus:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def _push(self, msg: str) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:  # slow client: drop it, it will reconnect
                self._subs.discard(q)

    def publish(self, kind: str, **data) -> None:
        """Safe to call from any thread."""
        msg = json.dumps({"type": kind, "at": time.time(), **data})
        if self._loop is None:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            self._push(msg)
        else:
            self._loop.call_soon_threadsafe(self._push, msg)


bus = Bus()

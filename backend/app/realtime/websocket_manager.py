"""WebSocketManager — tracks connected dashboard clients and broadcasts alerts.

Module-level lazy singleton (``get_ws_manager()``), same pattern as
``app.detection.registry.get_registry()`` — one shared instance for the life
of the process, because WebSocket connections have to be visible to every
request that might need to broadcast to them, not just the request that
accepted the connection.

TODO(Phase 8+): this is a single-process, in-memory connection dict —
correct for this project's single-worker deployment (no `--workers > 1`),
but it would NOT work across multiple uvicorn worker processes, since each
process would have its own disjoint ``_connections`` dict and a broadcast
from one process would never reach clients connected to another. A
multi-process deployment needs a shared broadcast channel (Redis pub/sub is
the standard fix) so every worker can publish and every worker's connected
clients receive it. Same caveat, same TODO pattern as the in-memory detector
state and chatbot conversation history elsewhere in this codebase.

CROSS-THREAD SCHEDULING: alerts are persisted from ``POST /api/v1/log``,
which is a *sync* ``def`` endpoint running on Starlette's threadpool (see
api/logs.py and the Phase 4 concurrency notes on why it stays sync). Calling
an ``async def`` method like ``broadcast()`` directly from that worker
thread isn't possible without a bridge — see ``schedule_broadcast()`` below,
which is the sync-callable entry point sync code should actually use.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Tracks connected WebSocket clients and broadcasts JSON messages."""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        # Captured once, at app startup, on the main event loop — see
        # set_loop() / schedule_broadcast() below.
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------ lifecycle

    async def connect(self, websocket: WebSocket) -> str:
        """Accept a WebSocket connection, register it, return its client_id."""
        await websocket.accept()
        client_id = str(uuid.uuid4())
        self._connections[client_id] = websocket
        logger.info(
            "WebSocket client connected: %s (total connected: %d)",
            client_id,
            len(self._connections),
        )
        return client_id

    def disconnect(self, client_id: str) -> None:
        """Remove a client. Safe to call for an id that's already gone."""
        removed = self._connections.pop(client_id, None)
        if removed is not None:
            logger.info(
                "WebSocket client disconnected: %s (total connected: %d)",
                client_id,
                len(self._connections),
            )

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    # -------------------------------------------------------------- sending

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send ``message`` (as JSON) to every connected client.

        A send failure on any one client (e.g. it disconnected without a
        clean close handshake) is caught, logged, and that client is
        dropped — it never aborts the loop for the remaining clients.
        """
        dead_client_ids: list[str] = []
        for client_id, websocket in list(self._connections.items()):
            try:
                await websocket.send_json(message)
            except Exception:
                logger.warning(
                    "Broadcast to client %s failed, dropping connection", client_id, exc_info=True
                )
                dead_client_ids.append(client_id)

        for client_id in dead_client_ids:
            self.disconnect(client_id)

    async def send_personal(self, client_id: str, message: dict[str, Any]) -> None:
        """Send ``message`` to exactly one client.

        Not called anywhere yet in this phase — implemented ahead of time
        for a future per-session use (e.g. a chatbot-over-websocket in a
        later phase, per the design notes). Same failure handling as
        ``broadcast()``: a dead connection is logged and dropped, not raised.
        """
        websocket = self._connections.get(client_id)
        if websocket is None:
            logger.warning("send_personal: no connected client with id %s", client_id)
            return
        try:
            await websocket.send_json(message)
        except Exception:
            logger.warning(
                "send_personal to client %s failed, dropping connection", client_id, exc_info=True
            )
            self.disconnect(client_id)

    # ------------------------------------------------ cross-thread bridge

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Record the main event loop — call once, at app startup (see
        main.py's lifespan handler), on that loop.
        """
        self._loop = loop

    def schedule_broadcast(self, message: dict[str, Any]) -> None:
        """Sync entry point: schedule a broadcast from a worker thread.

        ``POST /api/v1/log`` (api/logs.py) is a sync ``def`` endpoint, so
        FastAPI runs it on Starlette's threadpool (a real OS thread, not the
        main asyncio event loop — this is the same threadpool-execution fact
        Phase 4's concurrency fix is built around). ``broadcast()`` is
        ``async def`` and the live WebSocket connections it touches were
        accepted on, and belong to, the MAIN event loop — they aren't safe
        to drive from a different thread or a different event loop.

        The correct bridge for "run this coroutine on that other loop, from
        this thread" is ``asyncio.run_coroutine_threadsafe`` — NOT
        ``asyncio.run()``. ``asyncio.run()`` would create a brand-new,
        throwaway event loop inside the worker thread for every single
        call, which is wasteful, and worse, would try to drive the
        WebSocket objects (bound to the main loop) from a foreign loop —
        unsafe cross-loop access that asyncio does not support. See the
        docstring in api/logs.py for the full reasoning on why the endpoint
        stays sync rather than switching to async def.

        Fire-and-forget: this does not block the calling worker thread
        waiting for the broadcast to finish (matching the design note that
        broadcasting is a best-effort side effect after the DB commit, not
        something the HTTP client waits on). Any exception raised inside
        the scheduled coroutine is still logged via the future's done
        callback, rather than silently vanishing.
        """
        if self._loop is None:
            logger.warning(
                "WebSocketManager: no event loop captured yet (app not started via "
                "its lifespan handler?) — dropping broadcast: %r",
                message,
            )
            return

        future = asyncio.run_coroutine_threadsafe(self.broadcast(message), self._loop)
        future.add_done_callback(self._log_if_broadcast_failed)

    @staticmethod
    def _log_if_broadcast_failed(future: "asyncio.Future[None]") -> None:
        if future.cancelled():
            return
        exc = future.exception()
        if exc is not None:
            logger.error("Scheduled broadcast raised an exception: %s", exc, exc_info=exc)


# ------------------------------------------------------------------ singleton

_ws_manager: WebSocketManager | None = None


def get_ws_manager() -> WebSocketManager:
    """Lazily construct the process-wide WebSocketManager singleton."""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager


def reset_ws_manager() -> None:
    """For tests: drop the cached manager so connections/loop don't leak
    between test cases (same pattern as ``detection.registry.reset_registry``).
    """
    global _ws_manager
    _ws_manager = None

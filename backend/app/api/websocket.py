"""WebSocket endpoint for real-time alert push.

Reachable at ``ws://host:port/ws/alerts`` — deliberately NOT mounted under
``/api/v1``. FastAPI/Starlette WebSocket routes don't participate in the
same prefix/versioning conventions as HTTP routers in a way that matters
here; this module's router is included in main.py without the ``/api/v1``
prefix so the path matches ARCHITECTURE.md's real-time delivery diagram and
the plain ``ws://.../ws/alerts`` convention (REST endpoints are versioned
because their request/response shapes need to evolve independently; this
socket carries one push message shape for now and versioning it alongside
REST would be premature).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.realtime.websocket_manager import get_ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/alerts")
async def alerts_websocket(websocket: WebSocket) -> None:
    """Accept a dashboard client, register it, and keep the connection open.

    The server doesn't act on any client-to-server messages in this phase —
    there's no request/response protocol defined over this socket yet, it's
    push-only. But the loop below (blocking on ``receive_text()``) is still
    required: without the server actively receiving, some clients/proxies
    treat the connection as half-dead, and — more importantly — it's how we
    detect a client-initiated disconnect (``WebSocketDisconnect`` is raised
    out of ``receive_text()`` when the client closes the socket).
    """
    manager = get_ws_manager()
    client_id = await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("WebSocket client %s closed the connection", client_id)
    finally:
        manager.disconnect(client_id)

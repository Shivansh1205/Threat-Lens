"""Realtime package (Phase 7a): WebSocket connection tracking + broadcast.

See ``websocket_manager.py`` for ``WebSocketManager`` / ``get_ws_manager()``.
The WebSocket route itself lives in ``app.api.websocket`` (mounted at the
app root, not under ``/api/v1`` — see that module and main.py).
"""

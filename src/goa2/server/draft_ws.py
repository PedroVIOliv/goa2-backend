"""WebSocket handler for real-time draft-lobby updates.

The draft channel is **read-only**: clients still mutate the draft through the
REST endpoints (where all validation lives), and every mutation broadcasts a
player-scoped ``STATE_UPDATE`` to connected sockets. Inbound, only ``GET_VIEW``
is honoured (to re-request the current state); anything else gets an error reply.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from goa2.draft.errors import DraftNotFoundError
from goa2.server.draft_registry import DraftRegistry, ManagedDraft

router = APIRouter()


def draft_view_payload(md: ManagedDraft, player_id: str, is_spectator: bool) -> dict[str, Any]:
    """Build the player-scoped draft view fields (shared by REST and WS)."""
    you = None
    if not is_spectator:
        you = next(
            (p.model_dump(mode="json") for p in md.state.players if p.id == player_id),
            None,
        )
    return {
        "draft": md.state.model_dump(mode="json"),
        "you": you,
        "game_id": md.state.game_id,
        "game_token": md.player_game_tokens.get(player_id),
    }


def _state_message(md: ManagedDraft, player_id: str, is_spectator: bool) -> dict[str, Any]:
    return {"type": "STATE_UPDATE", **draft_view_payload(md, player_id, is_spectator)}


async def _send_json(ws: WebSocket, data: dict[str, Any]) -> bool:
    """Send JSON to a websocket, returning False if the connection is dead."""
    try:
        await ws.send_json(data)
        return True
    except Exception:
        return False


async def broadcast_draft(md: ManagedDraft, registry: DraftRegistry) -> None:
    """Push a player-scoped STATE_UPDATE to every connected socket on this draft."""
    dead_connections: list[tuple[str, WebSocket]] = []
    dead_spectators: list[WebSocket] = []
    # Snapshot connections because sends yield and allow reconnects to mutate
    # the registry while a broadcast is in progress.
    for token, ws in list(md.ws_connections.items()):
        resolved = registry.resolve_token(token)
        if resolved is None:
            dead_connections.append((token, ws))
            continue
        _, player_id, is_spectator, _ = resolved
        if not await _send_json(ws, _state_message(md, player_id, is_spectator)):
            dead_connections.append((token, ws))
    for ws in list(md.spectator_ws_connections.values()):
        if not await _send_json(ws, _state_message(md, "", True)):
            dead_spectators.append(ws)
    for token, ws in dead_connections:
        # A reconnect may have replaced the failed socket during an awaited
        # send. Only remove the exact connection that was found to be dead.
        if md.ws_connections.get(token) is ws:
            md.ws_connections.pop(token, None)
    for ws in dead_spectators:
        connection_id = id(ws)
        if md.spectator_ws_connections.get(connection_id) is ws:
            md.spectator_ws_connections.pop(connection_id, None)


@router.websocket("/drafts/{draft_id}/ws")
async def draft_ws(websocket: WebSocket, draft_id: str) -> None:
    """WebSocket endpoint for live draft-lobby updates.

    Connect with ?token=<bearer_token> query parameter. Read-only: send
    ``{"type": "GET_VIEW"}`` to re-request state; mutate via the REST API.
    """
    token = websocket.query_params.get("token", "")
    registry: DraftRegistry = websocket.app.state.draft_registry

    resolved = registry.resolve_token(token)
    if resolved is None:
        await websocket.close(code=4001, reason="Invalid token")
        return

    resolved_draft_id, player_id, is_spectator, _is_host = resolved
    if resolved_draft_id != draft_id:
        await websocket.close(code=4003, reason="Token does not match draft")
        return

    try:
        md = registry.get(draft_id)
    except DraftNotFoundError:
        await websocket.close(code=4004, reason="Draft not found")
        return

    await websocket.accept()
    spectator_connection_id = id(websocket)
    if is_spectator:
        md.spectator_ws_connections[spectator_connection_id] = websocket
    else:
        md.ws_connections[token] = websocket
    await websocket.send_json(_state_message(md, player_id, is_spectator))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "ERROR", "detail": "Invalid JSON"})
                continue

            if data.get("type") == "GET_VIEW":
                await websocket.send_json(_state_message(md, player_id, is_spectator))
            else:
                await websocket.send_json(
                    {
                        "type": "ERROR",
                        "detail": "Draft WS is read-only; mutate via REST. "
                        'Send {"type": "GET_VIEW"} to refresh.',
                    }
                )
    except WebSocketDisconnect:
        pass
    finally:
        if is_spectator:
            if md.spectator_ws_connections.get(spectator_connection_id) is websocket:
                md.spectator_ws_connections.pop(spectator_connection_id, None)
        else:
            # An older same-token player connection can close after a reconnect.
            # It must not unregister the newer socket that replaced it.
            if md.ws_connections.get(token) is websocket:
                md.ws_connections.pop(token, None)

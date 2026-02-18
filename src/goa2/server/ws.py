"""WebSocket handler for real-time game events."""

from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from goa2.domain.input import InputResponse
from goa2.domain.models import GamePhase
from goa2.domain.views import build_view
from goa2.engine.session import SessionResultType
from goa2.server.errors import (
    CardNotInHandError,
    GameNotFoundError,
    InvalidPhaseError,
    NotYourTurnError,
)
from goa2.server.registry import GameRegistry, ManagedGame

router = APIRouter()


def _build_state_update(game: ManagedGame, hero_id: str | None) -> Dict[str, Any]:
    """Build a STATE_UPDATE message for a specific player."""
    view = build_view(game.session.state, for_hero_id=hero_id)
    ir = game.last_result.input_request if game.last_result else None
    msg: Dict[str, Any] = {
        "type": "STATE_UPDATE",
        "view": view,
    }
    if ir:
        msg["input_request"] = ir.to_dict()
    return msg


async def _send_json(ws: WebSocket, data: Dict[str, Any]) -> bool:
    """Send JSON to a websocket, returning False if the connection is dead."""
    try:
        await ws.send_json(data)
        return True
    except Exception:
        return False


async def broadcast(game: ManagedGame, registry: GameRegistry) -> None:
    """Send player-scoped state updates to all connected websockets."""
    dead_tokens: list[str] = []
    for token, ws in game.ws_connections.items():
        hero_id = game.player_tokens.get(token)
        msg = _build_state_update(game, hero_id)
        if not await _send_json(ws, msg):
            dead_tokens.append(token)
    for t in dead_tokens:
        game.ws_connections.pop(t, None)


def _log_ws_result(game: ManagedGame, result) -> None:
    """Log a SessionResult from a WebSocket action."""
    gl = game.game_logger
    if not gl:
        return
    state = game.session.state
    gl.log_phase_change(result.current_phase.value, state.round, state.turn)
    events = [ev.model_dump() for ev in result.events]
    if events:
        gl.log_events(events)
    if result.input_request:
        gl.log_input_request(result.input_request.to_dict())
    if result.winner:
        gl.log_game_over(result.winner)


async def _handle_submit_input(
    game: ManagedGame, hero_id: str, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle SUBMIT_INPUT message."""
    # Turn validation (skip for simultaneous phases like UPGRADE_PHASE)
    if game.last_result and game.last_result.input_request:
        expected = game.last_result.input_request.player_id
        if expected != "simultaneous" and expected != hero_id:
            raise NotYourTurnError(hero_id, expected)

    response = InputResponse(
        request_id=data.get("request_id", ""),
        selection=data.get("selection"),
    )
    if game.game_logger:
        game.game_logger.log_input_response(hero_id, data.get("selection"))
    result = game.session.advance(response)
    game.last_result = result
    _log_ws_result(game, result)
    return {
        "type": "ACTION_RESULT",
        "result_type": result.result_type.value,
        "current_phase": result.current_phase.value,
        "events": [ev.model_dump() for ev in result.events],
        "input_request": result.input_request.to_dict() if result.input_request else None,
        "winner": result.winner,
    }


async def _handle_commit_card(
    game: ManagedGame, hero_id: str, data: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle COMMIT_CARD message."""
    session = game.session
    if session.current_phase != GamePhase.PLANNING:
        raise InvalidPhaseError("PLANNING", session.current_phase.value)

    card_id = data.get("card_id", "")
    hero = session.state.get_hero(hero_id)
    if hero is None:
        return {"type": "ERROR", "detail": "Hero not found"}

    card = next((c for c in hero.hand if c.id == card_id), None)
    if card is None:
        raise CardNotInHandError(card_id, hero_id)

    result = session.commit_card(hero_id, card)
    game.last_result = result
    if game.game_logger:
        game.game_logger.log_card_commit(hero_id, card_id)
    _log_ws_result(game, result)
    return {
        "type": "ACTION_RESULT",
        "result_type": result.result_type.value,
        "current_phase": result.current_phase.value,
        "events": [ev.model_dump() for ev in result.events],
        "input_request": result.input_request.to_dict() if result.input_request else None,
        "winner": result.winner,
    }


async def _handle_pass_turn(
    game: ManagedGame, hero_id: str
) -> Dict[str, Any]:
    """Handle PASS_TURN message."""
    session = game.session
    if session.current_phase != GamePhase.PLANNING:
        raise InvalidPhaseError("PLANNING", session.current_phase.value)

    result = session.pass_turn(hero_id)
    game.last_result = result
    if game.game_logger:
        game.game_logger.log_pass_turn(hero_id)
    _log_ws_result(game, result)
    return {
        "type": "ACTION_RESULT",
        "result_type": result.result_type.value,
        "current_phase": result.current_phase.value,
        "events": [ev.model_dump() for ev in result.events],
        "input_request": result.input_request.to_dict() if result.input_request else None,
        "winner": result.winner,
    }


@router.websocket("/games/{game_id}/ws")
async def game_ws(websocket: WebSocket, game_id: str) -> None:
    """WebSocket endpoint for real-time game interaction.

    Connect with ?token=<bearer_token> query parameter.
    """
    token = websocket.query_params.get("token", "")
    registry: GameRegistry = websocket.app.state.registry

    # Authenticate
    result = registry.resolve_token(token)
    if result is None:
        await websocket.close(code=4001, reason="Invalid token")
        return

    resolved_game_id, hero_id, is_spectator = result
    if resolved_game_id != game_id:
        await websocket.close(code=4003, reason="Token does not match game")
        return

    try:
        game = registry.get(game_id)
    except GameNotFoundError:
        await websocket.close(code=4004, reason="Game not found")
        return

    await websocket.accept()

    # Register connection
    game.ws_connections[token] = websocket

    if game.game_logger:
        game.game_logger.log_ws_connect(hero_id if not is_spectator else None, is_spectator)

    # Send initial state
    initial = _build_state_update(game, hero_id if not is_spectator else None)
    await websocket.send_json(initial)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "ERROR", "detail": "Invalid JSON"}
                )
                continue

            msg_type = data.get("type", "")

            if is_spectator and msg_type != "GET_VIEW":
                await websocket.send_json(
                    {"type": "ERROR", "detail": "Spectators can only GET_VIEW"}
                )
                continue

            try:
                async with game.lock:
                    if msg_type == "SUBMIT_INPUT":
                        reply = await _handle_submit_input(game, hero_id, data)
                    elif msg_type == "COMMIT_CARD":
                        reply = await _handle_commit_card(game, hero_id, data)
                    elif msg_type == "PASS_TURN":
                        reply = await _handle_pass_turn(game, hero_id)
                    elif msg_type == "GET_VIEW":
                        hid = hero_id if not is_spectator else None
                        reply = _build_state_update(game, hid)
                    else:
                        reply = {"type": "ERROR", "detail": f"Unknown message type: {msg_type}"}

                # Auto-save after mutations
                if msg_type in ("SUBMIT_INPUT", "COMMIT_CARD", "PASS_TURN"):
                    registry.save_game(game.game_id)

                # Send reply to sender
                await websocket.send_json(reply)

                # Broadcast state to others after mutations
                if msg_type in ("SUBMIT_INPUT", "COMMIT_CARD", "PASS_TURN"):
                    await broadcast(game, registry)

            except (NotYourTurnError, InvalidPhaseError, CardNotInHandError) as exc:
                if game.game_logger:
                    game.game_logger.log_error(str(exc), hero_id)
                await websocket.send_json(
                    {"type": "ERROR", "detail": str(exc)}
                )
            except ValueError as exc:
                if game.game_logger:
                    game.game_logger.log_error(str(exc), hero_id)
                await websocket.send_json(
                    {"type": "ERROR", "detail": str(exc)}
                )

    except WebSocketDisconnect:
        pass
    finally:
        game.ws_connections.pop(token, None)
        if game.game_logger:
            game.game_logger.log_ws_disconnect(hero_id if not is_spectator else None, is_spectator)

"""WebSocket handler for real-time game events."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from goa2.domain.events import GameEvent, GameEventType
from goa2.domain.input import InputResponse
from goa2.domain.models import GamePhase
from goa2.domain.types import HeroID
from goa2.domain.views import build_view
from goa2.server.errors import (
    CardNotInHandError,
    GameNotFoundError,
    InvalidPhaseError,
    NotYourTurnError,
    validate_input_turn,
    validate_simultaneous_input_scope,
)
from goa2.server.registry import GameRegistry, ManagedGame
from goa2.server.visibility import events_for_viewer, input_request_for_viewer

router = APIRouter()

MUTATION_MESSAGE_TYPES = frozenset(
    {
        "SUBMIT_INPUT",
        "COMMIT_CARD",
        "UNCOMMIT_CARD",
        "PASS_TURN",
        "FINISH_PLANNING",
        "ROLLBACK",
        "CHEATS_GOLD",
    }
)

CapturedBroadcast = list[tuple[str, WebSocket, dict[str, Any]]]


def _build_state_update(game: ManagedGame, hero_id: str | None) -> dict[str, Any]:
    """Build a STATE_UPDATE message for a specific player."""
    hero_id_typed = HeroID(hero_id) if hero_id else None
    view = build_view(game.session.state, for_hero_id=hero_id_typed)
    ir = game.last_result.input_request if game.last_result else None
    winner = game.last_result.winner if game.last_result else None
    msg: dict[str, Any] = {
        "type": "STATE_UPDATE",
        "view": view,
    }
    input_request = input_request_for_viewer(ir, game.session.state, hero_id)
    if input_request:
        msg["input_request"] = input_request
    if winner:
        msg["winner"] = winner
    return msg


async def _send_json(ws: WebSocket, data: dict[str, Any]) -> bool:
    """Send JSON to a websocket, returning False if the connection is dead."""
    try:
        await ws.send_json(data)
        return True
    except Exception:
        return False


def _capture_broadcast(
    game: ManagedGame,
    events: list[dict[str, Any]] | None = None,
) -> CapturedBroadcast:
    """Capture every recipient's scoped payload from one state snapshot.

    Callers must hold ``game.lock`` so no mutation can interleave while the
    player-specific views and event projections are being materialized.
    """
    messages: CapturedBroadcast = []
    for token, ws in list(game.ws_connections.items()):
        hero_id = game.player_tokens.get(token)
        msg = _build_state_update(game, hero_id)
        if events:
            msg["events"] = events_for_viewer(events, game.session.state, hero_id)
        messages.append((token, ws, msg))
    return messages


async def _send_captured_broadcast(
    game: ManagedGame,
    messages: CapturedBroadcast,
) -> None:
    """Send already-materialized payloads and prune failed connections."""
    dead_connections: list[tuple[str, WebSocket]] = []
    for token, ws, msg in messages:
        if not await _send_json(ws, msg):
            dead_connections.append((token, ws))
    for token, ws in dead_connections:
        # A reconnect may have replaced this failed socket while the broadcast
        # was awaiting I/O. Never remove the newer connection by token alone.
        if game.ws_connections.get(token) is ws:
            game.ws_connections.pop(token, None)


async def broadcast(
    game: ManagedGame,
    registry: GameRegistry,
    events: list[dict[str, Any]] | None = None,
) -> None:
    """Send player-scoped state updates to all connected websockets.

    ``events`` is the internal event list from the mutation that triggered this
    broadcast. Each recipient receives a visibility-filtered projection so
    animations cannot expose hidden cards or facedown token identities.
    Connect/GET_VIEW updates pass nothing and stay event-free.
    """
    async with game.outbound_lock:
        async with game.lock:
            messages = _capture_broadcast(game, events)
        await _send_captured_broadcast(game, messages)


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
    game: ManagedGame, hero_id: str, data: dict[str, Any]
) -> dict[str, Any]:
    """Handle SUBMIT_INPUT message."""
    # Turn validation (skip for simultaneous phases like UPGRADE_PHASE)
    if game.last_result and game.last_result.input_request:
        expected = game.last_result.input_request.player_id
        validate_input_turn(expected, hero_id, game.session.state)
        # For a per-hero simultaneous phase (UPGRADE_PHASE), a player may only
        # submit for their own hero.
        validate_simultaneous_input_scope(
            game.last_result.input_request, data.get("selection"), hero_id
        )

    response = InputResponse(
        request_id=data.get("request_id", ""),
        selection=data.get("selection"),
    )
    if game.game_logger:
        game.game_logger.log_input_response(hero_id, data.get("selection"))
    # Record only after the engine accepts the input, tagged with the pre-advance
    # round/turn, so a rejected selection leaves no phantom decision in the log.
    rec_round, rec_turn = game.session.state.round, game.session.state.turn
    result = game.session.advance(response)
    if game.replay_recorder:
        game.replay_recorder.record_input(hero_id, data.get("selection"), rec_round, rec_turn)
    game.last_result = result
    _log_ws_result(game, result)
    return {
        "type": "ACTION_RESULT",
        "result_type": result.result_type.value,
        "current_phase": result.current_phase.value,
        "events": [ev.model_dump() for ev in result.events],
        "input_request": input_request_for_viewer(
            result.input_request, game.session.state, hero_id
        ),
        "winner": result.winner,
    }


async def _handle_commit_card(
    game: ManagedGame, hero_id: str, data: dict[str, Any]
) -> dict[str, Any]:
    """Handle COMMIT_CARD message."""
    session = game.session
    if session.current_phase != GamePhase.PLANNING:
        raise InvalidPhaseError("PLANNING", session.current_phase.value)

    card_id = data.get("card_id", "")
    hero = session.state.get_hero(HeroID(hero_id))
    if hero is None:
        return {"type": "ERROR", "detail": "Hero not found"}

    card = next((c for c in hero.hand if c.id == card_id), None)
    if card is None:
        raise CardNotInHandError(card_id, hero_id)

    rec_round, rec_turn = session.state.round, session.state.turn
    result = session.commit_card(HeroID(hero_id), card)
    if game.replay_recorder:
        game.replay_recorder.record_commit(hero_id, card_id, rec_round, rec_turn)
    game.last_result = result
    if game.game_logger:
        game.game_logger.log_card_commit(hero_id, card_id)
    _log_ws_result(game, result)
    return {
        "type": "ACTION_RESULT",
        "result_type": result.result_type.value,
        "current_phase": result.current_phase.value,
        "events": [ev.model_dump() for ev in result.events],
        "input_request": input_request_for_viewer(
            result.input_request, game.session.state, hero_id
        ),
        "winner": result.winner,
    }


async def _handle_uncommit_card(game: ManagedGame, hero_id: str) -> dict[str, Any]:
    """Handle UNCOMMIT_CARD (Planning take-back; LIFO for a two-card hero)."""
    session = game.session
    if session.current_phase != GamePhase.PLANNING:
        raise InvalidPhaseError("PLANNING", session.current_phase.value)

    # NOTE: validate+mutate stays synchronous under game.lock — that is what
    # makes an uncommit racing the final commit resolve cleanly (one side
    # simply loses; state never corrupts). Don't add awaits before the
    # session call.
    state = session.state
    hid = HeroID(hero_id)
    card = state.pending_second_cards.get(hid) or state.pending_inputs.get(hid)
    rec_round, rec_turn = state.round, state.turn
    result = session.uncommit_card(hid)
    # Record only after success so a failed attempt never lands in the replay.
    if game.replay_recorder:
        game.replay_recorder.record_uncommit(hero_id, rec_round, rec_turn)
    game.last_result = result
    if game.game_logger and card is not None:
        game.game_logger.log_card_uncommit(hero_id, card.id)
    _log_ws_result(game, result)
    return {
        "type": "ACTION_RESULT",
        "result_type": result.result_type.value,
        "current_phase": result.current_phase.value,
        "events": [ev.model_dump() for ev in result.events],
        "input_request": input_request_for_viewer(
            result.input_request, game.session.state, hero_id
        ),
        "winner": result.winner,
    }


async def _handle_finish_planning(game: ManagedGame, hero_id: str) -> dict[str, Any]:
    """Handle FINISH_PLANNING message (done-signal for a two-card-capable
    hero — Emmitt's Alternative Timelines — playing only one card)."""
    session = game.session
    if session.current_phase != GamePhase.PLANNING:
        raise InvalidPhaseError("PLANNING", session.current_phase.value)

    rec_round, rec_turn = session.state.round, session.state.turn
    result = session.finish_planning(HeroID(hero_id))
    if game.replay_recorder:
        game.replay_recorder.record_finish_planning(hero_id, rec_round, rec_turn)
    game.last_result = result
    _log_ws_result(game, result)
    return {
        "type": "ACTION_RESULT",
        "result_type": result.result_type.value,
        "current_phase": result.current_phase.value,
        "events": [ev.model_dump() for ev in result.events],
        "input_request": input_request_for_viewer(
            result.input_request, game.session.state, hero_id
        ),
        "winner": result.winner,
    }


async def _handle_pass_turn(game: ManagedGame, hero_id: str) -> dict[str, Any]:
    """Handle PASS_TURN message."""
    session = game.session
    if session.current_phase != GamePhase.PLANNING:
        raise InvalidPhaseError("PLANNING", session.current_phase.value)

    rec_round, rec_turn = session.state.round, session.state.turn
    result = session.pass_turn(HeroID(hero_id))
    if game.replay_recorder:
        game.replay_recorder.record_pass(hero_id, rec_round, rec_turn)
    game.last_result = result
    if game.game_logger:
        game.game_logger.log_pass_turn(hero_id)
    _log_ws_result(game, result)
    return {
        "type": "ACTION_RESULT",
        "result_type": result.result_type.value,
        "current_phase": result.current_phase.value,
        "events": [ev.model_dump() for ev in result.events],
        "input_request": input_request_for_viewer(
            result.input_request, game.session.state, hero_id
        ),
        "winner": result.winner,
    }


async def _handle_rollback(game: ManagedGame, hero_id: str) -> dict[str, Any]:
    """Handle ROLLBACK message."""
    session = game.session
    if session.state.current_actor_id is None:
        raise NotYourTurnError(hero_id, "(no active actor)")
    # Authorize against whoever the pending input is addressed to — under Hanu's
    # ultimate that is the controller, not the controlled actor.
    responder = game.current_responder
    if responder != hero_id:
        raise NotYourTurnError(hero_id, responder or "(no active actor)")
    rec_round, rec_turn = session.state.round, session.state.turn
    result = session.rollback()
    if game.replay_recorder:
        game.replay_recorder.record_rollback(hero_id, rec_round, rec_turn)
    game.last_result = result
    _log_ws_result(game, result)
    return {
        "type": "ACTION_RESULT",
        "result_type": result.result_type.value,
        "current_phase": result.current_phase.value,
        "events": [ev.model_dump() for ev in result.events],
        "input_request": input_request_for_viewer(
            result.input_request, game.session.state, hero_id
        ),
        "winner": result.winner,
    }


async def _handle_cheats_gold(
    game: ManagedGame, hero_id: str, data: dict[str, Any]
) -> dict[str, Any]:
    """Handle CHEATS_GOLD message."""
    session = game.session

    if not session.state.cheats_enabled:
        return {"type": "ERROR", "detail": "Cheats are not enabled for this game"}

    if session.current_phase != GamePhase.PLANNING:
        raise InvalidPhaseError("PLANNING", session.current_phase.value)

    target_hero_id = data.get("hero_id", "")
    hero = session.state.get_hero(target_hero_id)
    if hero is None:
        return {"type": "ERROR", "detail": f"Hero '{target_hero_id}' not found"}

    amount = data.get("amount", 0)
    if amount <= 0:
        return {"type": "ERROR", "detail": "Amount must be a positive integer"}

    hero.gold += amount
    if game.replay_recorder:
        game.replay_recorder.record_cheat_gold(
            target_hero_id, amount, session.state.round, session.state.turn
        )

    event = GameEvent(
        event_type=GameEventType.GOLD_GAINED,
        actor_id=hero.id,
        metadata={"amount": amount, "reason": "cheat"},
    )

    if game.game_logger:
        game.game_logger.log_events([event.model_dump()])

    return {
        "type": "ACTION_RESULT",
        "result_type": "ACTION_COMPLETE",
        "current_phase": session.current_phase.value,
        "events": [event.model_dump()],
        "input_request": None,
        "winner": None,
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

    # A player token owns one live connection. Register the new socket before
    # closing its predecessor so the old handler's cleanup cannot leave a gap;
    # identity-safe cleanup below ensures it cannot remove this replacement.
    async with game.outbound_lock:
        async with game.lock:
            previous_websocket = game.ws_connections.get(token)
            game.ws_connections[token] = websocket
            initial = _build_state_update(game, hero_id if not is_spectator else None)
        if previous_websocket is not None and previous_websocket is not websocket:
            await previous_websocket.close(
                code=4002,
                reason="Connection superseded by a newer session",
            )
        await websocket.send_json(initial)

    if game.game_logger:
        game.game_logger.log_ws_connect(hero_id if not is_spectator else None, is_spectator)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                async with game.outbound_lock:
                    await websocket.send_json({"type": "ERROR", "detail": "Invalid JSON"})
                continue

            msg_type = data.get("type", "")

            if is_spectator and msg_type != "GET_VIEW":
                async with game.outbound_lock:
                    await websocket.send_json(
                        {"type": "ERROR", "detail": "Spectators can only GET_VIEW"}
                    )
                continue

            try:
                async with game.outbound_lock:
                    async with game.lock:
                        if msg_type == "SUBMIT_INPUT":
                            reply = await _handle_submit_input(game, hero_id, data)
                        elif msg_type == "COMMIT_CARD":
                            reply = await _handle_commit_card(game, hero_id, data)
                        elif msg_type == "UNCOMMIT_CARD":
                            reply = await _handle_uncommit_card(game, hero_id)
                        elif msg_type == "PASS_TURN":
                            reply = await _handle_pass_turn(game, hero_id)
                        elif msg_type == "FINISH_PLANNING":
                            reply = await _handle_finish_planning(game, hero_id)
                        elif msg_type == "ROLLBACK":
                            reply = await _handle_rollback(game, hero_id)
                        elif msg_type == "CHEATS_GOLD":
                            reply = await _handle_cheats_gold(game, hero_id, data)
                        elif msg_type == "GET_VIEW":
                            hid = hero_id if not is_spectator else None
                            reply = _build_state_update(game, hid)
                        else:
                            reply = {
                                "type": "ERROR",
                                "detail": f"Unknown message type: {msg_type}",
                            }

                        # Materialize both the direct reply and every scoped
                        # broadcast while they still describe this mutation.
                        sender_reply = reply
                        if reply.get("type") == "ACTION_RESULT":
                            sender_reply = {
                                **reply,
                                "events": events_for_viewer(
                                    reply.get("events", []), game.session.state, hero_id
                                ),
                            }
                        messages = (
                            _capture_broadcast(game, reply.get("events"))
                            if msg_type in MUTATION_MESSAGE_TYPES
                            else []
                        )

                    if msg_type in MUTATION_MESSAGE_TYPES:
                        registry.save_game(game.game_id)

                    await websocket.send_json(sender_reply)
                    await _send_captured_broadcast(game, messages)

            except (NotYourTurnError, InvalidPhaseError, CardNotInHandError) as exc:
                if game.game_logger:
                    game.game_logger.log_error(str(exc), hero_id)
                async with game.outbound_lock:
                    await websocket.send_json({"type": "ERROR", "detail": str(exc)})
            except ValueError as exc:
                if game.game_logger:
                    game.game_logger.log_error(str(exc), hero_id)
                async with game.outbound_lock:
                    await websocket.send_json({"type": "ERROR", "detail": str(exc)})

    except WebSocketDisconnect:
        pass
    finally:
        # The same token may already belong to a newer reconnect. Only remove
        # this handler's socket, never the replacement.
        if game.ws_connections.get(token) is websocket:
            game.ws_connections.pop(token, None)
        if game.game_logger:
            game.game_logger.log_ws_disconnect(hero_id if not is_spectator else None, is_spectator)

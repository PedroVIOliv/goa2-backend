"""REST endpoints under /games."""

from __future__ import annotations

import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from goa2.domain.input import InputResponse
from goa2.domain.models import GamePhase
from goa2.domain.views import build_view
from goa2.engine.session import GameSession, SessionResult
from goa2.domain.types import HeroID
from goa2.engine.setup import GameSetup
from goa2.server.auth import PlayerContext, get_current_player, get_registry
from goa2.server.errors import (
    AlreadyCommittedError,
    CardNotInHandError,
    InvalidPhaseError,
    validate_input_turn,
)
from goa2.server.models import (
    ActionResultResponse,
    CommitCardRequest,
    CreateGameRequest,
    CreateGameResponse,
    GameViewResponse,
    PlayerToken,
    SubmitInputRequest,
    GiveGoldRequest,
)
from goa2.domain.events import GameEvent, GameEventType
from goa2.server.registry import GameRegistry

router = APIRouter(prefix="/games", tags=["games"])


def _map_path(map_name: str) -> str:
    """Resolve a map name to its JSON file path."""
    base = os.path.join(os.path.dirname(__file__), "..", "data", "maps")
    path = os.path.normpath(os.path.join(base, f"{map_name}.json"))
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"Map '{map_name}' not found")
    return path


def _log_result(
    game,
    result: SessionResult,
    hero_id: str | None = None,
    action: str | None = None,
    detail: str | None = None,
) -> None:
    """Log a SessionResult to the game's logger."""
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


def _result_to_response(result: SessionResult) -> ActionResultResponse:
    return ActionResultResponse(
        result_type=result.result_type.value,
        current_phase=result.current_phase.value,
        events=[ev.model_dump() for ev in result.events],
        input_request=result.input_request.to_dict() if result.input_request else None,
        winner=result.winner,
    )


# ---- Endpoints ----


@router.post("", response_model=CreateGameResponse, status_code=201)
async def create_game(
    body: CreateGameRequest, registry: GameRegistry = Depends(get_registry)
) -> CreateGameResponse:
    map_path = _map_path(body.map_name)
    if body.game_type not in ("QUICK", "LONG"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid game_type '{body.game_type}'. Must be QUICK or LONG.",
        )
    state = GameSetup.create_game(
        map_path, body.red_heroes, body.blue_heroes, body.cheats_enabled, body.game_type
    )
    session = GameSession(state)

    hero_ids: List[str] = []
    for team in state.teams.values():
        for hero in team.heroes:
            hero_ids.append(hero.id)

    game = registry.create_game(session, hero_ids)

    if game.game_logger:
        game.game_logger.log_game_created(
            body.red_heroes, body.blue_heroes, body.map_name
        )

    return CreateGameResponse(
        game_id=game.game_id,
        player_tokens=[
            PlayerToken(hero_id=hid, token=tok)
            for hid, tok in game.hero_to_token.items()
        ],
        spectator_token=game.spectator_token,
    )


@router.get("/{game_id}", response_model=GameViewResponse)
async def get_game_view(
    game_id: str,
    player: PlayerContext = Depends(get_current_player),
    registry: GameRegistry = Depends(get_registry),
) -> GameViewResponse:
    game = registry.get(game_id)
    hero_id = player.hero_id if not player.is_spectator else None
    hero_id_typed = HeroID(hero_id) if hero_id else None
    view = build_view(game.session.state, for_hero_id=hero_id_typed)
    ir = game.last_result.input_request if game.last_result else None
    winner = game.last_result.winner if game.last_result else None
    return GameViewResponse(
        view=view,
        input_request=ir.to_dict() if ir else None,
        winner=winner,
    )


@router.post("/{game_id}/cards", response_model=ActionResultResponse)
async def commit_card(
    game_id: str,
    body: CommitCardRequest,
    player: PlayerContext = Depends(get_current_player),
    registry: GameRegistry = Depends(get_registry),
) -> ActionResultResponse:
    if player.is_spectator:
        raise HTTPException(status_code=403, detail="Spectators cannot commit cards")
    game = registry.get(game_id)

    async with game.lock:
        session = game.session
        if session.current_phase != GamePhase.PLANNING:
            raise InvalidPhaseError("PLANNING", session.current_phase.value)

        hero = session.state.get_hero(HeroID(player.hero_id))
        if hero is None:
            raise HTTPException(status_code=404, detail="Hero not found")

        card = next((c for c in hero.hand if c.id == body.card_id), None)
        if card is None:
            raise CardNotInHandError(body.card_id, player.hero_id)

        if player.hero_id in session.state.pending_inputs:
            raise AlreadyCommittedError(player.hero_id)

        result = session.commit_card(HeroID(player.hero_id), card)
        game.last_result = result
        if game.game_logger:
            game.game_logger.log_card_commit(player.hero_id, body.card_id)
        _log_result(game, result)
        registry.save_game(game_id)
        return _result_to_response(result)


@router.post("/{game_id}/pass", response_model=ActionResultResponse)
async def pass_turn(
    game_id: str,
    player: PlayerContext = Depends(get_current_player),
    registry: GameRegistry = Depends(get_registry),
) -> ActionResultResponse:
    if player.is_spectator:
        raise HTTPException(status_code=403, detail="Spectators cannot pass")
    game = registry.get(game_id)

    async with game.lock:
        session = game.session
        if session.current_phase != GamePhase.PLANNING:
            raise InvalidPhaseError("PLANNING", session.current_phase.value)

        result = session.pass_turn(HeroID(player.hero_id))
        game.last_result = result
        if game.game_logger:
            game.game_logger.log_pass_turn(player.hero_id)
        _log_result(game, result)
        registry.save_game(game_id)
        return _result_to_response(result)


@router.post("/{game_id}/input", response_model=ActionResultResponse)
async def submit_input(
    game_id: str,
    body: SubmitInputRequest,
    player: PlayerContext = Depends(get_current_player),
    registry: GameRegistry = Depends(get_registry),
) -> ActionResultResponse:
    if player.is_spectator:
        raise HTTPException(status_code=403, detail="Spectators cannot submit input")
    game = registry.get(game_id)

    async with game.lock:
        # Turn validation (skip for simultaneous phases like UPGRADE_PHASE)
        if game.last_result and game.last_result.input_request:
            expected = game.last_result.input_request.player_id
            validate_input_turn(expected, player.hero_id, game.session.state)

        response = InputResponse(
            request_id=body.request_id,
            selection=body.selection,
        )
        if game.game_logger:
            game.game_logger.log_input_response(player.hero_id, body.selection)
        result = game.session.advance(response)
        game.last_result = result
        _log_result(game, result)
        registry.save_game(game_id)
        return _result_to_response(result)


@router.post("/{game_id}/advance", response_model=ActionResultResponse)
async def advance(
    game_id: str,
    player: PlayerContext = Depends(get_current_player),
    registry: GameRegistry = Depends(get_registry),
) -> ActionResultResponse:
    if player.is_spectator:
        raise HTTPException(status_code=403, detail="Spectators cannot advance")
    game = registry.get(game_id)

    async with game.lock:
        result = game.session.advance()
        game.last_result = result
        _log_result(game, result)
        registry.save_game(game_id)
        return _result_to_response(result)


@router.post("/{game_id}/rollback", response_model=ActionResultResponse)
async def rollback_action(
    game_id: str,
    player: PlayerContext = Depends(get_current_player),
    registry: GameRegistry = Depends(get_registry),
) -> ActionResultResponse:
    if player.is_spectator:
        raise HTTPException(status_code=403, detail="Spectators cannot rollback")
    game = registry.get(game_id)

    async with game.lock:
        session = game.session
        if session.state.current_actor_id is None:
            raise HTTPException(
                status_code=400, detail="No active resolution to rollback"
            )
        if str(session.state.current_actor_id) != player.hero_id:
            raise HTTPException(
                status_code=403, detail="Only the current actor can rollback"
            )
        try:
            result = session.rollback()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        game.last_result = result
        _log_result(game, result)
        registry.save_game(game_id)
        return _result_to_response(result)


@router.post("/{game_id}/cheats/gold", response_model=ActionResultResponse)
async def give_gold_cheat(
    game_id: str,
    body: GiveGoldRequest,
    player: PlayerContext = Depends(get_current_player),
    registry: GameRegistry = Depends(get_registry),
) -> ActionResultResponse:
    if player.is_spectator:
        raise HTTPException(status_code=403, detail="Spectators cannot use cheats")
    game = registry.get(game_id)

    async with game.lock:
        session = game.session

        if not session.state.cheats_enabled:
            raise HTTPException(
                status_code=403, detail="Cheats are not enabled for this game"
            )

        if session.current_phase != GamePhase.PLANNING:
            raise InvalidPhaseError("PLANNING", session.current_phase.value)

        hero = session.state.get_hero(HeroID(body.hero_id))
        if hero is None:
            raise HTTPException(
                status_code=404, detail=f"Hero '{body.hero_id}' not found"
            )

        if body.amount <= 0:
            raise HTTPException(
                status_code=400, detail="Amount must be a positive integer"
            )

        hero.gold += body.amount

        event = GameEvent(
            event_type=GameEventType.GOLD_GAINED,
            actor_id=hero.id,
            metadata={"amount": body.amount, "reason": "cheat"},
        )

        result = ActionResultResponse(
            result_type="ACTION_COMPLETE",
            current_phase=session.current_phase.value,
            events=[event.model_dump()],
            input_request=None,
            winner=None,
        )

        if game.game_logger:
            game.game_logger.log_events([event.model_dump()])

        registry.save_game(game_id)
        return result

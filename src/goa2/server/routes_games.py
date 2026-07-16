"""REST endpoints under /games."""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, HTTPException

from goa2.domain.events import GameEvent, GameEventType
from goa2.domain.input import InputResponse
from goa2.domain.models import GamePhase
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.domain.views import build_view
from goa2.engine.session import GameSession, SessionResult
from goa2.engine.setup import GameSetup
from goa2.server.auth import PlayerDep, RegistryDep
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
    GiveGoldRequest,
    PlayerToken,
    SubmitInputRequest,
)
from goa2.server.visibility import events_for_viewer, input_request_for_viewer

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


def _result_to_response(
    result: SessionResult,
    state: GameState,
    for_hero_id: str,
) -> ActionResultResponse:
    return ActionResultResponse(
        result_type=result.result_type.value,
        current_phase=result.current_phase.value,
        events=events_for_viewer([ev.model_dump() for ev in result.events], state, for_hero_id),
        input_request=input_request_for_viewer(result.input_request, state, for_hero_id),
        winner=result.winner,
    )


# ---- Endpoints ----


@router.post("", response_model=CreateGameResponse, status_code=201)
async def create_game(body: CreateGameRequest, registry: RegistryDep) -> CreateGameResponse:
    map_path = _map_path(body.map_name)
    if body.game_type not in ("QUICK", "LONG"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid game_type '{body.game_type}'. Must be QUICK or LONG.",
        )
    game_seed_id = uuid.uuid4().hex
    game_id = game_seed_id[:12]
    seed = int(game_seed_id, 16)
    state = GameSetup.create_game(
        map_path,
        body.red_heroes,
        body.blue_heroes,
        body.cheats_enabled,
        body.game_type,
        seed=seed,
    )
    session = GameSession(state)

    hero_ids: list[str] = []
    for team in state.teams.values():
        for hero in team.heroes:
            hero_ids.append(hero.id)

    game = registry.create_game(session, hero_ids, game_id=game_id)

    if game.game_logger:
        game.game_logger.log_game_created(body.red_heroes, body.blue_heroes, body.map_name)
    if game.replay_recorder:
        game.replay_recorder.record_setup(
            map_name=body.map_name,
            red_heroes=body.red_heroes,
            blue_heroes=body.blue_heroes,
            game_type=body.game_type,
            cheats=body.cheats_enabled,
            seed=seed,
        )

    return CreateGameResponse(
        game_id=game.game_id,
        player_tokens=[
            PlayerToken(hero_id=hid, token=tok) for hid, tok in game.hero_to_token.items()
        ],
        spectator_token=game.spectator_token,
    )


@router.get("/{game_id}", response_model=GameViewResponse)
async def get_game_view(
    game_id: str,
    player: PlayerDep,
    registry: RegistryDep,
) -> GameViewResponse:
    game = registry.get(game_id)
    hero_id = player.hero_id if not player.is_spectator else None
    hero_id_typed = HeroID(hero_id) if hero_id else None
    view = build_view(game.session.state, for_hero_id=hero_id_typed)
    ir = game.last_result.input_request if game.last_result else None
    winner = game.last_result.winner if game.last_result else None
    return GameViewResponse(
        view=view,
        input_request=input_request_for_viewer(ir, game.session.state, hero_id),
        winner=winner,
    )


@router.post("/{game_id}/cards", response_model=ActionResultResponse)
async def commit_card(
    game_id: str,
    body: CommitCardRequest,
    player: PlayerDep,
    registry: RegistryDep,
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
            # A hero whose active ultimate allows two cards (Emmitt) may
            # commit a second one; everyone else is rejected here.
            from goa2.engine.phases import hero_can_play_two_cards

            if (
                not hero_can_play_two_cards(hero)
                or player.hero_id in session.state.pending_second_cards
                or player.hero_id in session.state.planning_done
            ):
                raise AlreadyCommittedError(player.hero_id)

        if game.replay_recorder:
            game.replay_recorder.record_commit(
                player.hero_id, body.card_id, session.state.round, session.state.turn
            )
        result = session.commit_card(HeroID(player.hero_id), card)
        game.last_result = result
        if game.game_logger:
            game.game_logger.log_card_commit(player.hero_id, body.card_id)
        _log_result(game, result)
        registry.save_game(game_id)
        return _result_to_response(result, session.state, player.hero_id)


@router.post("/{game_id}/uncommit", response_model=ActionResultResponse)
async def uncommit_card(
    game_id: str,
    player: PlayerDep,
    registry: RegistryDep,
) -> ActionResultResponse:
    """Take a committed card back into hand during Planning (board-game
    take-back; LIFO for a two-card hero). Allowed until the last player
    commits — that commit runs revelation synchronously, so a late uncommit
    gets a 409 phase error."""
    if player.is_spectator:
        raise HTTPException(status_code=403, detail="Spectators cannot uncommit cards")
    game = registry.get(game_id)

    async with game.lock:
        session = game.session
        if session.current_phase != GamePhase.PLANNING:
            raise InvalidPhaseError("PLANNING", session.current_phase.value)

        # NOTE: validate+mutate stays synchronous under game.lock — that is
        # what makes an uncommit racing the final commit resolve cleanly
        # (one side simply loses; state never corrupts). Don't add awaits
        # between the phase check and the session call.
        state = session.state
        hid = HeroID(player.hero_id)
        card = state.pending_second_cards.get(hid) or state.pending_inputs.get(hid)
        rec_round, rec_turn = state.round, state.turn
        result = session.uncommit_card(hid)
        # Record only after success so a failed attempt never lands in the
        # replay (contrast: commits pre-validate, so they can record first).
        if game.replay_recorder:
            game.replay_recorder.record_uncommit(hid, rec_round, rec_turn)
        game.last_result = result
        if game.game_logger and card is not None:
            game.game_logger.log_card_uncommit(hid, card.id)
        _log_result(game, result)
        registry.save_game(game_id)
        return _result_to_response(result, session.state, player.hero_id)


@router.post("/{game_id}/pass", response_model=ActionResultResponse)
async def pass_turn(
    game_id: str,
    player: PlayerDep,
    registry: RegistryDep,
) -> ActionResultResponse:
    if player.is_spectator:
        raise HTTPException(status_code=403, detail="Spectators cannot pass")
    game = registry.get(game_id)

    async with game.lock:
        session = game.session
        if session.current_phase != GamePhase.PLANNING:
            raise InvalidPhaseError("PLANNING", session.current_phase.value)

        if game.replay_recorder:
            game.replay_recorder.record_pass(
                player.hero_id, session.state.round, session.state.turn
            )
        result = session.pass_turn(HeroID(player.hero_id))
        game.last_result = result
        if game.game_logger:
            game.game_logger.log_pass_turn(player.hero_id)
        _log_result(game, result)
        registry.save_game(game_id)
        return _result_to_response(result, session.state, player.hero_id)


@router.post("/{game_id}/planning-done", response_model=ActionResultResponse)
async def planning_done(
    game_id: str,
    player: PlayerDep,
    registry: RegistryDep,
) -> ActionResultResponse:
    """Done-signal for a hero who may play two cards (Emmitt's ultimate) but
    chooses to play only one this turn. Requires a committed card."""
    if player.is_spectator:
        raise HTTPException(status_code=403, detail="Spectators cannot finish planning")
    game = registry.get(game_id)

    async with game.lock:
        session = game.session
        if session.current_phase != GamePhase.PLANNING:
            raise InvalidPhaseError("PLANNING", session.current_phase.value)

        if game.replay_recorder:
            game.replay_recorder.record_finish_planning(
                player.hero_id, session.state.round, session.state.turn
            )
        result = session.finish_planning(HeroID(player.hero_id))
        game.last_result = result
        _log_result(game, result)
        registry.save_game(game_id)
        return _result_to_response(result, session.state, player.hero_id)


@router.post("/{game_id}/input", response_model=ActionResultResponse)
async def submit_input(
    game_id: str,
    body: SubmitInputRequest,
    player: PlayerDep,
    registry: RegistryDep,
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
        # Record only after the engine accepts the input, tagged with the
        # pre-advance round/turn, so a rejected selection leaves no phantom decision.
        rec_round, rec_turn = game.session.state.round, game.session.state.turn
        result = game.session.advance(response)
        if game.replay_recorder:
            game.replay_recorder.record_input(player.hero_id, body.selection, rec_round, rec_turn)
        game.last_result = result
        _log_result(game, result)
        registry.save_game(game_id)
        return _result_to_response(result, game.session.state, player.hero_id)


@router.post("/{game_id}/advance", response_model=ActionResultResponse)
async def advance(
    game_id: str,
    player: PlayerDep,
    registry: RegistryDep,
) -> ActionResultResponse:
    if player.is_spectator:
        raise HTTPException(status_code=403, detail="Spectators cannot advance")
    game = registry.get(game_id)

    async with game.lock:
        result = game.session.advance()
        game.last_result = result
        _log_result(game, result)
        registry.save_game(game_id)
        return _result_to_response(result, game.session.state, player.hero_id)


@router.post("/{game_id}/rollback", response_model=ActionResultResponse)
async def rollback_action(
    game_id: str,
    player: PlayerDep,
    registry: RegistryDep,
) -> ActionResultResponse:
    if player.is_spectator:
        raise HTTPException(status_code=403, detail="Spectators cannot rollback")
    game = registry.get(game_id)

    async with game.lock:
        session = game.session
        if session.state.current_actor_id is None:
            raise HTTPException(status_code=400, detail="No active resolution to rollback")
        # Authorize against whoever the pending input is addressed to — under
        # Hanu's ultimate that is the controller, not the controlled actor.
        if game.current_responder != player.hero_id:
            raise HTTPException(status_code=403, detail="Only the current actor can rollback")
        rec_round, rec_turn = session.state.round, session.state.turn
        try:
            result = session.rollback()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if game.replay_recorder:
            game.replay_recorder.record_rollback(player.hero_id, rec_round, rec_turn)
        game.last_result = result
        _log_result(game, result)
        registry.save_game(game_id)
        return _result_to_response(result, session.state, player.hero_id)


@router.post("/{game_id}/cheats/gold", response_model=ActionResultResponse)
async def give_gold_cheat(
    game_id: str,
    body: GiveGoldRequest,
    player: PlayerDep,
    registry: RegistryDep,
) -> ActionResultResponse:
    if player.is_spectator:
        raise HTTPException(status_code=403, detail="Spectators cannot use cheats")
    game = registry.get(game_id)

    async with game.lock:
        session = game.session

        if not session.state.cheats_enabled:
            raise HTTPException(status_code=403, detail="Cheats are not enabled for this game")

        if session.current_phase != GamePhase.PLANNING:
            raise InvalidPhaseError("PLANNING", session.current_phase.value)

        hero = session.state.get_hero(HeroID(body.hero_id))
        if hero is None:
            raise HTTPException(status_code=404, detail=f"Hero '{body.hero_id}' not found")

        if body.amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be a positive integer")

        hero.gold += body.amount
        if game.replay_recorder:
            game.replay_recorder.record_cheat_gold(
                body.hero_id, body.amount, session.state.round, session.state.turn
            )

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

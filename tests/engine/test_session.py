"""
Tests for Phase 2: Engine Self-Containment.

Tests for submit_input(), process_stack(), GameSession, and SessionResult.
"""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, GamePhase
from goa2.domain.models.unit import Hero
from goa2.domain.input import InputResponse, InputRequest
from goa2.engine.handler import submit_input, process_stack, push_steps
from goa2.engine.steps import SelectStep, LogMessageStep
from goa2.domain.models.enums import TargetType


@pytest.fixture
def empty_state():
    board = Board()
    hero = Hero(id="hero_a", name="HeroA", team=TeamColor.RED, deck=[])
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        current_actor_id="hero_a",
    )
    h = Hex(q=0, r=0, s=0)
    board.tiles[h] = board.get_tile(h)
    state.place_entity("hero_a", h)
    return state


class TestSubmitInput:
    def test_accepts_dict(self, empty_state):
        """submit_input with legacy dict sets pending_input."""
        step = SelectStep(target_type=TargetType.UNIT, prompt="Pick")
        push_steps(empty_state, [step])
        submit_input(empty_state, {"selection": "hero_a"})
        assert empty_state.execution_stack[-1].pending_input == {"selection": "hero_a"}

    def test_accepts_input_response(self, empty_state):
        """submit_input with InputResponse converts to dict."""
        step = SelectStep(target_type=TargetType.UNIT, prompt="Pick")
        push_steps(empty_state, [step])
        resp = InputResponse(selection="hero_a")
        submit_input(empty_state, resp)
        assert empty_state.execution_stack[-1].pending_input is not None
        assert empty_state.execution_stack[-1].pending_input.get("selection") == "hero_a"

    def test_empty_stack_raises(self, empty_state):
        """submit_input with no pending step raises ValueError."""
        with pytest.raises(ValueError, match="No pending step"):
            submit_input(empty_state, {"selection": "x"})


class TestProcessStack:
    def test_returns_input_request(self, empty_state):
        """process_stack returns typed InputRequest instead of dict."""
        step = SelectStep(target_type=TargetType.UNIT, prompt="Pick a unit")
        push_steps(empty_state, [step])
        result = process_stack(empty_state)
        assert isinstance(result, InputRequest)
        assert result.prompt == "Pick a unit"

    def test_returns_none_when_empty(self, empty_state):
        """process_stack returns None when stack is empty."""
        result = process_stack(empty_state)
        assert result is None

    def test_processes_non_input_steps(self, empty_state):
        """process_stack processes steps that don't need input."""
        step = LogMessageStep(message="hello")
        push_steps(empty_state, [step])
        result = process_stack(empty_state)
        assert result is None


# =============================================================================
# Task 2: SessionResult and GameSession
# =============================================================================

from goa2.engine.session import GameSession, SessionResult, SessionResultType
from goa2.domain.input import InputRequestType


class TestSessionResult:
    def test_input_needed(self):
        req = InputRequest(
            request_type=InputRequestType.SELECT_UNIT,
            player_id="hero_a",
            prompt="Pick",
        )
        result = SessionResult(
            result_type=SessionResultType.INPUT_NEEDED,
            input_request=req,
            current_phase=GamePhase.RESOLUTION,
        )
        assert result.result_type == SessionResultType.INPUT_NEEDED
        assert result.input_request is req

    def test_phase_changed(self):
        result = SessionResult(
            result_type=SessionResultType.PHASE_CHANGED,
            current_phase=GamePhase.REVELATION,
        )
        assert result.result_type == SessionResultType.PHASE_CHANGED

    def test_game_over(self):
        result = SessionResult(
            result_type=SessionResultType.GAME_OVER,
            current_phase=GamePhase.GAME_OVER,
            winner="RED",
        )
        assert result.winner == "RED"


class TestGameSessionInit:
    def test_wraps_state(self, empty_state):
        session = GameSession(empty_state)
        assert session.state is empty_state
        assert session.current_phase == empty_state.phase

    def test_advance_in_planning_raises(self, empty_state):
        empty_state.phase = GamePhase.PLANNING
        session = GameSession(empty_state)
        with pytest.raises(ValueError, match="PLANNING"):
            session.advance()

    def test_commit_card_wrong_phase_raises(self, empty_state):
        empty_state.phase = GamePhase.RESOLUTION
        session = GameSession(empty_state)
        hero = empty_state.teams[TeamColor.RED].heroes[0]
        with pytest.raises(ValueError, match="Cannot commit card"):
            session.commit_card(hero.id, hero.deck[0] if hero.deck else None)

    def test_advance_processes_stack(self, empty_state):
        """advance() with no pending input processes the stack."""
        empty_state.phase = GamePhase.RESOLUTION
        session = GameSession(empty_state)
        step = SelectStep(target_type=TargetType.UNIT, prompt="Pick")
        push_steps(empty_state, [step])
        result = session.advance()
        assert result.result_type == SessionResultType.INPUT_NEEDED

    def test_advance_with_response(self, empty_state):
        """advance(response) applies input then processes stack."""
        empty_state.phase = GamePhase.RESOLUTION
        session = GameSession(empty_state)
        step = SelectStep(target_type=TargetType.UNIT, prompt="Pick")
        push_steps(empty_state, [step])
        # First advance to get input request
        result = session.advance()
        assert result.result_type == SessionResultType.INPUT_NEEDED
        # Now provide input
        result = session.advance({"selection": "hero_a"})
        # Step should resolve (hero_a is valid target on the board)
        assert result.result_type in (
            SessionResultType.ACTION_COMPLETE,
            SessionResultType.INPUT_NEEDED,
            SessionResultType.PHASE_CHANGED,
        )


# =============================================================================
# Task 3: GameSession planning + advance integration tests
# =============================================================================

import goa2.scripts.arien_effects  # noqa: F401
import goa2.scripts.wasp_effects  # noqa: F401
from goa2.engine.setup import GameSetup
from goa2.domain.types import HeroID


@pytest.fixture
def game_session():
    """Full game session in PLANNING phase."""
    state = GameSetup.create_game(
        map_path="src/goa2/data/maps/forgotten_island.json",
        red_heroes=["Arien"],
        blue_heroes=["Wasp"],
    )
    return GameSession(state)


class TestGameSessionPlanning:
    def test_commit_card_no_transition(self, game_session):
        """Committing one hero's card doesn't transition phase."""
        hero = game_session.state.teams[TeamColor.RED].heroes[0]
        card = hero.hand[0]
        result = game_session.commit_card(HeroID(hero.id), card)
        assert result.result_type == SessionResultType.ACTION_COMPLETE
        assert game_session.current_phase == GamePhase.PLANNING

    def test_commit_all_transitions(self, game_session):
        """Committing all heroes' cards transitions out of planning."""
        red = game_session.state.teams[TeamColor.RED].heroes[0]
        blue = game_session.state.teams[TeamColor.BLUE].heroes[0]
        game_session.commit_card(HeroID(red.id), red.hand[0])
        result = game_session.commit_card(HeroID(blue.id), blue.hand[0])
        # Should have transitioned and possibly hit an input request
        assert result.result_type in (
            SessionResultType.INPUT_NEEDED,
            SessionResultType.ACTION_COMPLETE,
            SessionResultType.PHASE_CHANGED,
        )
        assert game_session.current_phase != GamePhase.PLANNING

    def test_commit_wrong_phase_raises(self, game_session):
        game_session.state.phase = GamePhase.RESOLUTION
        hero = game_session.state.teams[TeamColor.RED].heroes[0]
        with pytest.raises(ValueError, match="Cannot commit card"):
            game_session.commit_card(HeroID(hero.id), hero.hand[0])

    def test_advance_in_planning_raises(self, game_session):
        with pytest.raises(ValueError, match="PLANNING"):
            game_session.advance()


def _make_response_dict(req: InputRequest) -> dict:
    """Build a legacy response dict that matches what each step type expects.

    Different steps expect different dict keys for their pending_input.
    This helper picks the right key based on the request type.
    """
    opt = req.options[0] if req.options else None
    sel = opt.id if opt else "SKIP"
    rt = req.request_type.value

    if rt in ("CHOOSE_ACTION", "ACTION_CHOICE"):
        return {"choice_id": sel}
    elif rt in ("DEFENSE_CARD", "SELECT_CARD_OR_PASS", "UPGRADE_CHOICE", "UPGRADE_PHASE"):
        return {"selected_card_id": sel}
    elif rt == "TIE_BREAKER":
        return {"winner_id": sel}
    elif rt == "CHOOSE_ACTOR":
        return {"selected_hero_id": sel}
    elif rt in ("CHOOSE_RESPAWN", "CHOOSE_RESPAWN_HEX"):
        if sel in ("RESPAWN", "PASS"):
            return {"choice": sel}
        return {"spawn_hex": sel}
    elif rt == "CONFIRM_PASSIVE":
        return {"choice": sel}
    elif rt == "SELECT_HEX":
        # Hex options store the hex dict in metadata
        if opt and "hex" in opt.metadata:
            return {"selection": opt.metadata["hex"]}
        return {"selection": sel}
    else:
        return {"selection": sel}


class TestGameSessionAdvance:
    def test_advance_returns_input_or_complete(self, game_session):
        """After planning, advance() returns INPUT_NEEDED or ACTION_COMPLETE."""
        red = game_session.state.teams[TeamColor.RED].heroes[0]
        blue = game_session.state.teams[TeamColor.BLUE].heroes[0]
        game_session.commit_card(HeroID(red.id), red.hand[0])
        game_session.commit_card(HeroID(blue.id), blue.hand[0])

        result = game_session.advance()
        assert result.result_type in (
            SessionResultType.INPUT_NEEDED,
            SessionResultType.ACTION_COMPLETE,
            SessionResultType.PHASE_CHANGED,
            SessionResultType.GAME_OVER,
        )

    def test_advance_with_response(self, game_session):
        """advance(response) applies input and continues."""
        red = game_session.state.teams[TeamColor.RED].heroes[0]
        blue = game_session.state.teams[TeamColor.BLUE].heroes[0]
        game_session.commit_card(HeroID(red.id), red.hand[0])
        result = game_session.commit_card(HeroID(blue.id), blue.hand[0])

        # Find first INPUT_NEEDED
        iterations = 0
        while result.result_type != SessionResultType.INPUT_NEEDED and iterations < 20:
            if result.result_type == SessionResultType.GAME_OVER:
                pytest.skip("Game ended")
            result = game_session.advance()
            iterations += 1

        if result.result_type == SessionResultType.INPUT_NEEDED:
            req = result.input_request
            response = _make_response_dict(req)
            result = game_session.advance(response)
            assert result.result_type in (
                SessionResultType.INPUT_NEEDED,
                SessionResultType.ACTION_COMPLETE,
                SessionResultType.PHASE_CHANGED,
                SessionResultType.GAME_OVER,
            )


class TestGameSessionIntegration:
    def test_full_turn(self, game_session):
        """Play a full turn via session: plan -> resolve -> back to planning."""
        session = game_session
        red = session.state.teams[TeamColor.RED].heroes[0]
        blue = session.state.teams[TeamColor.BLUE].heroes[0]

        # Planning
        session.commit_card(HeroID(red.id), red.hand[0])
        result = session.commit_card(HeroID(blue.id), blue.hand[0])

        # Resolution loop
        max_iter = 100
        i = 0
        while session.current_phase not in (GamePhase.PLANNING, GamePhase.GAME_OVER):
            if result.result_type == SessionResultType.INPUT_NEEDED:
                req = result.input_request
                if req.options:
                    response = _make_response_dict(req)
                elif req.can_skip:
                    response = {"selection": "SKIP"}
                else:
                    break
                result = session.advance(response)
            else:
                result = session.advance()
            i += 1
            if i >= max_iter:
                break

        assert i < max_iter, "Resolution loop did not terminate"
        assert session.current_phase in (GamePhase.PLANNING, GamePhase.GAME_OVER)

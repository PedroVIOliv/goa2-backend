"""Tests for Phase 3: Event emission from steps and collection in handler."""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Tile
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, GamePhase
from goa2.domain.models.unit import Hero
from goa2.domain.models.enums import TargetType
from goa2.domain.events import GameEvent, GameEventType
from goa2.engine.handler import process_stack, push_steps, StackResult
from goa2.engine.steps import (
    StepResult,
    MoveUnitStep,
    PlaceUnitStep,
    RemoveUnitStep,
    FinalizeHeroTurnStep,
    TriggerGameOverStep,
    LogMessageStep,
)


@pytest.fixture
def two_hex_state():
    """State with hero_a at (0,0,0) and an empty tile at (1,0,-1)."""
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
    h0 = Hex(q=0, r=0, s=0)
    h1 = Hex(q=1, r=0, s=-1)
    board.tiles[h0] = Tile(hex=h0)
    board.tiles[h1] = Tile(hex=h1)
    state.place_entity("hero_a", h0)
    return state


class TestStepResultEvents:
    def test_defaults_to_empty_list(self):
        r = StepResult()
        assert r.events == []

    def test_events_field(self):
        e = GameEvent(event_type=GameEventType.TURN_ENDED, actor_id="hero_a")
        r = StepResult(events=[e])
        assert len(r.events) == 1
        assert r.events[0].event_type == GameEventType.TURN_ENDED


class TestHandlerCollectsEvents:
    def test_collects_from_single_step(self, two_hex_state):
        """Handler collects events emitted by a single step."""
        dest = Hex(q=1, r=0, s=-1)
        push_steps(
            two_hex_state,
            [MoveUnitStep(unit_id="hero_a", target_hex_arg=dest, range_val=1)],
        )
        result = process_stack(two_hex_state)
        assert isinstance(result, StackResult)
        assert len(result.events) >= 1
        move_events = [
            e for e in result.events if e.event_type == GameEventType.UNIT_MOVED
        ]
        assert len(move_events) == 1
        assert move_events[0].actor_id == "hero_a"
        assert move_events[0].from_hex == {"q": 0, "r": 0, "s": 0}
        assert move_events[0].to_hex == {"q": 1, "r": 0, "s": -1}

    def test_collects_from_multiple_steps(self, two_hex_state):
        """Handler accumulates events from multiple steps."""
        dest = Hex(q=1, r=0, s=-1)
        push_steps(
            two_hex_state,
            [
                LogMessageStep(message="hello"),
                MoveUnitStep(unit_id="hero_a", target_hex_arg=dest, range_val=1),
            ],
        )
        result = process_stack(two_hex_state)
        # LogMessageStep emits no events, MoveUnitStep emits 1
        move_events = [
            e for e in result.events if e.event_type == GameEventType.UNIT_MOVED
        ]
        assert len(move_events) == 1

    def test_no_events_from_empty_stack(self, two_hex_state):
        result = process_stack(two_hex_state)
        assert result.events == []

    def test_no_events_from_non_emitting_step(self, two_hex_state):
        push_steps(two_hex_state, [LogMessageStep(message="nothing")])
        result = process_stack(two_hex_state)
        assert result.events == []


class TestMoveUnitStepEvent:
    def test_emits_unit_moved(self, two_hex_state):
        dest = Hex(q=1, r=0, s=-1)
        step = MoveUnitStep(unit_id="hero_a", target_hex_arg=dest, range_val=1)
        result = step.resolve(two_hex_state, two_hex_state.execution_context)
        assert len(result.events) == 1
        e = result.events[0]
        assert e.event_type == GameEventType.UNIT_MOVED
        assert e.metadata["range"] == 1


class TestPlaceUnitStepEvent:
    def test_emits_unit_placed(self, two_hex_state):
        dest = Hex(q=1, r=0, s=-1)
        step = PlaceUnitStep(unit_id="hero_a", target_hex_arg=dest)
        result = step.resolve(two_hex_state, two_hex_state.execution_context)
        assert len(result.events) == 1
        e = result.events[0]
        assert e.event_type == GameEventType.UNIT_PLACED
        assert e.to_hex == {"q": 1, "r": 0, "s": -1}


class TestRemoveUnitStepEvent:
    def test_emits_unit_removed(self, two_hex_state):
        step = RemoveUnitStep(unit_id="hero_a")
        result = step.resolve(two_hex_state, two_hex_state.execution_context)
        assert len(result.events) == 1
        e = result.events[0]
        assert e.event_type == GameEventType.UNIT_REMOVED
        assert e.target_id == "hero_a"
        assert e.from_hex == {"q": 0, "r": 0, "s": 0}


class TestFinalizeHeroTurnStepEvent:
    def test_emits_turn_ended(self, two_hex_state):
        step = FinalizeHeroTurnStep(hero_id="hero_a")
        result = step.resolve(two_hex_state, two_hex_state.execution_context)
        turn_events = [
            e for e in result.events if e.event_type == GameEventType.TURN_ENDED
        ]
        assert len(turn_events) == 1
        assert turn_events[0].actor_id == "hero_a"


class TestTriggerGameOverStepEvent:
    def test_emits_game_over(self, two_hex_state):
        step = TriggerGameOverStep(winner=TeamColor.RED, condition="ANNIHILATION")
        result = step.resolve(two_hex_state, two_hex_state.execution_context)
        assert len(result.events) == 1
        e = result.events[0]
        assert e.event_type == GameEventType.GAME_OVER
        assert e.metadata["winner"] == "RED"
        assert e.metadata["condition"] == "ANNIHILATION"


class TestSessionResultEvents:
    def test_advance_returns_events(self):
        """GameSession.advance() populates SessionResult.events."""
        import goa2.scripts.arien_effects  # noqa: F401
        import goa2.scripts.wasp_effects  # noqa: F401
        from goa2.engine.setup import GameSetup
        from goa2.engine.session import GameSession, SessionResultType
        from goa2.domain.types import HeroID

        state = GameSetup.create_game(
            map_path="src/goa2/data/maps/forgotten_island.json",
            red_heroes=["Arien"],
            blue_heroes=["Wasp"],
        )
        session = GameSession(state)

        red = state.teams[TeamColor.RED].heroes[0]
        blue = state.teams[TeamColor.BLUE].heroes[0]

        session.commit_card(HeroID(red.id), red.hand[0])
        result = session.commit_card(HeroID(blue.id), blue.hand[0])

        # Drive through resolution collecting events
        all_events = list(result.events)
        max_iter = 100
        for _ in range(max_iter):
            if session.current_phase in (GamePhase.PLANNING, GamePhase.GAME_OVER):
                break
            if result.result_type == SessionResultType.INPUT_NEEDED:
                req = result.input_request
                if not req or not req.options:
                    break
                opt = req.options[0]
                rt = req.request_type.value
                if rt in ("CHOOSE_ACTION", "ACTION_CHOICE"):
                    resp = {"choice_id": opt.id}
                elif rt in ("DEFENSE_CARD", "SELECT_CARD_OR_PASS", "UPGRADE_CHOICE", "UPGRADE_PHASE"):
                    resp = {"selected_card_id": opt.id}
                elif rt == "TIE_BREAKER":
                    resp = {"winner_id": opt.id}
                elif rt == "CHOOSE_ACTOR":
                    resp = {"selected_hero_id": opt.id}
                elif rt in ("CHOOSE_RESPAWN", "CHOOSE_RESPAWN_HEX"):
                    if opt.id in ("RESPAWN", "PASS"):
                        resp = {"choice": opt.id}
                    else:
                        resp = {"spawn_hex": opt.id}
                elif rt == "CONFIRM_PASSIVE":
                    resp = {"choice": opt.id}
                elif rt == "SELECT_HEX":
                    if "hex" in opt.metadata:
                        resp = {"selection": opt.metadata["hex"]}
                    else:
                        resp = {"selection": opt.id}
                else:
                    resp = {"selection": opt.id}
                result = session.advance(resp)
            else:
                result = session.advance()
            all_events.extend(result.events)

        # After a full turn, we should have collected some events
        assert len(all_events) > 0
        # Should have at least one TURN_ENDED event
        turn_ended = [e for e in all_events if e.event_type == GameEventType.TURN_ENDED]
        assert len(turn_ended) >= 1

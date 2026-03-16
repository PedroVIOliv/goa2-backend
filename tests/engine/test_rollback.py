"""Tests for Action Resolution Rollback & Confirmation."""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import (
    Team, TeamColor, Card, CardTier, CardColor, ActionType, GamePhase,
)
from goa2.domain.models.unit import Hero
from goa2.domain.types import HeroID
from goa2.domain.input import InputResponse
from goa2.engine.handler import (
    process_stack, process_resolution_stack, submit_input, push_steps,
)
from goa2.engine.steps import (
    ConfirmResolutionStep, ResolveCardStep, FinalizeHeroTurnStep,
    ReactionWindowStep, SelectStep, AskConfirmationStep,
)
from goa2.engine.filters import TeamFilter
from goa2.engine.session import GameSession, SessionResultType
from goa2.engine.phases import start_resolution_phase
from goa2.domain.models.enums import TargetType, StepType


def _make_card(card_id, initiative, action=ActionType.SKILL):
    return Card(
        id=card_id, name=f"Card {card_id}", tier=CardTier.I, color=CardColor.RED,
        initiative=initiative, primary_action=action, primary_action_value=None,
        secondary_actions={ActionType.HOLD: 0},
        effect_id="e", effect_text="t", is_facedown=False,
    )


def _filler_cards():
    return [Card(
        id=f"filler_{i}", name=f"Filler {i}", tier=CardTier.I, color=CardColor.RED,
        initiative=1, primary_action=ActionType.SKILL, primary_action_value=None,
        effect_id="e", effect_text="t",
    ) for i in range(3)]


def _make_state():
    """Two-hero state: hero_a (RED, init 20), hero_b (BLUE, init 10)."""
    hero_a = Hero(id=HeroID("hero_a"), name="A", team=TeamColor.RED, deck=[], hand=_filler_cards())
    hero_b = Hero(id=HeroID("hero_b"), name="B", team=TeamColor.BLUE, deck=[], hand=_filler_cards())
    board = Board()
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero_a], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[hero_b], minions=[]),
        },
    )
    state.place_entity("hero_a", Hex(q=0, r=0, s=0))
    state.place_entity("hero_b", Hex(q=2, r=0, s=-2))
    return state


def _setup_resolution(state):
    """Set up cards and start resolution phase."""
    state.get_hero("hero_a").current_turn_card = _make_card("card_a", 20)
    state.get_hero("hero_b").current_turn_card = _make_card("card_b", 10)
    state.unresolved_hero_ids = ["hero_a", "hero_b"]
    start_resolution_phase(state)


# ---- ConfirmResolutionStep basic behavior ----


class TestConfirmResolutionStep:
    def test_prompts_confirm_rollback(self):
        """Confirm step shows CONFIRM/ROLLBACK options when rollback is available."""
        step = ConfirmResolutionStep(hero_id="hero_a")
        state = _make_state()
        state.current_actor_id = "hero_a"
        result = step.resolve(state, {})
        assert result.requires_input
        req = result.input_request
        assert req.player_id == "hero_a"
        option_ids = [o.id for o in req.options]
        assert "CONFIRM" in option_ids
        assert "ROLLBACK" in option_ids

    def test_auto_skips_when_rollback_disabled(self):
        """Confirm step auto-confirms when rollback is disabled."""
        step = ConfirmResolutionStep(hero_id="hero_a")
        state = _make_state()
        state.current_actor_id = "hero_a"
        result = step.resolve(state, {"rollback_disabled": True})
        assert result.is_finished
        assert not result.requires_input

    def test_confirm_input_finishes(self):
        """Submitting CONFIRM finishes the step."""
        step = ConfirmResolutionStep(hero_id="hero_a")
        step.pending_input = {"selection": "CONFIRM"}
        state = _make_state()
        state.current_actor_id = "hero_a"
        result = step.resolve(state, {})
        assert result.is_finished


# ---- Rollback disabled tracking ----


class TestRollbackDisabled:
    def test_other_player_input_disables_rollback(self):
        """When a step prompts a non-actor player, rollback_disabled is set."""
        state = _make_state()
        state.current_actor_id = "hero_a"
        # Use AskConfirmationStep which allows setting player_id directly
        step = AskConfirmationStep(player_id="hero_b", prompt="Block?")
        push_steps(state, [step])
        stack_result = process_stack(state)
        assert stack_result.input_request is not None
        assert stack_result.input_request.player_id == "hero_b"
        assert state.execution_context.get("rollback_disabled") is True

    def test_same_player_input_does_not_disable_rollback(self):
        """When a step prompts the current actor, rollback_disabled is NOT set."""
        state = _make_state()
        state.current_actor_id = "hero_a"
        step = AskConfirmationStep(player_id="hero_a", prompt="Continue?")
        push_steps(state, [step])
        stack_result = process_stack(state)
        assert stack_result.input_request is not None
        assert stack_result.input_request.player_id == "hero_a"
        assert state.execution_context.get("rollback_disabled") is not True


# ---- GameSession rollback ----


class TestSessionRollback:
    def test_rollback_raises_when_no_snapshot(self):
        """rollback() raises ValueError when there's no snapshot."""
        state = _make_state()
        session = GameSession(state)
        with pytest.raises(ValueError, match="No rollback snapshot"):
            session.rollback()

    def test_basic_rollback_flow(self):
        """Start resolution -> choose action -> rollback -> back to action choice."""
        state = _make_state()
        session = GameSession(state)
        _setup_resolution(state)

        # Process stack to get first action choice
        result = session.advance()
        assert result.result_type == SessionResultType.INPUT_NEEDED
        assert result.input_request is not None
        assert result.input_request.player_id == "hero_a"
        assert result.input_request.can_rollback is True
        # Snapshot should be taken
        assert session._rollback_snapshot is not None

        # Choose HOLD
        result2 = session.advance(InputResponse(selection="HOLD"))
        # Should be at ConfirmResolutionStep
        assert result2.result_type == SessionResultType.INPUT_NEEDED
        assert result2.input_request.can_rollback is True

        # Rollback
        result3 = session.rollback()
        assert result3.result_type == SessionResultType.INPUT_NEEDED
        assert result3.input_request is not None
        # Back to action choice
        assert result3.input_request.player_id == "hero_a"
        assert result3.input_request.can_rollback is True

    def test_multiple_rollbacks(self):
        """Rollback, choose differently, rollback again."""
        state = _make_state()
        session = GameSession(state)
        _setup_resolution(state)

        # Get first action choice
        result = session.advance()
        assert result.input_request.player_id == "hero_a"

        # Choose HOLD
        session.advance(InputResponse(selection="HOLD"))

        # Rollback
        r = session.rollback()
        assert r.input_request.player_id == "hero_a"

        # Choose HOLD again
        session.advance(InputResponse(selection="HOLD"))

        # Rollback again
        r2 = session.rollback()
        assert r2.input_request.player_id == "hero_a"

    def test_snapshot_cleared_after_turn(self):
        """After confirm -> finalize, snapshot is cleared."""
        state = _make_state()
        session = GameSession(state)
        _setup_resolution(state)

        # hero_a's action choice
        session.advance()
        assert session._rollback_snapshot is not None

        # Choose HOLD
        session.advance(InputResponse(selection="HOLD"))

        # Confirm
        result = session.advance(InputResponse(selection="CONFIRM"))

        # Now hero_b acts, hero_a's snapshot should be cleared and new one for hero_b
        if result.input_request and result.input_request.player_id == "hero_b":
            # Snapshot is now for hero_b
            assert session._rollback_snapshot is not None

    def test_can_rollback_false_for_other_players(self):
        """Input requests targeting non-actor players don't have can_rollback."""
        state = _make_state()
        state.current_actor_id = "hero_a"
        session = GameSession(state)
        session._rollback_snapshot = state.model_dump(mode="json")

        # Push a step that targets hero_b
        step = AskConfirmationStep(player_id="hero_b", prompt="Block?")
        push_steps(state, [step])
        result = session.advance()
        assert result.input_request is not None
        assert result.input_request.player_id == "hero_b"
        assert result.input_request.can_rollback is False


# ---- Abort then rollback ----


class TestAbortThenRollback:
    def test_abort_clears_to_confirm_step(self):
        """Mandatory step failure aborts to ConfirmResolutionStep, not FinalizeHeroTurnStep."""
        state = _make_state()
        state.current_actor_id = "hero_a"

        # Use a mandatory select with filters that find no valid targets
        # TeamFilter(relation="ENEMY") requires enemies in range, but with
        # RangeFilter we can ensure none are found
        mandatory_select = SelectStep(
            target_type=TargetType.UNIT,
            prompt="Pick enemy",
            is_mandatory=True,
            filters=[
                TeamFilter(relation="ENEMY"),
                # hero_b is at distance 2 but range 0 means nothing in range
                {"type": "range_filter", "max_range": 0},
            ],
        )
        push_steps(state, [
            mandatory_select,
            ConfirmResolutionStep(hero_id="hero_a"),
            FinalizeHeroTurnStep(hero_id="hero_a"),
        ])

        # Process: mandatory select fails (no valid targets), aborts to ConfirmResolutionStep
        stack_result = process_stack(state)

        # Should land on ConfirmResolutionStep
        assert stack_result.input_request is not None
        assert len(state.execution_stack) >= 1
        # The top of stack should be ConfirmResolutionStep
        top_step = state.execution_stack[-1]
        assert isinstance(top_step, ConfirmResolutionStep)


# ---- can_rollback flag in full flow ----


class TestCanRollbackFlag:
    def test_can_rollback_on_action_choice(self):
        """can_rollback is True on the initial action choice for the current actor."""
        state = _make_state()
        session = GameSession(state)
        _setup_resolution(state)

        result = session.advance()
        assert result.input_request is not None
        assert result.input_request.can_rollback is True

    def test_can_rollback_on_confirm_step(self):
        """can_rollback is True on the confirm step."""
        state = _make_state()
        session = GameSession(state)
        _setup_resolution(state)

        # Action choice
        session.advance()
        # Choose HOLD
        result = session.advance(InputResponse(selection="HOLD"))
        # Confirm step
        assert result.input_request is not None
        assert result.input_request.can_rollback is True


# ---- Per-actor rollback isolation ----


class TestRollbackPerActorIsolation:
    def test_rollback_does_not_restore_previous_actors_snapshot(self):
        """Rollback for player B should restore to B's turn start, not A's."""
        state = _make_state()
        session = GameSession(state)
        _setup_resolution(state)

        # hero_a's action choice (highest initiative goes first)
        r1 = session.advance()
        assert r1.input_request.player_id == "hero_a"
        assert r1.input_request.can_rollback is True
        snapshot_a = session._rollback_snapshot

        # hero_a chooses HOLD
        session.advance(InputResponse(selection="HOLD"))

        # hero_a confirms
        r_confirm = session.advance(InputResponse(selection="CONFIRM"))

        # Now it's hero_b's turn
        assert r_confirm.input_request is not None
        assert r_confirm.input_request.player_id == "hero_b"
        assert r_confirm.input_request.can_rollback is True

        # Snapshot should have been replaced for hero_b
        assert session._rollback_actor_id == "hero_b"
        snapshot_b = session._rollback_snapshot
        assert snapshot_b is not snapshot_a

        # hero_b chooses HOLD
        session.advance(InputResponse(selection="HOLD"))

        # hero_b rolls back
        r_rollback = session.rollback()
        assert r_rollback.input_request is not None
        assert r_rollback.input_request.player_id == "hero_b"

        # The restored state should have hero_b as current actor, not hero_a
        assert session.state.current_actor_id == "hero_b"


# ---- StepType registration ----


class TestStepTypeRegistration:
    def test_confirm_resolution_step_type(self):
        """ConfirmResolutionStep has the correct StepType."""
        step = ConfirmResolutionStep(hero_id="hero_a")
        assert step.type == StepType.CONFIRM_RESOLUTION

    def test_serialization_roundtrip(self):
        """ConfirmResolutionStep can be serialized and deserialized."""
        step = ConfirmResolutionStep(hero_id="hero_a")
        data = step.model_dump(mode="json")
        assert data["type"] == "confirm_resolution"
        assert data["hero_id"] == "hero_a"

        restored = ConfirmResolutionStep.model_validate(data)
        assert restored.hero_id == "hero_a"
        assert restored.type == StepType.CONFIRM_RESOLUTION

"""Tests for origin_action_type tracking on effects."""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Card,
    CardTier,
    CardColor,
    ActionType,
)
from goa2.domain.hex import Hex
from goa2.domain.models.effect import (
    DurationType,
    EffectType,
    EffectScope,
    Shape,
)
from goa2.engine.steps import (
    CreateEffectStep,
    ReactionWindowStep,
    RestoreActionTypeStep,
)


@pytest.fixture
def game_state():
    """Basic game state for testing."""
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        turn=1,
        round=1,
    )
    state.current_actor_id = "hero_1"
    return state


class TestCreateEffectStepOriginActionType:
    """Tests for CreateEffectStep's origin_action_type handling."""

    def test_effect_uses_explicit_origin_action_type(self, game_state):
        """Effect uses explicitly set origin_action_type over context."""
        context = {"current_action_type": ActionType.ATTACK}

        step = CreateEffectStep(
            effect_type=EffectType.TARGET_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_TURN,
            origin_action_type=ActionType.SKILL,  # Explicit value
        )
        step.resolve(game_state, context)

        assert len(game_state.active_effects) == 1
        assert game_state.active_effects[0].origin_action_type == ActionType.SKILL

    def test_effect_uses_context_action_type_when_not_set(self, game_state):
        """Effect uses context action type when origin_action_type not set."""
        context = {"current_action_type": ActionType.ATTACK}

        step = CreateEffectStep(
            effect_type=EffectType.TARGET_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_TURN,
            # No origin_action_type set
        )
        step.resolve(game_state, context)

        assert len(game_state.active_effects) == 1
        assert game_state.active_effects[0].origin_action_type == ActionType.ATTACK

    def test_effect_has_none_when_no_context(self, game_state):
        """Effect has None origin_action_type when context has no action type."""
        context = {}  # No current_action_type

        step = CreateEffectStep(
            effect_type=EffectType.TARGET_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_TURN,
        )
        step.resolve(game_state, context)

        assert len(game_state.active_effects) == 1
        assert game_state.active_effects[0].origin_action_type is None

    def test_skill_action_sets_skill_origin(self, game_state):
        """Effects from SKILL actions have SKILL origin_action_type."""
        context = {"current_action_type": ActionType.SKILL}

        step = CreateEffectStep(
            effect_type=EffectType.MOVEMENT_ZONE,
            scope=EffectScope(shape=Shape.RADIUS, range=3, origin_id="hero_1"),
            duration=DurationType.THIS_TURN,
        )
        step.resolve(game_state, context)

        assert game_state.active_effects[0].origin_action_type == ActionType.SKILL

    def test_defense_action_sets_defense_origin(self, game_state):
        """Effects from DEFENSE actions have DEFENSE origin_action_type."""
        context = {"current_action_type": ActionType.DEFENSE}

        step = CreateEffectStep(
            effect_type=EffectType.TARGET_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_TURN,
        )
        step.resolve(game_state, context)

        assert game_state.active_effects[0].origin_action_type == ActionType.DEFENSE


class TestReactionWindowSetsDefenseType:
    """Tests for ReactionWindowStep setting DEFENSE action type."""

    @pytest.fixture
    def state_with_defender(self, game_state):
        """Game state with a defending hero."""
        hero = Hero(
            id="defender",
            name="Defender",
            team=TeamColor.BLUE,
            deck=[
                Card(
                    id="defense_card",
                    name="Defense Card",
                    tier=CardTier.I,
                    color=CardColor.RED,
                    initiative=2,
                    primary_action=ActionType.DEFENSE,
                    primary_action_value=3,
                    effect_id="defense_effect",
                    effect_text="Defense text",
                    is_facedown=False,
                ),
            ],
        )
        hero.hand = hero.deck.copy()
        hero.deck = []
        game_state.teams[TeamColor.BLUE].heroes.append(hero)
        game_state.entity_locations["defender"] = Hex(q=1, r=0, s=-1)
        return game_state

    def test_defense_card_played_sets_defense_type(self, state_with_defender):
        """Playing a defense card sets current_action_type to DEFENSE."""
        context = {
            "victim_id": "defender",
            "current_action_type": ActionType.ATTACK,  # Was an attack
        }

        step = ReactionWindowStep(target_player_key="victim_id")
        step.pending_input = {"selection": "defense_card"}
        step.resolve(state_with_defender, context)

        assert context.get("current_action_type") == ActionType.DEFENSE

    def test_defense_card_saves_previous_type_to_stack(self, state_with_defender):
        """Playing a defense card saves previous action type to stack."""
        context = {
            "victim_id": "defender",
            "current_action_type": ActionType.ATTACK,
        }

        step = ReactionWindowStep(target_player_key="victim_id")
        step.pending_input = {"selection": "defense_card"}
        step.resolve(state_with_defender, context)

        assert "action_type_stack" in context
        assert ActionType.ATTACK in context["action_type_stack"]

    def test_pass_does_not_change_action_type(self, state_with_defender):
        """Passing on defense does not change current_action_type."""
        context = {
            "victim_id": "defender",
            "current_action_type": ActionType.ATTACK,
        }

        step = ReactionWindowStep(target_player_key="victim_id")
        step.pending_input = {"selection": "PASS"}
        step.resolve(state_with_defender, context)

        assert context.get("current_action_type") == ActionType.ATTACK
        assert (
            "action_type_stack" not in context
            or len(context.get("action_type_stack", [])) == 0
        )


class TestRestoreActionTypeStep:
    """Tests for RestoreActionTypeStep."""

    def test_restores_previous_action_type(self, game_state):
        """Restores previous action type from stack."""
        context = {
            "current_action_type": ActionType.DEFENSE,
            "action_type_stack": [ActionType.ATTACK],
        }

        step = RestoreActionTypeStep()
        step.resolve(game_state, context)

        assert context.get("current_action_type") == ActionType.ATTACK
        assert len(context["action_type_stack"]) == 0

    def test_handles_empty_stack(self, game_state):
        """Handles empty stack gracefully."""
        context = {
            "current_action_type": ActionType.DEFENSE,
            "action_type_stack": [],
        }

        step = RestoreActionTypeStep()
        step.resolve(game_state, context)

        # Should not change, stack was empty
        assert context.get("current_action_type") == ActionType.DEFENSE

    def test_handles_missing_stack(self, game_state):
        """Handles missing stack gracefully."""
        context = {"current_action_type": ActionType.DEFENSE}

        step = RestoreActionTypeStep()
        step.resolve(game_state, context)

        # Should not change, no stack
        assert context.get("current_action_type") == ActionType.DEFENSE

    def test_nested_restores(self, game_state):
        """Correctly restores nested action types."""
        context = {
            "current_action_type": ActionType.DEFENSE,
            "action_type_stack": [ActionType.ATTACK, ActionType.SKILL],
        }

        step = RestoreActionTypeStep()

        # First restore - should get SKILL (last pushed)
        step.resolve(game_state, context)
        assert context.get("current_action_type") == ActionType.SKILL
        assert len(context["action_type_stack"]) == 1

        # Second restore - should get ATTACK
        step.resolve(game_state, context)
        assert context.get("current_action_type") == ActionType.ATTACK
        assert len(context["action_type_stack"]) == 0

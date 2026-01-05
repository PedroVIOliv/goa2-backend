"""Tests for effect/modifier expiration during phase transitions."""
import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, Hero, Card, CardTier, CardColor, ActionType, GamePhase
from goa2.domain.hex import Hex
from goa2.domain.models.modifier import Modifier, DurationType
from goa2.domain.models.effect import (
    ActiveEffect, EffectType, EffectScope, Shape
)
from goa2.engine.phases import end_turn
from goa2.engine.effect_manager import EffectManager


@pytest.fixture
def game_state():
    """Basic game state for testing phase transitions."""
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[])
        },
        turn=1,
        round=1
    )
    return state


class TestExpireEffectsFunction:
    """Tests for the expire_effects function in EffectManager."""

    def test_expire_effects_removes_matching_duration(self, game_state):
        """expire_effects removes effects with matching duration type."""
        game_state.active_effects.append(ActiveEffect(
            id="eff_1", source_id="hero_1",
            effect_type=EffectType.PLACEMENT_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_TURN,
            created_at_turn=1, created_at_round=1
        ))
        game_state.active_effects.append(ActiveEffect(
            id="eff_2", source_id="hero_1",
            effect_type=EffectType.MOVEMENT_ZONE,
            scope=EffectScope(shape=Shape.ADJACENT),
            duration=DurationType.THIS_ROUND,
            created_at_turn=1, created_at_round=1
        ))

        EffectManager.expire_effects(game_state, DurationType.THIS_TURN)

        assert len(game_state.active_effects) == 1
        assert game_state.active_effects[0].id == "eff_2"

    def test_expire_effects_preserves_non_matching(self, game_state):
        """expire_effects keeps effects with different duration types."""
        game_state.active_effects.append(ActiveEffect(
            id="eff_1", source_id="hero_1",
            effect_type=EffectType.AREA_STAT_MODIFIER,
            scope=EffectScope(shape=Shape.RADIUS, range=2),
            duration=DurationType.PASSIVE,
            created_at_turn=1, created_at_round=1
        ))
        game_state.active_effects.append(ActiveEffect(
            id="eff_2", source_id="hero_1",
            effect_type=EffectType.TARGET_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_ROUND,
            created_at_turn=1, created_at_round=1
        ))

        EffectManager.expire_effects(game_state, DurationType.THIS_TURN)

        assert len(game_state.active_effects) == 2


class TestEndTurnExpiration:
    """Tests for end_turn() expiring THIS_TURN effects and modifiers."""

    def test_end_turn_expires_this_turn_modifiers(self, game_state):
        """end_turn() expires THIS_TURN modifiers."""
        game_state.active_modifiers.append(Modifier(
            id="mod_1", source_id="hero_1", target_id="hero_2",
            status_tag="PREVENT_MOVEMENT", duration=DurationType.THIS_TURN,
            created_at_turn=1, created_at_round=1
        ))
        game_state.active_modifiers.append(Modifier(
            id="mod_2", source_id="hero_1", target_id="hero_3",
            status_tag="PREVENT_ATTACK", duration=DurationType.THIS_ROUND,
            created_at_turn=1, created_at_round=1
        ))

        end_turn(game_state)

        assert len(game_state.active_modifiers) == 1
        assert game_state.active_modifiers[0].id == "mod_2"

    def test_end_turn_expires_this_turn_effects(self, game_state):
        """end_turn() expires THIS_TURN effects."""
        game_state.active_effects.append(ActiveEffect(
            id="eff_1", source_id="hero_1",
            effect_type=EffectType.PLACEMENT_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_TURN,
            created_at_turn=1, created_at_round=1
        ))
        game_state.active_effects.append(ActiveEffect(
            id="eff_2", source_id="hero_1",
            effect_type=EffectType.MOVEMENT_ZONE,
            scope=EffectScope(shape=Shape.ADJACENT),
            duration=DurationType.THIS_ROUND,
            created_at_turn=1, created_at_round=1
        ))

        end_turn(game_state)

        assert len(game_state.active_effects) == 1
        assert game_state.active_effects[0].id == "eff_2"

    def test_end_turn_preserves_passive_modifiers(self, game_state):
        """end_turn() does not expire PASSIVE modifiers."""
        game_state.active_modifiers.append(Modifier(
            id="mod_1", source_id="hero_1", target_id="hero_2",
            status_tag="ITEM_BONUS", duration=DurationType.PASSIVE,
            created_at_turn=1, created_at_round=1
        ))

        end_turn(game_state)

        assert len(game_state.active_modifiers) == 1

    def test_end_turn_preserves_passive_effects(self, game_state):
        """end_turn() does not expire PASSIVE effects."""
        game_state.active_effects.append(ActiveEffect(
            id="eff_1", source_id="hero_1",
            effect_type=EffectType.AREA_STAT_MODIFIER,
            scope=EffectScope(shape=Shape.ADJACENT),
            duration=DurationType.PASSIVE,
            created_at_turn=1, created_at_round=1
        ))

        end_turn(game_state)

        assert len(game_state.active_effects) == 1


class TestEndPhaseCleanupStepExpiration:
    """Tests for EndPhaseCleanupStep expiring THIS_ROUND effects and modifiers."""

    def test_cleanup_step_expires_this_round_modifiers(self, game_state):
        """EndPhaseCleanupStep expires THIS_ROUND modifiers."""
        from goa2.engine.steps import EndPhaseCleanupStep
        from goa2.engine.handler import push_steps, process_resolution_stack

        game_state.active_modifiers.append(Modifier(
            id="mod_1", source_id="hero_1", target_id="hero_2",
            status_tag="PREVENT_MOVEMENT", duration=DurationType.THIS_ROUND,
            created_at_turn=1, created_at_round=1
        ))
        game_state.active_modifiers.append(Modifier(
            id="mod_2", source_id="hero_1", target_id="hero_3",
            status_tag="ITEM_BONUS", duration=DurationType.PASSIVE,
            created_at_turn=1, created_at_round=1
        ))

        push_steps(game_state, [EndPhaseCleanupStep()])
        process_resolution_stack(game_state)

        assert len(game_state.active_modifiers) == 1
        assert game_state.active_modifiers[0].id == "mod_2"

    def test_cleanup_step_expires_this_round_effects(self, game_state):
        """EndPhaseCleanupStep expires THIS_ROUND effects."""
        from goa2.engine.steps import EndPhaseCleanupStep
        from goa2.engine.handler import push_steps, process_resolution_stack

        game_state.active_effects.append(ActiveEffect(
            id="eff_1", source_id="hero_1",
            effect_type=EffectType.PLACEMENT_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_ROUND,
            created_at_turn=1, created_at_round=1
        ))
        game_state.active_effects.append(ActiveEffect(
            id="eff_2", source_id="hero_1",
            effect_type=EffectType.AREA_STAT_MODIFIER,
            scope=EffectScope(shape=Shape.ADJACENT),
            duration=DurationType.PASSIVE,
            created_at_turn=1, created_at_round=1
        ))

        push_steps(game_state, [EndPhaseCleanupStep()])
        process_resolution_stack(game_state)

        assert len(game_state.active_effects) == 1
        assert game_state.active_effects[0].id == "eff_2"

    def test_cleanup_step_preserves_passive_effects(self, game_state):
        """EndPhaseCleanupStep preserves PASSIVE effects."""
        from goa2.engine.steps import EndPhaseCleanupStep
        from goa2.engine.handler import push_steps, process_resolution_stack

        game_state.active_effects.append(ActiveEffect(
            id="eff_1", source_id="hero_1",
            effect_type=EffectType.AREA_STAT_MODIFIER,
            scope=EffectScope(shape=Shape.ADJACENT),
            duration=DurationType.PASSIVE,
            created_at_turn=1, created_at_round=1
        ))

        push_steps(game_state, [EndPhaseCleanupStep()])
        process_resolution_stack(game_state)

        assert len(game_state.active_effects) == 1

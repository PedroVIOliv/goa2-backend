"""Tests for CancelEffectsStep."""

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
    AffectsFilter,
    ActiveEffect,
)
from goa2.engine.steps import CancelEffectsStep


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


@pytest.fixture
def state_with_heroes(game_state):
    """Game state with red and blue heroes on board."""
    red_hero = Hero(id="red_hero", name="Red Hero", team=TeamColor.RED, deck=[])
    blue_hero = Hero(id="blue_hero", name="Blue Hero", team=TeamColor.BLUE, deck=[])
    game_state.teams[TeamColor.RED].heroes.append(red_hero)
    game_state.teams[TeamColor.BLUE].heroes.append(blue_hero)

    game_state.entity_locations["red_hero"] = Hex(q=0, r=0, s=0)
    game_state.entity_locations["blue_hero"] = Hex(q=2, r=0, s=-2)

    return game_state


class TestCancelEffectsStep:
    """Tests for CancelEffectsStep."""

    def test_cancel_by_effect_type(self, game_state):
        """Cancels effects matching specified effect type."""
        game_state.active_effects = [
            ActiveEffect(
                id="eff_1",
                source_id="hero_1",
                effect_type=EffectType.PLACEMENT_PREVENTION,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
            ),
            ActiveEffect(
                id="eff_2",
                source_id="hero_1",
                effect_type=EffectType.MOVEMENT_ZONE,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
            ),
            ActiveEffect(
                id="eff_3",
                source_id="hero_2",
                effect_type=EffectType.PLACEMENT_PREVENTION,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
            ),
        ]

        step = CancelEffectsStep(effect_types=[EffectType.PLACEMENT_PREVENTION])
        result = step.resolve(game_state, {})

        assert result.is_finished
        assert len(game_state.active_effects) == 1
        assert game_state.active_effects[0].id == "eff_2"

    def test_cancel_by_origin_action_type(self, game_state):
        """Cancels effects based on their origin action type (skill vs attack)."""
        game_state.active_effects = [
            ActiveEffect(
                id="eff_skill_1",
                source_id="hero_1",
                effect_type=EffectType.TARGET_PREVENTION,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
                origin_action_type=ActionType.SKILL,
            ),
            ActiveEffect(
                id="eff_attack_1",
                source_id="hero_1",
                effect_type=EffectType.TARGET_PREVENTION,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
                origin_action_type=ActionType.ATTACK,
            ),
            ActiveEffect(
                id="eff_none",
                source_id="hero_1",
                effect_type=EffectType.TARGET_PREVENTION,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
                origin_action_type=None,
            ),
        ]

        step = CancelEffectsStep(origin_action_types=[ActionType.SKILL])
        result = step.resolve(game_state, {})

        assert result.is_finished
        assert len(game_state.active_effects) == 2
        effect_ids = [e.id for e in game_state.active_effects]
        assert "eff_attack_1" in effect_ids
        assert "eff_none" in effect_ids
        assert "eff_skill_1" not in effect_ids

    def test_cancel_by_source_team(self, state_with_heroes):
        """Cancels effects from a specific team."""
        state_with_heroes.active_effects = [
            ActiveEffect(
                id="eff_red",
                source_id="red_hero",
                effect_type=EffectType.MOVEMENT_ZONE,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
            ),
            ActiveEffect(
                id="eff_blue",
                source_id="blue_hero",
                effect_type=EffectType.MOVEMENT_ZONE,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
            ),
        ]

        step = CancelEffectsStep(source_team=TeamColor.BLUE)
        result = step.resolve(state_with_heroes, {})

        assert result.is_finished
        assert len(state_with_heroes.active_effects) == 1
        assert state_with_heroes.active_effects[0].id == "eff_red"

    def test_cancel_by_source_ids(self, game_state):
        """Cancels effects from specific source IDs."""
        game_state.active_effects = [
            ActiveEffect(
                id="eff_1",
                source_id="hero_1",
                effect_type=EffectType.MOVEMENT_ZONE,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
            ),
            ActiveEffect(
                id="eff_2",
                source_id="hero_2",
                effect_type=EffectType.MOVEMENT_ZONE,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
            ),
            ActiveEffect(
                id="eff_3",
                source_id="hero_3",
                effect_type=EffectType.MOVEMENT_ZONE,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
            ),
        ]

        step = CancelEffectsStep(source_ids=["hero_1", "hero_3"])
        result = step.resolve(game_state, {})

        assert result.is_finished
        assert len(game_state.active_effects) == 1
        assert game_state.active_effects[0].id == "eff_2"

    def test_cancel_by_scope_radius(self, state_with_heroes):
        """Cancels effects within a specified radius."""
        state_with_heroes.entity_locations["turret"] = Hex(q=0, r=0, s=0)
        state_with_heroes.active_effects = [
            ActiveEffect(
                id="eff_near",
                source_id="turret",
                effect_type=EffectType.TARGET_PREVENTION,
                scope=EffectScope(shape=Shape.POINT),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
            ),
            ActiveEffect(
                id="eff_far",
                source_id="far_thing",
                effect_type=EffectType.TARGET_PREVENTION,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
            ),
        ]

        step = CancelEffectsStep(
            scope=EffectScope(shape=Shape.RADIUS, range=3, origin_id="turret")
        )
        result = step.resolve(state_with_heroes, {})

        assert result.is_finished
        assert len(state_with_heroes.active_effects) == 1
        assert state_with_heroes.active_effects[0].id == "eff_far"

    def test_cancel_combined_filters(self, state_with_heroes):
        """Cancels effects matching multiple criteria (AND logic)."""
        state_with_heroes.entity_locations["turret"] = Hex(q=0, r=0, s=0)
        state_with_heroes.active_effects = [
            ActiveEffect(
                id="eff_target_1",
                source_id="blue_hero",
                effect_type=EffectType.TARGET_PREVENTION,
                scope=EffectScope(shape=Shape.POINT),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
                origin_action_type=ActionType.SKILL,
            ),
            ActiveEffect(
                id="eff_target_2",
                source_id="blue_hero",
                effect_type=EffectType.TARGET_PREVENTION,
                scope=EffectScope(shape=Shape.POINT),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
                origin_action_type=ActionType.ATTACK,
            ),
            ActiveEffect(
                id="eff_target_3",
                source_id="red_hero",
                effect_type=EffectType.TARGET_PREVENTION,
                scope=EffectScope(shape=Shape.POINT),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
                origin_action_type=ActionType.SKILL,
            ),
        ]

        step = CancelEffectsStep(
            effect_types=[EffectType.TARGET_PREVENTION],
            origin_action_types=[ActionType.SKILL],
            source_team=TeamColor.BLUE,
        )
        result = step.resolve(state_with_heroes, {})

        assert result.is_finished
        assert len(state_with_heroes.active_effects) == 2
        effect_ids = [e.id for e in state_with_heroes.active_effects]
        assert "eff_target_1" not in effect_ids
        assert "eff_target_2" in effect_ids
        assert "eff_target_3" in effect_ids

    def test_cancel_no_matching_effects(self, game_state):
        """Does nothing when no effects match criteria."""
        game_state.active_effects = [
            ActiveEffect(
                id="eff_1",
                source_id="hero_1",
                effect_type=EffectType.MOVEMENT_ZONE,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
            ),
        ]

        step = CancelEffectsStep(effect_types=[EffectType.TARGET_PREVENTION])
        result = step.resolve(game_state, {})

        assert result.is_finished
        assert len(game_state.active_effects) == 1
        assert game_state.active_effects[0].id == "eff_1"

    def test_cancel_empty_effects_list(self, game_state):
        """Handles empty active effects list gracefully."""
        step = CancelEffectsStep(effect_types=[EffectType.TARGET_PREVENTION])
        result = step.resolve(game_state, {})

        assert result.is_finished
        assert len(game_state.active_effects) == 0

    def test_cancel_with_skip_condition(self, game_state):
        """Skips when active_if_key condition is not met."""
        game_state.active_effects = [
            ActiveEffect(
                id="eff_1",
                source_id="hero_1",
                effect_type=EffectType.MOVEMENT_ZONE,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
            ),
        ]

        step = CancelEffectsStep(
            effect_types=[EffectType.MOVEMENT_ZONE],
            active_if_key="should_cancel",
        )
        result = step.resolve(game_state, {})

        assert result.is_finished
        assert len(game_state.active_effects) == 1  # Not cancelled

    def test_cancel_with_active_if_key_met(self, game_state):
        """Cancels when active_if_key condition is met."""
        game_state.active_effects = [
            ActiveEffect(
                id="eff_1",
                source_id="hero_1",
                effect_type=EffectType.MOVEMENT_ZONE,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
            ),
        ]

        step = CancelEffectsStep(
            effect_types=[EffectType.MOVEMENT_ZONE],
            active_if_key="should_cancel",
        )
        result = step.resolve(game_state, {"should_cancel": True})

        assert result.is_finished
        assert len(game_state.active_effects) == 0


class TestCancelEffectsStepDisruptorPulse:
    """Tests simulating Disruptor Pulse card behavior."""

    def test_cancel_skill_effects_in_radius(self, state_with_heroes):
        """
        Simulates: Disruptor Pulse - Cancel skills with active effects
        of enemies in radius of the Turret.
        """
        state_with_heroes.entity_locations["turret"] = Hex(q=0, r=0, s=0)
        state_with_heroes.active_effects = [
            ActiveEffect(
                id="eff_enemy_skill_1",
                source_id="blue_hero",
                effect_type=EffectType.TARGET_PREVENTION,
                scope=EffectScope(shape=Shape.RADIUS, range=5, origin_id="blue_hero"),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
                origin_action_type=ActionType.SKILL,
            ),
            ActiveEffect(
                id="eff_enemy_skill_2",
                source_id="blue_hero",
                effect_type=EffectType.MOVEMENT_ZONE,
                scope=EffectScope(shape=Shape.ADJACENT, origin_id="blue_hero"),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
                origin_action_type=ActionType.SKILL,
            ),
            ActiveEffect(
                id="eff_enemy_attack",
                source_id="blue_hero",
                effect_type=EffectType.TARGET_PREVENTION,
                scope=EffectScope(shape=Shape.RADIUS, range=5, origin_id="blue_hero"),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
                origin_action_type=ActionType.ATTACK,
            ),
            ActiveEffect(
                id="eff_friendly_skill",
                source_id="red_hero",
                effect_type=EffectType.TARGET_PREVENTION,
                scope=EffectScope(shape=Shape.RADIUS, range=5, origin_id="red_hero"),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
                origin_action_type=ActionType.SKILL,
            ),
        ]

        step = CancelEffectsStep(
            effect_types=[EffectType.TARGET_PREVENTION, EffectType.MOVEMENT_ZONE],
            origin_action_types=[ActionType.SKILL],
            source_team=TeamColor.BLUE,
            scope=EffectScope(shape=Shape.RADIUS, range=3, origin_id="turret"),
        )
        result = step.resolve(state_with_heroes, {})

        assert result.is_finished
        assert len(state_with_heroes.active_effects) == 2
        remaining_ids = [e.id for e in state_with_heroes.active_effects]
        assert "eff_enemy_attack" in remaining_ids
        assert "eff_friendly_skill" in remaining_ids

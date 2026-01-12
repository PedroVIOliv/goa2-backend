"""Tests for EffectManager."""

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
from goa2.domain.models.effect import DurationType
from goa2.domain.models.enums import StatType
from goa2.domain.models.effect import (
    ActiveEffect,
    EffectType,
    EffectScope,
    Shape,
    AffectsFilter,
)
from goa2.engine.effect_manager import EffectManager


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


class TestEffectManagerCreateEffect:
    """Tests for EffectManager.create_effect()."""

    def test_create_effect_basic(self, game_state):
        """Creates an effect and adds it to state."""
        effect = EffectManager.create_effect(
            state=game_state,
            source_id="hero_1",
            effect_type=EffectType.PLACEMENT_PREVENTION,
            scope=EffectScope(shape=Shape.RADIUS, range=3),
            duration=DurationType.THIS_TURN,
        )

        assert effect in game_state.active_effects
        assert effect.source_id == "hero_1"
        assert effect.effect_type == EffectType.PLACEMENT_PREVENTION
        assert effect.scope.shape == Shape.RADIUS
        assert effect.created_at_turn == 1
        assert effect.created_at_round == 1

    def test_create_effect_with_card_id(self, game_state):
        """Creates an effect linked to a card."""
        effect = EffectManager.create_effect(
            state=game_state,
            source_id="hero_1",
            effect_type=EffectType.MOVEMENT_ZONE,
            scope=EffectScope(shape=Shape.ADJACENT, affects=AffectsFilter.ENEMY_UNITS),
            duration=DurationType.THIS_TURN,
            source_card_id="card_456",
            max_value=1,
        )

        assert effect.source_card_id == "card_456"
        assert effect.max_value == 1


class TestEffectManagerExpire:
    """Tests for EffectManager expiration methods."""

    def test_expire_effects_by_duration(self, game_state):
        """Expires all effects matching duration type."""
        game_state.active_effects.append(
            ActiveEffect(
                id="eff_1",
                source_id="h1",
                effect_type=EffectType.PLACEMENT_PREVENTION,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_TURN,
                created_at_turn=1,
                created_at_round=1,
            )
        )
        game_state.active_effects.append(
            ActiveEffect(
                id="eff_2",
                source_id="h1",
                effect_type=EffectType.MOVEMENT_ZONE,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_ROUND,
                created_at_turn=1,
                created_at_round=1,
            )
        )

        EffectManager.expire_effects(game_state, DurationType.THIS_TURN)

        assert len(game_state.active_effects) == 1
        assert game_state.active_effects[0].id == "eff_2"

    def test_expire_by_card(self, game_state):
        """Expires all effects linked to a specific card."""
        game_state.active_effects.append(
            ActiveEffect(
                id="eff_1",
                source_id="h1",
                source_card_id="card_1",
                effect_type=EffectType.PLACEMENT_PREVENTION,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_ROUND,
                created_at_turn=1,
                created_at_round=1,
            )
        )
        game_state.active_effects.append(
            ActiveEffect(
                id="eff_2",
                source_id="h1",
                source_card_id="card_2",
                effect_type=EffectType.MOVEMENT_ZONE,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_ROUND,
                created_at_turn=1,
                created_at_round=1,
            )
        )

        EffectManager.expire_by_card(game_state, "card_1")

        assert len(game_state.active_effects) == 1
        assert game_state.active_effects[0].id == "eff_2"

    def test_expire_by_source(self, game_state):
        """Expires all effects from a specific source (e.g., defeated hero)."""
        game_state.active_effects.append(
            ActiveEffect(
                id="eff_1",
                source_id="hero_1",
                effect_type=EffectType.AREA_STAT_MODIFIER,
                scope=EffectScope(shape=Shape.ADJACENT),
                duration=DurationType.PASSIVE,
                created_at_turn=1,
                created_at_round=1,
            )
        )
        game_state.active_effects.append(
            ActiveEffect(
                id="eff_2",
                source_id="hero_2",
                effect_type=EffectType.AREA_STAT_MODIFIER,
                scope=EffectScope(shape=Shape.ADJACENT),
                duration=DurationType.PASSIVE,
                created_at_turn=1,
                created_at_round=1,
            )
        )

        EffectManager.expire_by_source(game_state, "hero_1")

        assert len(game_state.active_effects) == 1
        assert game_state.active_effects[0].source_id == "hero_2"


class TestEffectManagerCleanupStale:
    """Tests for cleaning up stale effects (card not in played state)."""

    def test_cleanup_stale_effects(self, game_state):
        """Removes effects whose source card is no longer in played state."""
        # Create a hero with a card
        hero = Hero(id="hero_1", name="Test Hero", team=TeamColor.RED, deck=[])
        card = Card(
            id="card_1",
            name="Test Card",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=5,
            primary_action=ActionType.ATTACK,
            primary_action_value=2,
            effect_id="test",
            effect_text="test",
        )
        hero.hand.append(card)
        game_state.teams[TeamColor.RED].heroes.append(hero)

        # Add effect linked to card (card not played yet)
        game_state.active_effects.append(
            ActiveEffect(
                id="eff_1",
                source_id="hero_1",
                source_card_id="card_1",
                effect_type=EffectType.PLACEMENT_PREVENTION,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_ROUND,
                created_at_turn=1,
                created_at_round=1,
            )
        )
        # Add effect with no card link (should remain)
        game_state.active_effects.append(
            ActiveEffect(
                id="eff_2",
                source_id="hero_1",
                source_card_id=None,
                effect_type=EffectType.AREA_STAT_MODIFIER,
                scope=EffectScope(shape=Shape.ADJACENT),
                duration=DurationType.PASSIVE,
                created_at_turn=1,
                created_at_round=1,
            )
        )

        EffectManager.cleanup_stale_effects(game_state)

        # eff_1 should be removed (card not played)
        # eff_2 should remain (no card link)
        assert len(game_state.active_effects) == 1
        assert game_state.active_effects[0].id == "eff_2"

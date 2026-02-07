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


class TestCardActiveTracking:
    """Tests for card.is_active tracking when effects are created and expired."""

    def test_create_effect_sets_card_is_active(self, game_state):
        """Effect creation sets card.is_active to True."""
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

        assert card.is_active is False

        # Create effect linked to card
        EffectManager.create_effect(
            state=game_state,
            source_id="hero_1",
            effect_type=EffectType.MOVEMENT_ZONE,
            scope=EffectScope(shape=Shape.ADJACENT),
            duration=DurationType.THIS_TURN,
            source_card_id="card_1",
        )

        assert card.is_active is True

    def test_expire_by_card_sets_card_is_active_false(self, game_state):
        """Expiring effects by card sets card.is_active to False."""
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

        # Create effect
        EffectManager.create_effect(
            state=game_state,
            source_id="hero_1",
            effect_type=EffectType.MOVEMENT_ZONE,
            scope=EffectScope(shape=Shape.ADJACENT),
            duration=DurationType.THIS_TURN,
            source_card_id="card_1",
        )
        assert card.is_active is True

        # Expire effects from card
        EffectManager.expire_by_card(game_state, "card_1")
        assert card.is_active is False

    def test_expire_effects_sets_card_is_active_false(self, game_state):
        """Expiring effects by duration sets card.is_active to False."""
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

        # Create THIS_TURN effect
        EffectManager.create_effect(
            state=game_state,
            source_id="hero_1",
            effect_type=EffectType.MOVEMENT_ZONE,
            scope=EffectScope(shape=Shape.ADJACENT),
            duration=DurationType.THIS_TURN,
            source_card_id="card_1",
        )
        assert card.is_active is True

        # Expire THIS_TURN effects
        EffectManager.expire_effects(game_state, DurationType.THIS_TURN)
        assert card.is_active is False

    def test_expire_by_source_sets_card_is_active_false(self, game_state):
        """Expiring effects by source (hero defeat) sets card.is_active to False."""
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

        # Create effect
        EffectManager.create_effect(
            state=game_state,
            source_id="hero_1",
            effect_type=EffectType.MOVEMENT_ZONE,
            scope=EffectScope(shape=Shape.ADJACENT),
            duration=DurationType.THIS_TURN,
            source_card_id="card_1",
        )
        assert card.is_active is True

        # Expire effects from hero
        EffectManager.expire_by_source(game_state, "hero_1")
        assert card.is_active is False

    def test_multiple_effects_card_remains_active_until_all_expired(self, game_state):
        """Card remains active if it has multiple effects and only one expires."""
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

        # Create two effects with different durations
        EffectManager.create_effect(
            state=game_state,
            source_id="hero_1",
            effect_type=EffectType.MOVEMENT_ZONE,
            scope=EffectScope(shape=Shape.ADJACENT),
            duration=DurationType.THIS_TURN,
            source_card_id="card_1",
        )
        EffectManager.create_effect(
            state=game_state,
            source_id="hero_1",
            effect_type=EffectType.TARGET_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_ROUND,
            source_card_id="card_1",
        )
        assert card.is_active is True

        # Expire only THIS_TURN effects
        EffectManager.expire_effects(game_state, DurationType.THIS_TURN)
        assert card.is_active is True  # Still has THIS_ROUND effect

        # Expire THIS_ROUND effects
        EffectManager.expire_effects(game_state, DurationType.THIS_ROUND)
        assert card.is_active is False  # Now no effects

    def test_get_card_by_id(self, game_state):
        """GameState.get_card_by_id() finds cards across all hero locations."""
        hero = Hero(id="hero_1", name="Test Hero", team=TeamColor.RED, deck=[])
        card1 = Card(
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
        card2 = Card(
            id="card_2",
            name="Test Card 2",
            tier=CardTier.I,
            color=CardColor.BLUE,
            initiative=3,
            primary_action=ActionType.MOVEMENT,
            primary_action_value=1,
            effect_id="test2",
            effect_text="test2",
        )
        hero.hand.append(card1)
        hero.played_cards.append(card2)
        hero.current_turn_card = None
        game_state.teams[TeamColor.RED].heroes.append(hero)

        assert game_state.get_card_by_id("card_1") is card1
        assert game_state.get_card_by_id("card_2") is card2
        assert game_state.get_card_by_id("card_999") is None

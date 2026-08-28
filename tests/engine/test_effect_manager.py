"""Tests for EffectManager."""

import pytest

from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardTier,
    Hero,
    Team,
    TeamColor,
)
from goa2.domain.models.effect import (
    ActiveEffect,
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.state import GameState
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


class TestOneInstancePerCard:
    """Only one instance of an active effect per card can be active.

    Repeating an active effect must not duplicate it (game rule). Identity is
    (source_card_id, effect_type, scope): a card whose text needs several
    distinct payloads still gets one row per payload, but performing that card
    again creates nothing new.
    """

    def _create(self, state, **overrides):
        params = dict(
            state=state,
            source_id="hero_1",
            effect_type=EffectType.AREA_STAT_MODIFIER,
            scope=EffectScope(shape=Shape.RADIUS, range=2, affects=AffectsFilter.ENEMY_HEROES),
            duration=DurationType.THIS_TURN,
            source_card_id="card_1",
        )
        params.update(overrides)
        return EffectManager.create_effect(**params)

    def test_repeating_a_card_effect_reuses_the_existing_instance(self, game_state):
        first = self._create(game_state)
        second = self._create(game_state)

        assert second is first
        assert len(game_state.active_effects) == 1

    def test_same_card_with_a_different_payload_creates_a_second_instance(self, game_state):
        self._create(game_state, effect_type=EffectType.AREA_STAT_MODIFIER)
        self._create(game_state, effect_type=EffectType.REPEAT_PREVENTION)

        assert len(game_state.active_effects) == 2

    def test_same_card_and_type_with_a_different_scope_creates_a_second_instance(self, game_state):
        self._create(game_state, scope=EffectScope(shape=Shape.POINT, affects=AffectsFilter.SELF))
        self._create(
            game_state,
            scope=EffectScope(shape=Shape.POINT, affects=AffectsFilter.FRIENDLY_UNITS),
        )

        assert len(game_state.active_effects) == 2

    def test_a_different_source_does_not_share_an_instance(self, game_state):
        """A copied card protects the copier, not just the original caster."""
        self._create(game_state, source_id="hero_1")
        self._create(game_state, source_id="hero_2")

        assert len(game_state.active_effects) == 2

    def test_different_cards_do_not_share_an_instance(self, game_state):
        self._create(game_state, source_card_id="card_1")
        self._create(game_state, source_card_id="card_2")

        assert len(game_state.active_effects) == 2

    def test_effects_without_a_card_never_dedup(self, game_state):
        self._create(game_state, source_card_id=None)
        self._create(game_state, source_card_id=None)

        assert len(game_state.active_effects) == 2

    def test_a_repeat_does_not_refresh_a_spent_effect(self, game_state):
        first = self._create(
            game_state,
            effect_type=EffectType.MINION_DEFEAT_BOUNTY,
            max_value=2,
        )
        first.max_value = 1
        game_state.turn = 5

        self._create(game_state, effect_type=EffectType.MINION_DEFEAT_BOUNTY, max_value=2)

        assert len(game_state.active_effects) == 1
        assert first.max_value == 1
        assert first.created_at_turn == 1

    def test_a_repeat_does_not_reactivate_a_deactivated_card(self, game_state):
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
        hero.played_cards.append(card)
        game_state.teams[TeamColor.RED].heroes.append(hero)

        effect = self._create(game_state)
        EffectManager.deactivate_effects_by_card(game_state, "card_1")
        card.is_active = False

        self._create(game_state)

        assert len(game_state.active_effects) == 1
        assert effect.is_active is False
        assert card.is_active is False


class TestEffectOwnership:
    """Defeat cancels the active effects on the defeated hero's own cards.

    Rulebook: "An Active effect on your card is cancelled … if you are
    defeated." A card can be performed by someone else (NebKher's Mind Grip
    performs a card in an enemy's turn slot) and the effect still sits on the
    owner's card, so it ends with the owner — not with the performer.
    """

    def _state_with_performed_card(self, game_state):
        owner = Hero(id="hero_owner", name="Owner", team=TeamColor.BLUE, deck=[])
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
        owner.played_cards.append(card)
        performer = Hero(id="hero_performer", name="Performer", team=TeamColor.RED, deck=[])
        game_state.teams[TeamColor.BLUE].heroes.append(owner)
        game_state.teams[TeamColor.RED].heroes.append(performer)
        EffectManager.create_effect(
            state=game_state,
            source_id="hero_performer",
            source_card_id="card_1",
            effect_type=EffectType.TARGET_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_TURN,
            is_active=True,
        )

    def test_defeating_the_card_owner_ends_the_performers_effect(self, game_state):
        self._state_with_performed_card(game_state)

        EffectManager.expire_by_source(game_state, "hero_owner")

        assert game_state.active_effects == []

    def test_defeating_the_performer_leaves_the_effect_on_the_owners_card(self, game_state):
        self._state_with_performed_card(game_state)

        EffectManager.expire_by_source(game_state, "hero_performer")

        assert len(game_state.active_effects) == 1

    def test_a_cardless_effect_still_ends_with_its_creator(self, game_state):
        """Engine-internal delayed triggers have no card to read an owner from."""
        EffectManager.create_effect(
            state=game_state,
            source_id="hero_1",
            effect_type=EffectType.TARGET_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_TURN,
            is_active=True,
        )

        EffectManager.expire_by_source(game_state, "hero_1")

        assert game_state.active_effects == []


class TestSubjectId:
    """``subject_id`` names the unit an effect is registered against.

    Unit-bound immunity protects its subject; when unset the subject is the
    creator, which is true of every self-targeting effect (Death Seeker,
    Snorri's Oath). Hanu's Journey is the case that needs them to differ: Hanu
    creates it, the displaced hero is protected by it.
    """

    def test_subject_defaults_to_the_source(self, game_state):
        effect = EffectManager.create_effect(
            state=game_state,
            source_id="hero_1",
            effect_type=EffectType.IMMUNITY_ENEMY_ACTIONS,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_TURN,
            is_active=True,
        )

        assert effect.protected_unit_id == "hero_1"

    def test_subject_overrides_the_source(self, game_state):
        effect = EffectManager.create_effect(
            state=game_state,
            source_id="hero_1",
            subject_id="hero_2",
            effect_type=EffectType.IMMUNITY_ENEMY_ACTIONS,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_TURN,
            is_active=True,
        )

        assert effect.protected_unit_id == "hero_2"


class TestTokenBoundEffects:
    """A token-bound effect's lifecycle is the token's and nothing else's.

    The token stays on the board when its placer is defeated, has no card to
    leave play, and is reclaimed on its own schedule — so only removing the
    token ends the effect it projects.
    """

    def _token_effect(self, game_state, duration=DurationType.PASSIVE):
        return EffectManager.create_effect(
            state=game_state,
            source_id="hero_1",
            token_id="ice_1",
            effect_type=EffectType.AREA_STAT_MODIFIER,
            scope=EffectScope(shape=Shape.ADJACENT, origin_id="ice_1"),
            duration=duration,
            is_active=True,
        )

    def test_survives_the_defeat_of_the_hero_who_placed_it(self, game_state):
        self._token_effect(game_state)

        EffectManager.expire_by_source(game_state, "hero_1")

        assert len(game_state.active_effects) == 1

    def test_survives_a_turn_expiry_sweep(self, game_state):
        self._token_effect(game_state, duration=DurationType.THIS_TURN)

        EffectManager.expire_active_turn_effects(game_state)

        assert len(game_state.active_effects) == 1

    def test_survives_a_round_expiry_sweep(self, game_state):
        self._token_effect(game_state, duration=DurationType.THIS_ROUND)

        EffectManager.expire_effects(game_state, DurationType.THIS_ROUND)

        assert len(game_state.active_effects) == 1

    def test_ends_when_its_token_leaves_the_board(self, game_state):
        from goa2.domain.models import Token, TokenType
        from goa2.domain.types import BoardEntityID
        from goa2.engine.steps.markers import _remove_token_from_board

        token = Token(id="ice_1", name="Ice", token_type=TokenType.ICE)
        game_state.register_entity(token)
        game_state.entity_locations[BoardEntityID("ice_1")] = Hex(q=0, r=0, s=0)
        self._token_effect(game_state)

        _remove_token_from_board(game_state, "ice_1")

        assert game_state.active_effects == []

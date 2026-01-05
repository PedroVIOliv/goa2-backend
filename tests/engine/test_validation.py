"""Tests for ValidationService and ValidationResult."""
import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.tile import Tile
from goa2.domain.models import (
    Team, TeamColor, Card, CardTier, CardColor, ActionType, Hero
)
from goa2.domain.hex import Hex
from goa2.domain.models.modifier import Modifier, DurationType
from goa2.domain.models.effect import (
    ActiveEffect, EffectType, EffectScope, Shape, AffectsFilter
)
from goa2.engine.validation import ValidationResult, ValidationService


# --- Fixtures ---

@pytest.fixture
def empty_state():
    """Basic state with empty teams."""
    return GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[])
        }
    )


@pytest.fixture
def state_with_heroes():
    """State with heroes on both teams and cards."""
    # Create cards for heroes
    red_card = Card(
        id="red_card_1",
        name="Red Attack",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=2,
        effect_id="e1",
        effect_text="Attack"
    )
    blue_card = Card(
        id="blue_card_1",
        name="Blue Shield",
        tier=CardTier.I,
        color=CardColor.BLUE,
        initiative=3,
        primary_action=ActionType.DEFENSE,
        primary_action_value=2,
        effect_id="e2",
        effect_text="Defend"
    )

    red_hero = Hero(
        id="red_hero",
        name="Red Hero",
        team=TeamColor.RED,
        deck=[red_card]
    )
    red_hero.hand.append(red_card)

    blue_hero = Hero(
        id="blue_hero",
        name="Blue Hero",
        team=TeamColor.BLUE,
        deck=[blue_card]
    )
    blue_hero.hand.append(blue_card)

    # Create board with tiles
    board = Board()
    for q in range(-2, 3):
        for r in range(-2, 3):
            s = -q - r
            if abs(s) <= 2:
                h = Hex(q=q, r=r, s=s)
                board.tiles[h] = Tile(hex=h)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[red_hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[blue_hero], minions=[])
        },
        turn=1,
        round=1
    )

    # Place heroes on board
    state.place_entity("red_hero", Hex(q=0, r=0, s=0))
    state.place_entity("blue_hero", Hex(q=2, r=-1, s=-1))

    return state


class TestValidationResult:
    """Tests for ValidationResult data class."""

    def test_validation_result_allow(self):
        """allow() creates a result with allowed=True."""
        result = ValidationResult.allow()
        assert result.allowed is True
        assert result.reason == ""
        assert result.blocking_effect_ids == []
        assert result.blocking_modifier_ids == []

    def test_validation_result_deny_basic(self):
        """deny() creates a result with allowed=False and reason."""
        result = ValidationResult.deny(reason="Movement prevented")
        assert result.allowed is False
        assert result.reason == "Movement prevented"

    def test_validation_result_deny_with_modifier_ids(self):
        """deny() can include blocking modifier IDs."""
        result = ValidationResult.deny(
            reason="Action blocked",
            modifier_ids=["mod_1", "mod_2"]
        )
        assert result.allowed is False
        assert "mod_1" in result.blocking_modifier_ids
        assert "mod_2" in result.blocking_modifier_ids

    def test_validation_result_deny_with_effect_ids(self):
        """deny() can include blocking effect IDs."""
        result = ValidationResult.deny(
            reason="Placement blocked",
            effect_ids=["eff_1"]
        )
        assert result.allowed is False
        assert "eff_1" in result.blocking_effect_ids

    def test_validation_result_deny_with_source(self):
        """deny() can include the source that caused the block."""
        result = ValidationResult.deny(
            reason="Blocked by enemy",
            source="enemy_hero"
        )
        assert result.allowed is False
        assert result.blocked_by_source == "enemy_hero"

    def test_validation_result_deny_full(self):
        """deny() with all parameters."""
        result = ValidationResult.deny(
            reason="Cannot be placed",
            effect_ids=["eff_1"],
            modifier_ids=["mod_1"],
            source="wasp"
        )
        assert result.allowed is False
        assert result.reason == "Cannot be placed"
        assert result.blocking_effect_ids == ["eff_1"]
        assert result.blocking_modifier_ids == ["mod_1"]
        assert result.blocked_by_source == "wasp"


class TestValidationServiceCardState:
    """Tests for card state checking in ValidationService."""

    def test_is_card_in_played_state_card_in_hand(self, state_with_heroes):
        """Card in hand is not in played state."""
        state = state_with_heroes
        hero = state.get_hero("red_hero")
        card = hero.hand[0]

        validator = ValidationService()
        assert validator._is_card_in_played_state(state, "red_hero", card.id) is False

    def test_is_card_in_played_state_current_turn_card(self, state_with_heroes):
        """Card that is current_turn_card is in played state."""
        state = state_with_heroes
        hero = state.get_hero("red_hero")
        card = hero.hand[0]

        # Play the card
        hero.play_card(card)

        validator = ValidationService()
        assert validator._is_card_in_played_state(state, "red_hero", card.id) is True

    def test_is_card_in_played_state_resolved(self, state_with_heroes):
        """Card in played_cards (resolved) is in played state."""
        state = state_with_heroes
        hero = state.get_hero("red_hero")
        card = hero.hand[0]

        # Play and resolve
        hero.play_card(card)
        hero.resolve_current_card()

        validator = ValidationService()
        assert validator._is_card_in_played_state(state, "red_hero", card.id) is True

    def test_is_card_in_played_state_after_retrieval(self, state_with_heroes):
        """Card retrieved to hand is not in played state."""
        state = state_with_heroes
        hero = state.get_hero("red_hero")
        card = hero.hand[0]

        # Play, resolve, then retrieve
        hero.play_card(card)
        hero.resolve_current_card()
        hero.retrieve_cards()

        validator = ValidationService()
        assert validator._is_card_in_played_state(state, "red_hero", card.id) is False


class TestValidationServiceModifierActive:
    """Tests for modifier activity checking."""

    def test_modifier_active_passive_duration(self, empty_state):
        """PASSIVE modifiers are always active."""
        mod = Modifier(
            id="mod_1",
            source_id="hero_1",
            target_id="hero_2",
            status_tag="BONUS",
            duration=DurationType.PASSIVE,
            created_at_turn=1,
            created_at_round=1
        )

        validator = ValidationService()
        assert validator._is_modifier_active(mod, empty_state) is True

    def test_modifier_inactive_when_card_not_played(self, state_with_heroes):
        """Modifier with source_card_id is inactive when card not played."""
        state = state_with_heroes
        hero = state.get_hero("blue_hero")
        card = hero.hand[0]  # Card still in hand

        mod = Modifier(
            id="mod_1",
            source_id="blue_hero",
            source_card_id=card.id,
            target_id="red_hero",
            status_tag="PREVENT_MOVEMENT",
            duration=DurationType.THIS_TURN,
            created_at_turn=1,
            created_at_round=1
        )

        validator = ValidationService()
        assert validator._is_modifier_active(mod, state) is False

    def test_modifier_active_when_card_played(self, state_with_heroes):
        """Modifier with source_card_id is active when card is played."""
        state = state_with_heroes
        hero = state.get_hero("blue_hero")
        card = hero.hand[0]

        # Play the card
        hero.play_card(card)
        hero.resolve_current_card()

        mod = Modifier(
            id="mod_1",
            source_id="blue_hero",
            source_card_id=card.id,
            target_id="red_hero",
            status_tag="PREVENT_MOVEMENT",
            duration=DurationType.THIS_TURN,
            created_at_turn=1,
            created_at_round=1
        )

        validator = ValidationService()
        assert validator._is_modifier_active(mod, state) is True

    def test_modifier_this_turn_correct_turn(self, empty_state):
        """THIS_TURN modifier is active on same turn."""
        empty_state.turn = 2
        empty_state.round = 1

        mod = Modifier(
            id="mod_1",
            source_id="hero_1",
            target_id="hero_2",
            status_tag="BONUS",
            duration=DurationType.THIS_TURN,
            created_at_turn=2,
            created_at_round=1
        )

        validator = ValidationService()
        assert validator._is_modifier_active(mod, empty_state) is True

    def test_modifier_this_turn_wrong_turn(self, empty_state):
        """THIS_TURN modifier is inactive on different turn."""
        empty_state.turn = 3
        empty_state.round = 1

        mod = Modifier(
            id="mod_1",
            source_id="hero_1",
            target_id="hero_2",
            status_tag="BONUS",
            duration=DurationType.THIS_TURN,
            created_at_turn=2,
            created_at_round=1
        )

        validator = ValidationService()
        assert validator._is_modifier_active(mod, empty_state) is False

    def test_modifier_this_round_correct_round(self, empty_state):
        """THIS_ROUND modifier is active on same round."""
        empty_state.turn = 3
        empty_state.round = 1

        mod = Modifier(
            id="mod_1",
            source_id="hero_1",
            target_id="hero_2",
            status_tag="BONUS",
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1
        )

        validator = ValidationService()
        assert validator._is_modifier_active(mod, empty_state) is True

    def test_modifier_this_round_wrong_round(self, empty_state):
        """THIS_ROUND modifier is inactive on different round."""
        empty_state.turn = 1
        empty_state.round = 2

        mod = Modifier(
            id="mod_1",
            source_id="hero_1",
            target_id="hero_2",
            status_tag="BONUS",
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1
        )

        validator = ValidationService()
        assert validator._is_modifier_active(mod, empty_state) is False

    def test_modifier_next_turn_activates_correctly(self, empty_state):
        """NEXT_TURN modifier activates on the following turn."""
        empty_state.turn = 2
        empty_state.round = 1

        mod = Modifier(
            id="mod_1",
            source_id="hero_1",
            target_id="hero_2",
            status_tag="PREVENT_ATTACK",
            duration=DurationType.NEXT_TURN,
            created_at_turn=1,
            created_at_round=1
        )

        validator = ValidationService()
        assert validator._is_modifier_active(mod, empty_state) is True

    def test_modifier_next_turn_not_active_on_creation_turn(self, empty_state):
        """NEXT_TURN modifier is not active on creation turn."""
        empty_state.turn = 1
        empty_state.round = 1

        mod = Modifier(
            id="mod_1",
            source_id="hero_1",
            target_id="hero_2",
            status_tag="PREVENT_ATTACK",
            duration=DurationType.NEXT_TURN,
            created_at_turn=1,
            created_at_round=1
        )

        validator = ValidationService()
        assert validator._is_modifier_active(mod, empty_state) is False

    def test_modifier_next_turn_cross_round_never_activates(self, empty_state):
        """NEXT_TURN modifier created on Turn 4 never activates (cards retrieved)."""
        # Created turn 4, now turn 1 of next round
        empty_state.turn = 1
        empty_state.round = 2

        mod = Modifier(
            id="mod_1",
            source_id="hero_1",
            target_id="hero_2",
            status_tag="PREVENT_MOVEMENT",
            duration=DurationType.NEXT_TURN,
            created_at_turn=4,
            created_at_round=1
        )

        validator = ValidationService()
        # Should be False because cross-round NEXT_TURN never activates
        assert validator._is_modifier_active(mod, empty_state) is False


class TestValidationServiceCanPerformAction:
    """Tests for can_perform_action validation."""

    def test_can_perform_action_no_prevention(self, empty_state):
        """Action allowed when no prevention modifiers exist."""
        validator = ValidationService()
        result = validator.can_perform_action(
            empty_state, "hero_1", ActionType.MOVEMENT
        )
        assert result.allowed is True

    def test_can_perform_action_movement_prevented(self, empty_state):
        """Movement blocked by PREVENT_MOVEMENT status tag."""
        empty_state.active_modifiers.append(Modifier(
            id="mod_1",
            source_id="enemy",
            target_id="hero_1",
            status_tag="PREVENT_MOVEMENT",
            duration=DurationType.PASSIVE,
            created_at_turn=1,
            created_at_round=1
        ))

        validator = ValidationService()
        result = validator.can_perform_action(
            empty_state, "hero_1", ActionType.MOVEMENT
        )
        assert result.allowed is False
        assert "mod_1" in result.blocking_modifier_ids

    def test_can_perform_action_attack_prevented(self, empty_state):
        """Attack blocked by PREVENT_ATTACK status tag."""
        empty_state.active_modifiers.append(Modifier(
            id="mod_1",
            source_id="enemy",
            target_id="hero_1",
            status_tag="PREVENT_ATTACK",
            duration=DurationType.PASSIVE,
            created_at_turn=1,
            created_at_round=1
        ))

        validator = ValidationService()
        result = validator.can_perform_action(
            empty_state, "hero_1", ActionType.ATTACK
        )
        assert result.allowed is False

    def test_can_perform_action_other_hero_not_affected(self, empty_state):
        """Prevention on hero_1 doesn't affect hero_2."""
        empty_state.active_modifiers.append(Modifier(
            id="mod_1",
            source_id="enemy",
            target_id="hero_1",
            status_tag="PREVENT_MOVEMENT",
            duration=DurationType.PASSIVE,
            created_at_turn=1,
            created_at_round=1
        ))

        validator = ValidationService()
        result = validator.can_perform_action(
            empty_state, "hero_2", ActionType.MOVEMENT
        )
        assert result.allowed is True

    def test_can_perform_action_inactive_modifier_ignored(self, empty_state):
        """Inactive modifiers don't prevent actions."""
        empty_state.turn = 2
        empty_state.round = 1

        # Modifier from turn 1, now turn 2
        empty_state.active_modifiers.append(Modifier(
            id="mod_1",
            source_id="enemy",
            target_id="hero_1",
            status_tag="PREVENT_MOVEMENT",
            duration=DurationType.THIS_TURN,
            created_at_turn=1,
            created_at_round=1
        ))

        validator = ValidationService()
        result = validator.can_perform_action(
            empty_state, "hero_1", ActionType.MOVEMENT
        )
        assert result.allowed is True


class TestValidationServiceCanBePlaced:
    """Tests for can_be_placed validation."""

    def test_can_be_placed_no_effects(self, state_with_heroes):
        """Placement allowed when no effects exist."""
        state = state_with_heroes
        state.current_actor_id = "red_hero"

        validator = ValidationService()
        result = validator.can_be_placed(
            state,
            unit_id="red_hero",
            actor_id="red_hero",
            destination=Hex(q=1, r=0, s=-1)
        )
        assert result.allowed is True

    def test_can_be_placed_blocked_by_status_tag(self, state_with_heroes):
        """Placement blocked by PREVENT_PLACEMENT status tag."""
        state = state_with_heroes

        # Add prevention modifier on red_hero
        state.active_modifiers.append(Modifier(
            id="mod_1",
            source_id="blue_hero",
            target_id="red_hero",
            status_tag="PREVENT_PLACEMENT",
            duration=DurationType.PASSIVE,
            created_at_turn=1,
            created_at_round=1
        ))

        validator = ValidationService()
        result = validator.can_be_placed(
            state,
            unit_id="red_hero",
            actor_id="blue_hero",  # Enemy trying to place
            destination=Hex(q=1, r=0, s=-1)
        )
        assert result.allowed is False
        assert "mod_1" in result.blocking_modifier_ids

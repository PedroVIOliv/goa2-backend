"""Tests for ValidationService and ValidationResult."""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.tile import Tile
from goa2.domain.models import (
    Team,
    TeamColor,
    Card,
    CardTier,
    CardColor,
    ActionType,
    Hero,
)
from goa2.domain.hex import Hex
from goa2.engine.validation import ValidationResult, ValidationService


# --- Fixtures ---


@pytest.fixture
def empty_state():
    """Basic state with empty teams."""
    return GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
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
        effect_text="Attack",
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
        effect_text="Defend",
    )

    red_hero = Hero(id="red_hero", name="Red Hero", team=TeamColor.RED, deck=[red_card])
    red_hero.hand.append(red_card)

    blue_hero = Hero(
        id="blue_hero", name="Blue Hero", team=TeamColor.BLUE, deck=[blue_card]
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
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[blue_hero], minions=[]),
        },
        turn=1,
        round=1,
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
            reason="Action blocked", modifier_ids=["mod_1", "mod_2"]
        )
        assert result.allowed is False
        assert "mod_1" in result.blocking_modifier_ids
        assert "mod_2" in result.blocking_modifier_ids

    def test_validation_result_deny_with_effect_ids(self):
        """deny() can include blocking effect IDs."""
        result = ValidationResult.deny(reason="Placement blocked", effect_ids=["eff_1"])
        assert result.allowed is False
        assert "eff_1" in result.blocking_effect_ids

    def test_validation_result_deny_with_source(self):
        """deny() can include the source that caused the block."""
        result = ValidationResult.deny(reason="Blocked by enemy", source="enemy_hero")
        assert result.allowed is False
        assert result.blocked_by_source == "enemy_hero"

    def test_validation_result_deny_full(self):
        """deny() with all parameters."""
        result = ValidationResult.deny(
            reason="Cannot be placed",
            effect_ids=["eff_1"],
            modifier_ids=["mod_1"],
            source="wasp",
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
        """Card that is current_turn_card (UNRESOLVED) is NOT in active played state.

        Per game rules, active effects only become active once the card is RESOLVED
        (after the hero's turn completes). During resolution, the card is still
        UNRESOLVED and its effects shouldn't be active yet.
        """
        state = state_with_heroes
        hero = state.get_hero("red_hero")
        card = hero.hand[0]

        # Play the card (UNRESOLVED state)
        hero.play_card(card)

        validator = ValidationService()
        # UNRESOLVED cards should NOT have active effects
        assert validator._is_card_in_played_state(state, "red_hero", card.id) is False

    def test_is_card_in_played_state_resolved(self, state_with_heroes):
        """Card in played_cards (RESOLVED + face-up) is in active played state."""
        state = state_with_heroes
        hero = state.get_hero("red_hero")
        card = hero.hand[0]

        # Play, reveal (face-up), and resolve
        hero.play_card(card)
        card.is_facedown = False  # Revelation phase flips card face-up
        hero.resolve_current_card()

        validator = ValidationService()
        assert validator._is_card_in_played_state(state, "red_hero", card.id) is True

    def test_is_card_in_played_state_resolved_but_facedown(self, state_with_heroes):
        """Card that is RESOLVED but facedown should NOT have active effects.

        Per game rules, active effects are cancelled when the card is turned facedown.
        """
        state = state_with_heroes
        hero = state.get_hero("red_hero")
        card = hero.hand[0]

        # Play and resolve without revealing (edge case)
        hero.play_card(card)
        hero.resolve_current_card()
        # Card is still facedown

        validator = ValidationService()
        assert validator._is_card_in_played_state(state, "red_hero", card.id) is False

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


class TestValidationServiceCanPerformAction:
    """Tests for can_perform_action validation."""

    def test_can_perform_action_no_prevention(self, empty_state):
        """Action allowed when no prevention modifiers exist."""
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
            destination=Hex(q=1, r=0, s=-1),
        )
        assert result.allowed is True

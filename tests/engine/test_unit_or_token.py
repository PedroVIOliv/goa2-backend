"""
Tests for UNIT_OR_TOKEN target type support.

Covers:
- GameState.get_units_and_tokens() helper method
- SelectStep with target_type=UNIT_OR_TOKEN
- TelekinesisEffect integration
"""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Token,
)
from goa2.domain.hex import Hex
from goa2.domain.types import BoardEntityID
from goa2.engine.steps import SelectStep, TargetType
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.filters import RangeFilter


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def state_with_units_and_tokens():
    """
    Creates a state with:
    - Hero (wasp) at (0,0,0)
    - Enemy hero at (1,0,-1)
    - Token at (1,1,-2)
    """
    board = Board()
    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=1, r=1, s=-2),
        Hex(q=2, r=0, s=-2),
        Hex(q=0, r=1, s=-1),
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    wasp = Hero(id="wasp", name="Wasp", team=TeamColor.RED, deck=[], level=1)
    enemy = Hero(id="enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[wasp], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )

    # Place units
    state.place_entity("wasp", Hex(q=0, r=0, s=0))
    state.place_entity("enemy", Hex(q=1, r=0, s=-1))

    # Create and place a token
    token = Token(id=BoardEntityID("trap_1"), name="Trap")
    state.misc_entities[BoardEntityID("trap_1")] = token
    state.place_entity(BoardEntityID("trap_1"), Hex(q=1, r=1, s=-2))

    state.current_actor_id = "wasp"
    return state


# =============================================================================
# GameState.get_units_and_tokens() Tests
# =============================================================================


class TestGetUnitsAndTokens:
    """Tests for the get_units_and_tokens() helper method."""

    def test_returns_units_and_tokens(self, state_with_units_and_tokens):
        """Test that the method returns both units and tokens."""
        result = state_with_units_and_tokens.get_units_and_tokens()

        # Should include: wasp, enemy (units) and trap_1 (token)
        assert "wasp" in result or BoardEntityID("wasp") in result
        assert "enemy" in result or BoardEntityID("enemy") in result
        assert "trap_1" in result or BoardEntityID("trap_1") in result
        assert len(result) == 3

    def test_excludes_non_placed_entities(self, state_with_units_and_tokens):
        """Test that only placed entities are returned."""
        # Create a token but don't place it
        unplaced_token = Token(id=BoardEntityID("unplaced"), name="Unplaced")
        state_with_units_and_tokens.misc_entities[BoardEntityID("unplaced")] = (
            unplaced_token
        )

        result = state_with_units_and_tokens.get_units_and_tokens()

        # Unplaced token should not be in result
        assert "unplaced" not in result and BoardEntityID("unplaced") not in result

    def test_empty_board(self):
        """Test with no entities on the board."""
        board = Board()
        hexes = {Hex(q=0, r=0, s=0)}
        z1 = Zone(id="z1", hexes=hexes, neighbors=[])
        board.zones = {"z1": z1}
        board.populate_tiles_from_zones()

        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
            },
        )

        result = state.get_units_and_tokens()
        assert result == []


# =============================================================================
# SelectStep with UNIT_OR_TOKEN Tests
# =============================================================================


class TestSelectStepUnitOrToken:
    """Tests for SelectStep with target_type=UNIT_OR_TOKEN."""

    def test_includes_both_units_and_tokens(self, state_with_units_and_tokens):
        """Test that UNIT_OR_TOKEN selection includes both units and tokens."""
        step = SelectStep(
            target_type=TargetType.UNIT_OR_TOKEN,
            prompt="Select unit or token",
            output_key="target",
            is_mandatory=False,
            skip_immunity_filter=True,  # Skip immunity for this test
            skip_self_filter=True,  # Test wants to include the acting hero
        )

        push_steps(state_with_units_and_tokens, [step])
        req = process_resolution_stack(state_with_units_and_tokens)

        assert req is not None
        assert req["type"] == "SELECT_UNIT_OR_TOKEN"

        valid_options = req["valid_options"]

        # Should include units and tokens
        assert "wasp" in valid_options
        assert "enemy" in valid_options
        assert "trap_1" in valid_options

    def test_filters_apply_to_both(self, state_with_units_and_tokens):
        """Test that filters are applied to both units and tokens."""
        # RangeFilter should work on both
        step = SelectStep(
            target_type=TargetType.UNIT_OR_TOKEN,
            prompt="Select unit or token in range",
            output_key="target",
            is_mandatory=False,
            skip_immunity_filter=True,
            filters=[RangeFilter(max_range=1)],  # Only adjacent
        )

        push_steps(state_with_units_and_tokens, [step])
        req = process_resolution_stack(state_with_units_and_tokens)

        valid_options = req["valid_options"]

        # Only enemy is adjacent (range 1), wasp is self (range 0), token is range 2
        assert "enemy" in valid_options
        # wasp might be included (range 0 is within max_range=1)
        # trap_1 should be excluded (range 2)
        assert "trap_1" not in valid_options

    def test_mandatory_fails_when_no_valid_candidates(self):
        """Test that mandatory selection fails properly."""
        board = Board()
        hexes = {Hex(q=0, r=0, s=0)}
        z1 = Zone(id="z1", hexes=hexes, neighbors=[])
        board.zones = {"z1": z1}
        board.populate_tiles_from_zones()

        wasp = Hero(id="wasp", name="Wasp", team=TeamColor.RED, deck=[], level=1)

        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[wasp], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
            },
        )
        state.place_entity("wasp", Hex(q=0, r=0, s=0))
        state.current_actor_id = "wasp"

        # Mandatory selection with filter that excludes everything
        step = SelectStep(
            target_type=TargetType.UNIT_OR_TOKEN,
            prompt="Select something",
            output_key="target",
            is_mandatory=True,
            skip_immunity_filter=True,
            filters=[RangeFilter(max_range=1, min_range=1)],  # Excludes self
        )

        push_steps(state, [step])
        req = process_resolution_stack(state)

        # Should abort (mandatory with no candidates)
        assert req is None  # Stack exhausted due to abort


# =============================================================================
# TelekinesisEffect Integration Tests
# =============================================================================


class TestTelekinesisWithToken:
    """Integration tests for TelekinesisEffect targeting tokens."""

    def test_telekinesis_can_select_token(self, state_with_units_and_tokens):
        """Test that Telekinesis can target a token."""
        from goa2.engine.effects import CardEffectRegistry
        from goa2.domain.models import Card, CardTier, CardColor, ActionType
        import goa2.scripts.wasp_effects  # noqa: F401

        effect = CardEffectRegistry.get("telekinesis")
        assert effect is not None

        wasp = state_with_units_and_tokens.get_hero("wasp")

        card = Card(
            id="telekinesis",
            name="Telekinesis",
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=7,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            is_ranged=False,
            range_value=3,
            effect_id="telekinesis",
            effect_text="Place a unit or a token in range...",
            is_facedown=False,
        )

        steps = effect.get_steps(state_with_units_and_tokens, wasp, card)

        # First step should be SelectStep with UNIT_OR_TOKEN
        select_step = steps[0]
        assert select_step.target_type == TargetType.UNIT_OR_TOKEN


# =============================================================================
# ValidationService Token Support Tests
# =============================================================================


class TestValidationServiceTokenSupport:
    """Tests for ValidationService.can_be_placed() with tokens."""

    def test_can_be_placed_accepts_tokens(self, state_with_units_and_tokens):
        """Test that can_be_placed() works with tokens."""
        result = state_with_units_and_tokens.validator.can_be_placed(
            state=state_with_units_and_tokens,
            unit_id="trap_1",  # Token ID
            actor_id="wasp",
        )
        assert result.allowed is True

    def test_can_be_placed_rejects_missing_entity(self, state_with_units_and_tokens):
        """Test that can_be_placed() rejects non-existent entities."""
        result = state_with_units_and_tokens.validator.can_be_placed(
            state=state_with_units_and_tokens,
            unit_id="nonexistent",
            actor_id="wasp",
        )
        assert result.allowed is False
        assert "not found" in result.reason.lower()

    def test_can_be_placed_with_destination_validation(
        self, state_with_units_and_tokens
    ):
        """Test that destination validation works for tokens."""
        # Try to place token at occupied hex
        result = state_with_units_and_tokens.validator.can_be_placed(
            state=state_with_units_and_tokens,
            unit_id="trap_1",
            actor_id="wasp",
            destination=Hex(q=1, r=0, s=-1),  # Occupied by enemy
        )
        assert result.allowed is False
        assert "occupied" in result.reason.lower()

    def test_can_be_placed_with_empty_destination(self, state_with_units_and_tokens):
        """Test that token can be placed at empty hex."""
        result = state_with_units_and_tokens.validator.can_be_placed(
            state=state_with_units_and_tokens,
            unit_id="trap_1",
            actor_id="wasp",
            destination=Hex(q=0, r=1, s=-1),  # Empty hex
        )
        assert result.allowed is True

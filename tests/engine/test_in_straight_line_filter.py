"""
Tests for InStraightLineFilter.
"""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import Team, TeamColor, Hero
from goa2.domain.hex import Hex
from goa2.domain.models.enums import FilterType
from goa2.engine.filters import InStraightLineFilter, NotInStraightLineFilter


@pytest.fixture
def simple_state():
    """Create a simple game state with units in various positions."""
    board = Board()
    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=2, r=0, s=-2),
        Hex(q=1, r=1, s=-2),
        Hex(q=0, r=1, s=-1),
        Hex(q=-1, r=1, s=0),
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    # Create hero
    wasp = Hero(id="wasp", name="Wasp", team=TeamColor.RED, deck=[], level=1)

    # Create enemy units
    enemy_adjacent = Hero(
        id="enemy_adjacent",
        name="Enemy Adjacent",
        team=TeamColor.BLUE,
        deck=[],
        level=1,
    )
    enemy_straight = Hero(
        id="enemy_straight",
        name="Enemy Straight",
        team=TeamColor.BLUE,
        deck=[],
        level=1,
    )
    enemy_diagonal = Hero(
        id="enemy_diagonal",
        name="Enemy Diagonal",
        team=TeamColor.BLUE,
        deck=[],
        level=1,
    )
    enemy_adjacent2 = Hero(
        id="enemy_adjacent2",
        name="Enemy Adjacent 2",
        team=TeamColor.BLUE,
        deck=[],
        level=1,
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[wasp], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE,
                heroes=[
                    enemy_adjacent,
                    enemy_straight,
                    enemy_diagonal,
                    enemy_adjacent2,
                ],
                minions=[],
            ),
        },
    )

    state.place_entity("wasp", Hex(q=0, r=0, s=0))
    state.place_entity(
        "enemy_adjacent", Hex(q=1, r=0, s=-1)
    )  # Same q-axis, straight line
    state.place_entity(
        "enemy_straight", Hex(q=2, r=0, s=-2)
    )  # Same q-axis, straight line
    state.place_entity(
        "enemy_diagonal", Hex(q=1, r=1, s=-2)
    )  # Diagonal, NOT straight line
    state.place_entity(
        "enemy_adjacent2", Hex(q=0, r=1, s=-1)
    )  # Same s-axis, straight line

    state.current_actor_id = "wasp"
    return state


def test_in_straight_line_filter_type():
    """Test that the filter has the correct type."""
    f = InStraightLineFilter()
    assert f.type == FilterType.IN_STRAIGHT_LINE


def test_in_straight_line_includes_straight_line(simple_state):
    """
    Test that InStraightLineFilter includes targets in a straight line.
    """
    f = InStraightLineFilter()

    # Should include units in straight line
    assert f.apply("enemy_adjacent", simple_state, {}) is True, (
        "Adjacent unit in straight line should be included"
    )
    assert f.apply("enemy_straight", simple_state, {}) is True, (
        "Straight line unit should be included"
    )
    assert f.apply("enemy_adjacent2", simple_state, {}) is True, (
        "Second adjacent unit in straight line should be included"
    )

    # Should NOT include diagonal unit
    assert f.apply("enemy_diagonal", simple_state, {}) is False, (
        "Diagonal unit should NOT be included"
    )


def test_in_straight_line_with_hex_candidates(simple_state):
    """Test the filter works with Hex objects as candidates."""
    f = InStraightLineFilter()
    from goa2.domain.types import BoardEntityID

    # Test with Hex objects
    straight_hex = Hex(q=2, r=0, s=-2)
    diagonal_hex = Hex(q=1, r=1, s=-2)

    assert f.apply(straight_hex, simple_state, {}) is True, (
        "Straight line hex should be included"
    )
    assert f.apply(diagonal_hex, simple_state, {}) is False, (
        "Diagonal hex should NOT be included"
    )


def test_in_straight_line_filter_origin_id(simple_state):
    """Test that filter respects custom origin_id."""
    # Use enemy_diagonal as origin - it's at (1, 1, -2)
    f = InStraightLineFilter(origin_id="enemy_diagonal")

    # Origin is at (1, 1, -2), checking if other units are in straight line from there
    # wasp at (0, 0, 0) - no matching coordinates, NOT straight line
    # enemy_adjacent at (1, 0, -1) - same q-axis (q=1), straight line
    # enemy_straight at (2, 0, -2) - same s-axis (s=-2), straight line
    # enemy_adjacent2 at (0, 1, -1) - same r-axis (r=1), straight line

    assert f.apply("wasp", simple_state, {}) is False, (
        "Wasp not in straight line from enemy_diagonal"
    )
    assert f.apply("enemy_adjacent", simple_state, {}) is True, (
        "enemy_adjacent in straight line (same q-axis)"
    )
    assert f.apply("enemy_straight", simple_state, {}) is True, (
        "enemy_straight in straight line (same s-axis)"
    )
    assert f.apply("enemy_adjacent2", simple_state, {}) is True, (
        "enemy_adjacent2 in straight line (same r-axis)"
    )


def test_in_straight_line_filter_origin_key(simple_state):
    """Test that the filter respects origin_key from context."""
    f = InStraightLineFilter(origin_key="custom_origin")

    context = {"custom_origin": "enemy_adjacent"}

    # Same as test_in_straight_line_filter_origin_id but using context
    assert f.apply("enemy_straight", simple_state, context) is True
    assert f.apply("enemy_diagonal", simple_state, context) is True
    assert f.apply("wasp", simple_state, context) is True


def test_in_straight_line_vs_not_in_straight_line(simple_state):
    """Test that InStraightLineFilter and NotInStraightLineFilter are opposites."""
    in_filter = InStraightLineFilter()
    not_in_filter = NotInStraightLineFilter()

    for unit_id in [
        "enemy_adjacent",
        "enemy_straight",
        "enemy_diagonal",
        "enemy_adjacent2",
    ]:
        in_result = in_filter.apply(unit_id, simple_state, {})
        not_in_result = not_in_filter.apply(unit_id, simple_state, {})

        # They should be opposites
        assert in_result is not not_in_result, (
            f"InStraightLineFilter and NotInStraightLineFilter should return opposite results for {unit_id}"
        )


def test_in_straight_line_respects_topology():
    """
    Test that InStraightLineFilter respects topology (same reality).

    If units are in different realities (disconnected by topology),
    they should NOT be considered "in a straight line" even if
    geometrically aligned.
    """
    from goa2.domain.models.effect import (
        ActiveEffect,
        EffectType,
        Shape,
        EffectScope,
        DurationType,
    )
    from goa2.domain.models.effect import ActiveEffect

    board = Board()
    hexes = {
        Hex(q=-1, r=0, s=1),  # NEGATIVE
        Hex(q=0, r=0, s=0),  # ZERO (bridge)
        Hex(q=1, r=0, s=-1),  # POSITIVE
        Hex(q=2, r=0, s=-2),  # POSITIVE
        Hex(q=3, r=0, s=-3),  # POSITIVE
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    wasp = Hero(id="wasp", name="Wasp", team=TeamColor.RED, deck=[], level=1)
    enemy_negative = Hero(
        id="enemy_negative",
        name="Enemy Negative",
        team=TeamColor.BLUE,
        deck=[],
        level=1,
    )
    enemy_positive = Hero(
        id="enemy_positive",
        name="Enemy Positive",
        team=TeamColor.BLUE,
        deck=[],
        level=1,
    )
    enemy_positive_far = Hero(
        id="enemy_positive_far",
        name="Enemy Positive Far",
        team=TeamColor.BLUE,
        deck=[],
        level=1,
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[wasp], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE,
                heroes=[enemy_negative, enemy_positive, enemy_positive_far],
                minions=[],
            ),
        },
    )

    # Place units
    # Wasp in POSITIVE region (not bridge)
    state.place_entity("wasp", Hex(q=1, r=0, s=-1))

    # Enemy in NEGATIVE region (geometrically aligned but different reality)
    state.place_entity("enemy_negative", Hex(q=-1, r=0, s=1))

    # Enemies in POSITIVE region (same reality)
    state.place_entity("enemy_positive", Hex(q=2, r=0, s=-2))
    state.place_entity("enemy_positive_far", Hex(q=3, r=0, s=-3))

    state.current_actor_id = "wasp"

    # Add TOPOLOGY_SPLIT effect on q-axis, split at q=0
    # NEGATIVE: q < 0, ZERO: q = 0, POSITIVE: q > 0
    split_effect = ActiveEffect(
        id="split",
        effect_type=EffectType.TOPOLOGY_SPLIT,
        source_id="some_hero",
        scope=EffectScope(shape=Shape.GLOBAL),
        duration=DurationType.THIS_ROUND,
        created_at_turn=1,
        created_at_round=1,
        is_active=True,
        split_axis="q",
        split_value=0,
    )
    state.active_effects = [split_effect]

    f = InStraightLineFilter()

    # Geometrically: all enemies are in straight line (same r-axis, r=0)
    # But topology-aware: only same reality counts

    # Wasp (q=1, POSITIVE) can see enemy_positive (q=2, POSITIVE) - connected
    assert f.apply("enemy_positive", state, {}) is True, (
        "Enemy in POSITIVE should be in straight line"
    )

    # Wasp (q=1, POSITIVE) can see enemy_positive_far (q=3, POSITIVE) - connected
    assert f.apply("enemy_positive_far", state, {}) is True, (
        "Far enemy in POSITIVE should be in straight line"
    )

    # Wasp (q=1, POSITIVE) CANNOT see enemy_negative (q=-1, NEGATIVE) - blocked by topology
    assert f.apply("enemy_negative", state, {}) is False, (
        "Enemy in NEGATIVE should NOT be in straight line (different reality)"
    )

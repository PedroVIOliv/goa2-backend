"""
Tests for StraightLinePathFilter.
"""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import Team, TeamColor, Hero
from goa2.domain.hex import Hex
from goa2.engine.filters import StraightLinePathFilter


@pytest.fixture
def straight_line_state():
    """
    Board layout (q-axis going right):
        (0,0,0) -- (1,0,-1) -- (2,0,-2) -- (3,0,-3)
    Also add some off-axis hexes for diagonal tests.
    """
    board = Board()
    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=2, r=0, s=-2),
        Hex(q=3, r=0, s=-3),
        Hex(q=1, r=1, s=-2),  # off-axis
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    hero = Hero(id="hero_a", name="Hero A", team=TeamColor.RED, deck=[], level=1)
    enemy = Hero(id="enemy_b", name="Enemy B", team=TeamColor.BLUE, deck=[], level=1)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )

    state.place_entity("hero_a", Hex(q=0, r=0, s=0))
    state.current_actor_id = "hero_a"

    return state


def test_clear_path_allowed(straight_line_state):
    """Clear straight-line path with no obstacles → allowed."""
    f = StraightLinePathFilter(origin_id="hero_a")
    # Distance 2, intermediate hex (1,0,-1) is empty
    assert f.apply(Hex(q=2, r=0, s=-2), straight_line_state, {}) is True


def test_clear_path_distance_3(straight_line_state):
    """Clear path over 3 hexes."""
    f = StraightLinePathFilter(origin_id="hero_a")
    assert f.apply(Hex(q=3, r=0, s=-3), straight_line_state, {}) is True


def test_adjacent_hex_no_intermediates(straight_line_state):
    """Adjacent hex (distance 1) has no intermediates → always allowed."""
    f = StraightLinePathFilter(origin_id="hero_a")
    assert f.apply(Hex(q=1, r=0, s=-1), straight_line_state, {}) is True


def test_obstacle_on_intermediate_blocks(straight_line_state):
    """Unit on intermediate hex → blocked."""
    state = straight_line_state
    state.place_entity("enemy_b", Hex(q=1, r=0, s=-1))

    f = StraightLinePathFilter(origin_id="hero_a")
    assert f.apply(Hex(q=2, r=0, s=-2), state, {}) is False


def test_obstacle_on_intermediate_with_pass_through(straight_line_state):
    """Unit on intermediate hex with pass_through_obstacles=True → allowed."""
    state = straight_line_state
    state.place_entity("enemy_b", Hex(q=1, r=0, s=-1))

    f = StraightLinePathFilter(origin_id="hero_a", pass_through_obstacles=True)
    assert f.apply(Hex(q=2, r=0, s=-2), state, {}) is True


def test_not_in_straight_line_blocked(straight_line_state):
    """Destination not in straight line → blocked."""
    f = StraightLinePathFilter(origin_id="hero_a")
    # (1,1,-2) is not in a straight line from (0,0,0)
    assert f.apply(Hex(q=1, r=1, s=-2), straight_line_state, {}) is False


def test_destination_is_not_hex(straight_line_state):
    """Non-Hex candidate → rejected."""
    f = StraightLinePathFilter(origin_id="hero_a")
    assert f.apply("not_a_hex", straight_line_state, {}) is False


def test_origin_key_from_context(straight_line_state):
    """Resolves origin from context key."""
    f = StraightLinePathFilter(origin_key="charge_origin")
    ctx = {"charge_origin": "hero_a"}
    assert f.apply(Hex(q=2, r=0, s=-2), straight_line_state, ctx) is True


def test_missing_intermediate_hex_on_board(straight_line_state):
    """If an intermediate hex doesn't exist on the board, path is blocked."""
    state = straight_line_state
    # Place hero at (3,0,-3), try to go to (0,0,0)
    # Intermediate (2,0,-2) and (1,0,-1) exist, so this works
    # Instead, create a board with a gap
    board = Board()
    hexes = {
        Hex(q=0, r=0, s=0),
        # Hex(q=1, r=0, s=-1) is MISSING
        Hex(q=2, r=0, s=-2),
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    hero = Hero(id="hero_x", name="Hero X", team=TeamColor.RED, deck=[], level=1)
    state2 = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
        },
    )
    state2.place_entity("hero_x", Hex(q=0, r=0, s=0))
    state2.current_actor_id = "hero_x"

    f = StraightLinePathFilter(origin_id="hero_x")
    assert f.apply(Hex(q=2, r=0, s=-2), state2, {}) is False


def test_unit_on_destination_not_checked(straight_line_state):
    """Unit on the destination hex itself does NOT block (only intermediates matter)."""
    state = straight_line_state
    state.place_entity("enemy_b", Hex(q=2, r=0, s=-2))

    f = StraightLinePathFilter(origin_id="hero_a")
    # The destination has a unit but it's not an intermediate — should be allowed
    assert f.apply(Hex(q=2, r=0, s=-2), state, {}) is True

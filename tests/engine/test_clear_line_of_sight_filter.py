"""
Tests for ClearLineOfSightFilter.
"""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import Team, TeamColor, Hero, Minion
from goa2.domain.models.enums import MinionType
from goa2.domain.models.token import Token
from goa2.domain.hex import Hex
from goa2.engine.filters import ClearLineOfSightFilter


@pytest.fixture
def los_state():
    """
    Board layout (q-axis going right):
        (0,0,0) -- (1,0,-1) -- (2,0,-2) -- (3,0,-3) -- (4,0,-4)
    Also add off-axis hex for non-straight-line tests.
    """
    board = Board()
    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=2, r=0, s=-2),
        Hex(q=3, r=0, s=-3),
        Hex(q=4, r=0, s=-4),
        Hex(q=1, r=1, s=-2),  # off-axis
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    hero = Hero(id="hero_a", name="Hero A", team=TeamColor.RED, deck=[], level=1)
    enemy = Hero(id="enemy_b", name="Enemy B", team=TeamColor.BLUE, deck=[], level=1)
    minion = Minion(
        id="minion_1", name="Blocker", type=MinionType.MELEE, team=TeamColor.BLUE
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[enemy], minions=[minion]
            ),
        },
    )

    state.place_entity("hero_a", Hex(q=0, r=0, s=0))
    state.current_actor_id = "hero_a"

    return state


# ---- Clear path ----


def test_clear_path_to_empty_hex(los_state):
    """No blockers on intermediate hexes → passes."""
    f = ClearLineOfSightFilter()
    assert f.apply(Hex(q=3, r=0, s=-3), los_state, {}) is True


def test_clear_path_to_unit(los_state):
    """Target is a unit, intermediates are clear → passes."""
    los_state.place_entity("enemy_b", Hex(q=2, r=0, s=-2))
    f = ClearLineOfSightFilter()
    assert f.apply("enemy_b", los_state, {}) is True


def test_adjacent_always_clear(los_state):
    """Adjacent hex (distance 1) has no intermediates → always clear."""
    los_state.place_entity("enemy_b", Hex(q=1, r=0, s=-1))
    f = ClearLineOfSightFilter()
    assert f.apply("enemy_b", los_state, {}) is True


# ---- Blocked by unit ----


def test_unit_on_intermediate_blocks(los_state):
    """Unit on an intermediate hex blocks the line (default)."""
    los_state.place_entity("minion_1", Hex(q=1, r=0, s=-1))
    f = ClearLineOfSightFilter(blocked_by_units=True)
    assert f.apply(Hex(q=2, r=0, s=-2), los_state, {}) is False


def test_unit_on_intermediate_blocks_unit_target(los_state):
    """Unit on intermediate blocks targeting another unit behind it."""
    los_state.place_entity("minion_1", Hex(q=1, r=0, s=-1))
    los_state.place_entity("enemy_b", Hex(q=3, r=0, s=-3))
    f = ClearLineOfSightFilter()
    assert f.apply("enemy_b", los_state, {}) is False


def test_unit_on_intermediate_allowed_when_not_blocked(los_state):
    """blocked_by_units=False allows shooting over units."""
    los_state.place_entity("minion_1", Hex(q=1, r=0, s=-1))
    f = ClearLineOfSightFilter(blocked_by_units=False)
    assert f.apply(Hex(q=2, r=0, s=-2), los_state, {}) is True


# ---- Blocked by terrain ----


def test_terrain_on_intermediate_blocks(los_state):
    """Terrain on intermediate hex blocks the line (default)."""
    los_state.board.tiles[Hex(q=1, r=0, s=-1)].is_terrain = True
    f = ClearLineOfSightFilter(blocked_by_terrain=True)
    assert f.apply(Hex(q=2, r=0, s=-2), los_state, {}) is False


def test_terrain_on_intermediate_allowed_when_not_blocked(los_state):
    """blocked_by_terrain=False allows shooting over terrain."""
    los_state.board.tiles[Hex(q=1, r=0, s=-1)].is_terrain = True
    f = ClearLineOfSightFilter(blocked_by_terrain=False)
    assert f.apply(Hex(q=2, r=0, s=-2), los_state, {}) is True


# ---- Not in straight line ----


def test_not_in_straight_line_rejected(los_state):
    """Off-axis hex is not in straight line → rejected."""
    f = ClearLineOfSightFilter()
    assert f.apply(Hex(q=1, r=1, s=-2), los_state, {}) is False


# ---- Both blockers ----


def test_both_blockers_terrain_blocks(los_state):
    """With both flags on, terrain blocks."""
    los_state.board.tiles[Hex(q=2, r=0, s=-2)].is_terrain = True
    f = ClearLineOfSightFilter(blocked_by_units=True, blocked_by_terrain=True)
    assert f.apply(Hex(q=3, r=0, s=-3), los_state, {}) is False


def test_both_blockers_unit_blocks(los_state):
    """With both flags on, unit blocks."""
    los_state.place_entity("minion_1", Hex(q=2, r=0, s=-2))
    f = ClearLineOfSightFilter(blocked_by_units=True, blocked_by_terrain=True)
    assert f.apply(Hex(q=3, r=0, s=-3), los_state, {}) is False


def test_neither_blocker_both_present(los_state):
    """With both flags off, neither terrain nor units block."""
    los_state.board.tiles[Hex(q=1, r=0, s=-1)].is_terrain = True
    los_state.place_entity("minion_1", Hex(q=2, r=0, s=-2))
    f = ClearLineOfSightFilter(blocked_by_units=False, blocked_by_terrain=False)
    assert f.apply(Hex(q=3, r=0, s=-3), los_state, {}) is True


# ---- Origin resolution ----


def test_origin_from_context_key(los_state):
    """origin_key reads the origin ID from context."""
    los_state.place_entity("enemy_b", Hex(q=3, r=0, s=-3))
    f = ClearLineOfSightFilter(origin_key="shooter")
    ctx = {"shooter": "hero_a"}
    assert f.apply("enemy_b", los_state, ctx) is True


def test_origin_from_literal_id(los_state):
    """origin_id uses a literal ID."""
    los_state.place_entity("enemy_b", Hex(q=2, r=0, s=-2))
    f = ClearLineOfSightFilter(origin_id="hero_a")
    assert f.apply("enemy_b", los_state, {}) is True


def test_defaults_to_current_actor(los_state):
    """Without origin_id/origin_key, uses state.current_actor_id."""
    f = ClearLineOfSightFilter()
    assert f.apply(Hex(q=2, r=0, s=-2), los_state, {}) is True


# ---- Edge cases ----


def test_hex_not_on_board_blocks(los_state):
    """Intermediate hex missing from board → blocked."""
    # Remove intermediate hex from tiles
    del los_state.board.tiles[Hex(q=1, r=0, s=-1)]
    f = ClearLineOfSightFilter()
    assert f.apply(Hex(q=2, r=0, s=-2), los_state, {}) is False


def test_destination_occupant_does_not_block(los_state):
    """Unit on the destination hex itself is not a blocker."""
    los_state.place_entity("enemy_b", Hex(q=2, r=0, s=-2))
    f = ClearLineOfSightFilter()
    # Target the hex directly — enemy is on destination, not intermediate
    assert f.apply(Hex(q=2, r=0, s=-2), los_state, {}) is True


def test_destination_terrain_does_not_block(los_state):
    """Terrain on the destination hex itself is not checked."""
    los_state.board.tiles[Hex(q=2, r=0, s=-2)].is_terrain = True
    f = ClearLineOfSightFilter()
    assert f.apply(Hex(q=2, r=0, s=-2), los_state, {}) is True


def test_multiple_intermediates_first_blocks(los_state):
    """First intermediate blocks even if rest are clear."""
    los_state.place_entity("minion_1", Hex(q=1, r=0, s=-1))
    f = ClearLineOfSightFilter()
    assert f.apply(Hex(q=4, r=0, s=-4), los_state, {}) is False


def test_multiple_intermediates_second_blocks(los_state):
    """Second intermediate blocks."""
    los_state.place_entity("minion_1", Hex(q=2, r=0, s=-2))
    f = ClearLineOfSightFilter()
    assert f.apply(Hex(q=4, r=0, s=-4), los_state, {}) is False


# ---- Tokens don't block ----


def test_token_on_intermediate_does_not_block(los_state):
    """Tokens are not units — they don't block line of sight for blocked_by_units."""
    token = Token(id="token_1", name="Obstacle Token")
    los_state.register_entity(token)
    los_state.place_entity("token_1", Hex(q=1, r=0, s=-1))
    los_state.place_entity("enemy_b", Hex(q=2, r=0, s=-2))
    f = ClearLineOfSightFilter(blocked_by_units=True, blocked_by_terrain=False)
    assert f.apply("enemy_b", los_state, {}) is True


def test_unit_still_blocks_with_token_present(los_state):
    """Unit on intermediate still blocks even when token is elsewhere."""
    token = Token(id="token_1", name="Obstacle Token")
    los_state.register_entity(token)
    los_state.place_entity("token_1", Hex(q=1, r=0, s=-1))
    los_state.place_entity("minion_1", Hex(q=2, r=0, s=-2))
    los_state.place_entity("enemy_b", Hex(q=3, r=0, s=-3))
    f = ClearLineOfSightFilter(blocked_by_units=True, blocked_by_terrain=False)
    assert f.apply("enemy_b", los_state, {}) is False

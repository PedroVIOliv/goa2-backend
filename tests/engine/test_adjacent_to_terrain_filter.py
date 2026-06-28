"""Unit tests for AdjacentToTerrainFilter.

"Terrain" means an impassable terrain tile OR the off-map board edge: the board
edge counts as terrain, matching the canonical board convention (Board.get_tile
returns a virtual is_terrain=True tile for off-map hexes). A unit is "adjacent to
terrain" if any neighbour is on-map terrain or off the map.
"""

import pytest

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Hero, Team, TeamColor
from goa2.domain.state import GameState
from goa2.domain.tile import Tile
from goa2.engine.filters import AdjacentToTerrainFilter


def _radius2_hexes() -> list[Hex]:
    """All hexes within cube distance 2 of the origin (a radius-2 hex board)."""
    hexes = []
    for q in range(-2, 3):
        for r in range(-2, 3):
            s = -q - r
            if max(abs(q), abs(r), abs(s)) <= 2:
                hexes.append(Hex(q=q, r=r, s=s))
    return hexes


@pytest.fixture
def terrain_state():
    board = Board()
    for h in _radius2_hexes():
        board.tiles[h] = Tile(hex=h)

    board.zones["Mid"] = Zone(id="Mid", label="Mid", hexes=set(board.tiles.keys()))

    # h_interior at (0,0,0): all six neighbours are on-map, non-terrain -> interior.
    # h_edge at (2,0,-2): a radius-2 hex with off-map neighbours -> edge-adjacent.
    h_interior = Hero(id="h_interior", name="Interior", team=TeamColor.RED, deck=[])
    h_edge = Hero(id="h_edge", name="Edge", team=TeamColor.BLUE, deck=[])
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h_interior], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[h_edge], minions=[]),
        },
        entity_locations={},
        current_actor_id="h_interior",
        active_zone_id="Mid",
    )
    state.place_entity("h_interior", Hex(q=0, r=0, s=0))
    state.place_entity("h_edge", Hex(q=2, r=0, s=-2))
    return state


def test_adjacent_to_terrain_true_for_on_map_terrain_neighbour(terrain_state):
    # Make an on-map neighbour of the interior hero terrain.
    terrain_state.board.tiles[Hex(q=1, r=0, s=-1)].is_terrain = True
    f = AdjacentToTerrainFilter(is_adjacent=True)
    assert f.apply("h_interior", terrain_state, {}) is True


def test_board_edge_counts_as_terrain(terrain_state):
    # h_edge has off-map neighbours and no on-map terrain neighbour, yet it is
    # adjacent to terrain because the board edge IS terrain.
    f = AdjacentToTerrainFilter(is_adjacent=True)
    assert f.apply("h_edge", terrain_state, {}) is True


def test_fully_interior_hex_not_adjacent_to_terrain(terrain_state):
    # No terrain anywhere; the interior hero has all-on-map, non-terrain neighbours.
    assert AdjacentToTerrainFilter(is_adjacent=True).apply("h_interior", terrain_state, {}) is False
    assert AdjacentToTerrainFilter(is_adjacent=False).apply("h_interior", terrain_state, {}) is True

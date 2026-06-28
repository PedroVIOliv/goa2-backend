"""Unit tests for AdjacentToTerrainFilter (used by Swift's Suppress family).

Terrain means on-map impassable terrain tiles only. The off-map board edge
does NOT count as terrain for adjacency.
"""

import pytest

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Hero, Team, TeamColor
from goa2.domain.state import GameState
from goa2.domain.tile import Tile
from goa2.engine.filters import AdjacentToTerrainFilter


@pytest.fixture
def terrain_state():
    board = Board()
    hexes = [
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=2, r=0, s=-2),
        Hex(q=1, r=-1, s=0),
        Hex(q=0, r=1, s=-1),
        Hex(q=3, r=0, s=-3),
    ]
    for h in hexes:
        board.tiles[h] = Tile(hex=h)
    # (1,-1,0) is the only terrain tile; it neighbours (0,0,0) but not (2,0,-2).
    board.tiles[Hex(q=1, r=-1, s=0)].is_terrain = True

    board.zones["Mid"] = Zone(id="Mid", label="Mid", hexes=set(hexes))

    h_adj = Hero(id="h_adj", name="Adj", team=TeamColor.RED, deck=[])
    h_clear = Hero(id="h_clear", name="Clear", team=TeamColor.BLUE, deck=[])
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h_adj], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[h_clear], minions=[]),
        },
        entity_locations={},
        current_actor_id="h_adj",
        active_zone_id="Mid",
    )
    state.place_entity("h_adj", Hex(q=0, r=0, s=0))  # neighbour of terrain (1,-1,0)
    state.place_entity("h_clear", Hex(q=2, r=0, s=-2))  # no terrain neighbours
    return state


def test_adjacent_to_terrain_true_for_unit_next_to_terrain(terrain_state):
    f = AdjacentToTerrainFilter(is_adjacent=True)
    assert f.apply("h_adj", terrain_state, {}) is True
    assert f.apply("h_clear", terrain_state, {}) is False


def test_not_adjacent_to_terrain_passes_unit_away_from_terrain(terrain_state):
    f = AdjacentToTerrainFilter(is_adjacent=False)
    assert f.apply("h_clear", terrain_state, {}) is True
    assert f.apply("h_adj", terrain_state, {}) is False


def test_off_map_edge_does_not_count_as_terrain(terrain_state):
    # h_clear at (2,0,-2) has several off-map neighbours but no on-map terrain
    # neighbour, so it is NOT adjacent to terrain.
    f = AdjacentToTerrainFilter(is_adjacent=False)
    assert f.apply("h_clear", terrain_state, {}) is True

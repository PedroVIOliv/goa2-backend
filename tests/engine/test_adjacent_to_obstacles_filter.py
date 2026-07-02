"""Unit tests for AdjacentToObstaclesFilter (Brynn's signature primitive).

A candidate passes when >= min_count of its neighbouring hexes are obstacles
(terrain, board edge, or occupied by any unit/token) as reported by
``is_obstacle_for_actor``. Brynn's ultimate "Over the Top" overrides this: while
Brynn (the current actor, level >= 8 with over_the_top) acts, every enemy HERO
counts as adjacent to 3+ obstacles regardless of the real board — minions never.
"""

import pytest

from goa2.data.heroes.brynn import create_brynn
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Hero, Minion, MinionType, Team, TeamColor
from goa2.domain.state import GameState
from goa2.domain.tile import Tile
from goa2.engine.filters import AdjacentToObstaclesFilter


def _radius2_hexes() -> list[Hex]:
    hexes = []
    for q in range(-2, 3):
        for r in range(-2, 3):
            s = -q - r
            if max(abs(q), abs(r), abs(s)) <= 2:
                hexes.append(Hex(q=q, r=r, s=s))
    return hexes


@pytest.fixture
def board_state():
    board = Board()
    for h in _radius2_hexes():
        board.tiles[h] = Tile(hex=h)
    board.zones["Mid"] = Zone(id="Mid", label="Mid", hexes=set(board.tiles.keys()))

    brynn = Hero(id="hero_brynn", name="Brynn", team=TeamColor.RED, deck=[])
    target = Hero(id="enemy_hero", name="Target", team=TeamColor.BLUE, deck=[])
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[brynn], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[target], minions=[]),
        },
        entity_locations={},
        current_actor_id="hero_brynn",
        active_zone_id="Mid",
    )
    # Target interior (all six neighbours on-map, non-terrain, empty).
    state.place_entity("enemy_hero", Hex(q=0, r=0, s=0))
    # Brynn parked far away so she doesn't add an obstacle unless we move her.
    state.place_entity("hero_brynn", Hex(q=-2, r=0, s=2))
    return state


def test_three_terrain_neighbours_passes(board_state):
    for h in (Hex(q=1, r=0, s=-1), Hex(q=1, r=-1, s=0), Hex(q=0, r=-1, s=1)):
        board_state.board.tiles[h].is_terrain = True
    assert AdjacentToObstaclesFilter(min_count=3).apply("enemy_hero", board_state, {}) is True


def test_two_obstacles_fails_until_occupant_makes_three(board_state):
    # Two terrain neighbours only -> count == 2 -> fails.
    for h in (Hex(q=1, r=0, s=-1), Hex(q=1, r=-1, s=0)):
        board_state.board.tiles[h].is_terrain = True
    f = AdjacentToObstaclesFilter(min_count=3)
    assert f.apply("enemy_hero", board_state, {}) is False
    # Move Brynn onto a third neighbour: occupied hex is an obstacle -> count == 3.
    board_state.move_unit("hero_brynn", Hex(q=0, r=-1, s=1))
    assert f.apply("enemy_hero", board_state, {}) is True


def test_board_edge_neighbours_count(board_state):
    # Corner (2,0,-2) on a radius-2 board has three off-map (board-edge) neighbours.
    board_state.move_unit("enemy_hero", Hex(q=2, r=0, s=-2))
    assert AdjacentToObstaclesFilter(min_count=3).apply("enemy_hero", board_state, {}) is True


def test_ultimate_override_lets_open_enemy_hero_pass(board_state):
    brynn = create_brynn()
    brynn.level = 8
    board_state.teams[TeamColor.RED].heroes = [brynn]
    board_state.place_entity("hero_brynn", Hex(q=-2, r=0, s=2))  # re-register
    # Enemy hero is fully in the open (0 obstacle neighbours) but ult flips it.
    assert AdjacentToObstaclesFilter(min_count=3).apply("enemy_hero", board_state, {}) is True


def test_ultimate_override_does_not_apply_to_minion(board_state):
    brynn = create_brynn()
    brynn.level = 8
    board_state.teams[TeamColor.RED].heroes = [brynn]
    board_state.place_entity("hero_brynn", Hex(q=-2, r=0, s=2))
    minion = Minion(id="enemy_minion", name="M", team=TeamColor.BLUE, type=MinionType.MELEE)
    board_state.teams[TeamColor.BLUE].minions.append(minion)
    board_state.place_entity("enemy_minion", Hex(q=0, r=1, s=-1))
    assert AdjacentToObstaclesFilter(min_count=3).apply("enemy_minion", board_state, {}) is False


def test_ultimate_override_inactive_below_level_eight(board_state):
    brynn = create_brynn()
    brynn.level = 7  # ultimate not yet unlocked
    board_state.teams[TeamColor.RED].heroes = [brynn]
    board_state.place_entity("hero_brynn", Hex(q=-2, r=0, s=2))
    assert AdjacentToObstaclesFilter(min_count=3).apply("enemy_hero", board_state, {}) is False

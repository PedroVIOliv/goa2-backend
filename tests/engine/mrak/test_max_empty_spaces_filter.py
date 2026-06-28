"""MaxEmptySpacesInLineFilter: straight-line move budget of empty hexes (Mrak).

"Move any number of spaces in a straight line, ignoring obstacles, without
moving through more than N empty spaces." Only EMPTY interior hexes count toward
the budget; obstacles (terrain/units/tokens) passed through do not. Start and
destination hexes never count.
"""

from __future__ import annotations

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Hero, Minion, MinionType, Team, TeamColor
from goa2.domain.state import GameState
from goa2.domain.tile import Tile
from goa2.engine.filters import MaxEmptySpacesInLineFilter


def _state() -> GameState:
    board = Board()
    hexes = [Hex(q=q, r=0, s=-q) for q in range(6)]
    for h in hexes:
        board.tiles[h] = Tile(hex=h)
    board.zones["Mid"] = Zone(id="Mid", label="Mid", hexes=set(hexes))

    hero = Hero(id="h", name="H", team=TeamColor.RED, deck=[])
    blocker = Minion(id="blocker", name="B", team=TeamColor.RED, type=MinionType.MELEE)
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[blocker]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        current_actor_id="h",
        active_zone_id="Mid",
    )
    state.place_entity("h", Hex(q=0, r=0, s=0))
    return state


def test_clear_path_counts_each_empty_interior_hex() -> None:
    state = _state()
    dest = Hex(q=3, r=0, s=-3)  # interior: (1,0,-1), (2,0,-2) -> 2 empties
    assert MaxEmptySpacesInLineFilter(origin_id="h", max_empty=2).apply(dest, state, {}) is True
    assert MaxEmptySpacesInLineFilter(origin_id="h", max_empty=1).apply(dest, state, {}) is False


def test_terrain_in_path_does_not_consume_budget() -> None:
    state = _state()
    state.board.tiles[Hex(q=1, r=0, s=-1)].is_terrain = True  # obstacle, not empty
    dest = Hex(q=3, r=0, s=-3)  # interior empties now just (2,0,-2) -> 1
    assert MaxEmptySpacesInLineFilter(origin_id="h", max_empty=1).apply(dest, state, {}) is True


def test_occupied_interior_hex_does_not_consume_budget() -> None:
    state = _state()
    state.place_entity("blocker", Hex(q=2, r=0, s=-2))  # occupied, not empty
    dest = Hex(q=3, r=0, s=-3)  # interior empties now just (1,0,-1) -> 1
    assert MaxEmptySpacesInLineFilter(origin_id="h", max_empty=1).apply(dest, state, {}) is True

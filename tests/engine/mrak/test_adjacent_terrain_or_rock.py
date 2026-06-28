"""The shared 'adjacent to terrain, or a Rock token' targeting helper (Mrak)."""

from __future__ import annotations

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Minion, MinionType, Team, TeamColor, Token, TokenType
from goa2.domain.state import GameState
from goa2.domain.tile import Tile
from goa2.scripts.mrak_effects import _adjacent_to_terrain_or_rock


def _radius2_hexes() -> list[Hex]:
    hexes = []
    for q in range(-2, 3):
        for r in range(-2, 3):
            s = -q - r
            if max(abs(q), abs(r), abs(s)) <= 2:
                hexes.append(Hex(q=q, r=r, s=s))
    return hexes


def _state() -> GameState:
    board = Board()
    for h in _radius2_hexes():
        board.tiles[h] = Tile(hex=h)
    board.zones["Mid"] = Zone(id="Mid", label="Mid", hexes=set(board.tiles.keys()))

    near_terrain = Minion(id="m_terrain", name="T", team=TeamColor.RED, type=MinionType.MELEE)
    near_rock = Minion(id="m_rock", name="R", team=TeamColor.RED, type=MinionType.MELEE)
    interior = Minion(id="m_none", name="N", team=TeamColor.RED, type=MinionType.MELEE)
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(
                color=TeamColor.RED, heroes=[], minions=[near_terrain, near_rock, interior]
            ),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        active_zone_id="Mid",
    )
    # m_terrain at (1,0,-1) with an on-map terrain neighbour.
    state.place_entity("m_terrain", Hex(q=1, r=0, s=-1))
    state.board.tiles[Hex(q=2, r=0, s=-2)].is_terrain = True
    # m_rock at (-1,0,1) with an adjacent Rock token.
    state.place_entity("m_rock", Hex(q=-1, r=0, s=1))
    rock = Token(id="rock_1", name="Rock", token_type=TokenType.ROCK)
    state.register_entity(rock)
    state.place_entity("rock_1", Hex(q=-2, r=0, s=2))
    # m_none at the fully interior origin: no terrain, no rock adjacent.
    state.place_entity("m_none", Hex(q=0, r=0, s=0))
    return state


def test_unit_adjacent_to_terrain_passes() -> None:
    f = _adjacent_to_terrain_or_rock()
    assert f.apply("m_terrain", _state(), {}) is True


def test_unit_adjacent_to_rock_token_passes() -> None:
    f = _adjacent_to_terrain_or_rock()
    assert f.apply("m_rock", _state(), {}) is True


def test_interior_unit_adjacent_to_neither_fails() -> None:
    f = _adjacent_to_terrain_or_rock()
    assert f.apply("m_none", _state(), {}) is False

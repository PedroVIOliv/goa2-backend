"""FarthestEmptyAdjacentFilter batch-search hints.

The batch completability search cannot physically place tokens or perform
removals while it explores assignments, so it communicates its hypotheses
through context:

- ``occupied_hex_keys``: context keys whose hexes must be treated as occupied
  (hexes already chosen for earlier batch slots).
- ``BATCH_FREED_HEXES_KEY``: hexes to treat as empty (tokens whose removal is
  part of the hypothesis being tested).
"""

from __future__ import annotations

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Hero, Team, TeamColor, Token, TokenType
from goa2.domain.state import GameState
from goa2.domain.tile import Tile
from goa2.engine.filters_base import BATCH_FREED_HEXES_KEY
from goa2.engine.filters_geometry import FarthestEmptyAdjacentFilter

# Board: Mrak at (0,0,0); anchor enemy at (2,0,-2) with three on-map
# neighbours: (1,0,-1) at distance 1, (3,0,-3) and (2,1,-3) at distance 3.
_HEXES = [(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3), (2, 1, -3)]


def _state() -> GameState:
    board = Board()
    hexes = [Hex(q=q, r=r, s=s) for q, r, s in _HEXES]
    for h in hexes:
        board.tiles[h] = Tile(hex=h)
    board.zones["Mid"] = Zone(id="Mid", label="Mid", hexes=set(hexes))

    mrak = Hero(id="hero_mrak", name="Mrak", team=TeamColor.RED, deck=[])
    arien = Hero(id="hero_arien", name="Arien", team=TeamColor.BLUE, deck=[])
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[mrak], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[arien], minions=[]),
        },
    )
    state.place_entity("hero_mrak", Hex(q=0, r=0, s=0))
    state.place_entity("hero_arien", Hex(q=2, r=0, s=-2))
    return state


def _filter(**kwargs) -> FarthestEmptyAdjacentFilter:
    return FarthestEmptyAdjacentFilter(origin_id="hero_mrak", anchor_key="grip_hero", **kwargs)


def _ctx(**extra) -> dict:
    return {"grip_hero": "hero_arien", **extra}


def test_occupied_hex_keys_exclude_chosen_hexes() -> None:
    f = _filter(occupied_hex_keys=["slot_0"])
    ctx = _ctx(slot_0={"q": 3, "r": 0, "s": -3})
    state = _state()
    # The hex hypothetically taken by slot 0 is no longer a candidate...
    assert not f.apply(Hex(q=3, r=0, s=-3), state, ctx)
    # ...and the max is recomputed over what remains (the other distance-3 hex).
    assert f.apply(Hex(q=2, r=1, s=-3), state, ctx)
    # Without the key set, the hex is a normal farthest candidate.
    assert f.apply(Hex(q=3, r=0, s=-3), state, _ctx())


def test_batch_freed_hexes_count_as_empty() -> None:
    state = _state()
    rock = Token(id="rock_1", name="Rock", token_type=TokenType.ROCK)
    state.register_entity(rock)
    state.place_entity("rock_1", Hex(q=3, r=0, s=-3))

    f = _filter()
    # Live board: the rock hex is occupied and fails.
    assert not f.apply(Hex(q=3, r=0, s=-3), state, _ctx())
    # With the search's freed hint, it counts as empty (and ties for farthest).
    ctx = _ctx(**{BATCH_FREED_HEXES_KEY: [Hex(q=3, r=0, s=-3)]})
    assert f.apply(Hex(q=3, r=0, s=-3), state, ctx)
    assert f.apply(Hex(q=2, r=1, s=-3), state, ctx)


def test_freed_hex_can_raise_the_max() -> None:
    # Both distance-3 neighbours hold rocks; only (1,0,-1) is empty. Live: it
    # is trivially farthest. If the hypothesis frees a distance-3 hex, the max
    # rises and the near hex stops qualifying.
    state = _state()
    for i, at in enumerate([(3, 0, -3), (2, 1, -3)]):
        rock = Token(id=f"rock_{i}", name="Rock", token_type=TokenType.ROCK)
        state.register_entity(rock)
        state.place_entity(f"rock_{i}", Hex(q=at[0], r=at[1], s=at[2]))

    f = _filter()
    assert f.apply(Hex(q=1, r=0, s=-1), state, _ctx())
    ctx = _ctx(**{BATCH_FREED_HEXES_KEY: [Hex(q=3, r=0, s=-3)]})
    assert not f.apply(Hex(q=1, r=0, s=-1), state, ctx)
    assert f.apply(Hex(q=3, r=0, s=-3), state, ctx)
    # The still-occupied distance-3 hex is not freed and keeps failing.
    assert not f.apply(Hex(q=2, r=1, s=-3), state, ctx)

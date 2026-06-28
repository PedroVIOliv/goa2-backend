"""PlaceTokensInLineStep: scan a straight line and fill the first N empty hexes.

Used by Fissure. Obstacles in the line are skipped (not landed on); the scan
stops at the board edge, placing fewer tokens if it runs out of board first.
"""

from __future__ import annotations

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Hero, Team, TeamColor, Token, TokenType
from goa2.domain.state import GameState
from goa2.domain.tile import Tile
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import PlaceTokensInLineStep


def _state(length: int = 6) -> GameState:
    board = Board()
    hexes = [Hex(q=q, r=0, s=-q) for q in range(length)]
    for h in hexes:
        board.tiles[h] = Tile(hex=h)
    board.zones["Mid"] = Zone(id="Mid", label="Mid", hexes=set(hexes))

    hero = Hero(id="hero_mrak", name="Mrak", team=TeamColor.RED, deck=[])
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        current_actor_id="hero_mrak",
        active_zone_id="Mid",
    )
    state.place_entity("hero_mrak", Hex(q=0, r=0, s=0))
    state.token_pool[TokenType.ROCK] = []
    for i in range(3):
        rock = Token(id=f"rock_{i}", name="Rock", token_type=TokenType.ROCK)
        state.register_entity(rock)
        state.token_pool[TokenType.ROCK].append(rock)
    return state


def _rock_at(state, q, r, s) -> bool:
    target = Hex(q=q, r=r, s=s)
    return any(
        state.entity_locations.get(str(t.id)) == target for t in state.token_pool[TokenType.ROCK]
    )


def _run(state) -> None:
    state.execution_context["dir_ref"] = Hex(q=1, r=0, s=-1).model_dump()
    push_steps(
        state,
        [PlaceTokensInLineStep(token_type=TokenType.ROCK, direction_ref_key="dir_ref", count=3)],
    )
    process_stack(state)


def test_places_three_rocks_in_consecutive_empty_hexes() -> None:
    state = _state(length=6)
    _run(state)
    assert _rock_at(state, 1, 0, -1)
    assert _rock_at(state, 2, 0, -2)
    assert _rock_at(state, 3, 0, -3)


def test_skips_obstacles_in_the_line() -> None:
    state = _state(length=6)
    state.board.tiles[Hex(q=2, r=0, s=-2)].is_terrain = True  # obstacle, skipped
    _run(state)
    assert _rock_at(state, 1, 0, -1)
    assert not _rock_at(state, 2, 0, -2)  # terrain skipped, no rock here
    assert _rock_at(state, 3, 0, -3)
    assert _rock_at(state, 4, 0, -4)


def test_places_fewer_when_board_edge_reached_first() -> None:
    state = _state(length=3)  # hexes q=0,1,2 only
    _run(state)
    assert _rock_at(state, 1, 0, -1)
    assert _rock_at(state, 2, 0, -2)
    # Only two empty hexes exist before the board edge -> only two rocks placed.
    placed = sum(
        1
        for t in state.token_pool[TokenType.ROCK]
        if state.entity_locations.get(str(t.id)) is not None
    )
    assert placed == 2

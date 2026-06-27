"""MoveSequenceStep.allow_straight_line_through_obstacles (Wuk Trample)."""

from __future__ import annotations

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Hero, Team, TeamColor
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.engine.steps.movement import MoveSequenceStep

FAR = Hex(q=4, r=0, s=-4)
NEAR = Hex(q=1, r=0, s=-1)
OBSTACLE = Hex(q=2, r=0, s=-2)


def _state() -> GameState:
    board = Board()
    board.zones = {"z": Zone(id="z", hexes={Hex(q=q, r=0, s=-q) for q in range(5)})}
    board.populate_tiles_from_zones()
    board.tiles[OBSTACLE].is_terrain = True  # blocks normal pathing past q=1
    hero = Hero(id=HeroID("hero_x"), name="X", team=TeamColor.RED, deck=[], level=1)
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        current_actor_id="hero_x",
    )
    state.place_entity("hero_x", Hex(q=0, r=0, s=0))
    return state


def _dest_filters(allow_sl_through: bool):
    state = _state()
    step = MoveSequenceStep(
        unit_id="hero_x",
        range_val=4,
        allow_straight_line_through_obstacles=allow_sl_through,
    )
    select = step.resolve(state, {}).new_steps[0]
    return state, select.filters


def _reachable(state, filters, target: Hex) -> bool:
    return all(f.apply(target, state, {}) for f in filters)


def test_far_hex_blocked_without_flag() -> None:
    state, filters = _dest_filters(allow_sl_through=False)
    assert _reachable(state, filters, FAR) is False
    # near hex still reachable normally
    assert _reachable(state, filters, NEAR) is True


def test_far_hex_reachable_with_flag() -> None:
    state, filters = _dest_filters(allow_sl_through=True)
    assert _reachable(state, filters, FAR) is True
    # normal near hex still offered too
    assert _reachable(state, filters, NEAR) is True

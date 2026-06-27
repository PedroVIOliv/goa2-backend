"""CollectUnitsStep gathers all units matching filters (no player choice)."""

from __future__ import annotations

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Hero, Minion, MinionType, Team, TeamColor
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.engine.filters_units import TeamFilter, UnitTypeFilter
from goa2.engine.steps import CollectUnitsStep


def _state() -> GameState:
    board = Board()
    board.zones = {"z": Zone(id="z", hexes={Hex(q=q, r=0, s=-q) for q in range(5)})}
    board.populate_tiles_from_zones()
    actor = Hero(id=HeroID("hero_x"), name="X", team=TeamColor.RED, deck=[])
    eh1 = Hero(id=HeroID("eh1"), name="E1", team=TeamColor.BLUE, deck=[])
    eh2 = Hero(id=HeroID("eh2"), name="E2", team=TeamColor.BLUE, deck=[])
    em = Minion(id="em", name="EM", team=TeamColor.BLUE, type=MinionType.MELEE)
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[actor], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[eh1, eh2], minions=[em]),
        },
        current_actor_id="hero_x",
    )
    state.place_entity("hero_x", Hex(q=0, r=0, s=0))
    state.place_entity("eh1", Hex(q=1, r=0, s=-1))
    state.place_entity("eh2", Hex(q=2, r=0, s=-2))
    state.place_entity("em", Hex(q=3, r=0, s=-3))
    return state


def test_collect_units_gathers_all_matching_enemy_heroes() -> None:
    state = _state()
    ctx: dict = {}
    step = CollectUnitsStep(
        filters=[TeamFilter(relation="ENEMY"), UnitTypeFilter(unit_type="HERO")],
        output_key="collected",
    )
    result = step.resolve(state, ctx)

    assert result.is_finished
    assert set(ctx["collected"]) == {"eh1", "eh2"}

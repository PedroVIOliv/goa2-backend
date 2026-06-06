"""Regression (M9): the after-movement charm/control/dominate destination must
compute movement reachability for the after-selected minion, not fall back to
Xargatha. The destination filter's MovementPathFilter must key off
'charmed_minion_after', not 'charmed_minion'."""

import pytest

import goa2.scripts.xargatha_effects  # noqa: F401 - register effects
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardTier,
    Hero,
    Team,
    TeamColor,
)
from goa2.domain.state import GameState
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.filters_hex import MovementPathFilter
from goa2.engine.stats import compute_card_stats
from goa2.engine.steps.selection import SelectStep


@pytest.fixture
def xargatha_state():
    board = Board()
    z = Zone(id="z1", hexes={Hex(q=0, r=0, s=0)}, neighbors=[])
    board.zones = {"z1": z}
    board.populate_tiles_from_zones()
    hero = Hero(id="xargatha", name="Xargatha", team=TeamColor.RED, deck=[], level=1)
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
    )
    state.place_entity("xargatha", Hex(q=0, r=0, s=0))
    state.current_actor_id = "xargatha"
    return state


def _make_card(effect_id: str) -> Card:
    return Card(
        id=effect_id,
        name=effect_id,
        tier=CardTier.II,
        color=CardColor.RED,
        initiative=9,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=3,
        radius_value=4,
        effect_id=effect_id,
        effect_text="t",
        is_facedown=False,
    )


@pytest.mark.parametrize("effect_id", ["charm", "control", "dominate"])
def test_after_move_destination_paths_from_the_after_minion(xargatha_state, effect_id):
    hero = xargatha_state.get_hero("xargatha")
    card = _make_card(effect_id)
    effect = CardEffectRegistry.get(effect_id)
    stats = compute_card_stats(xargatha_state, hero.id, card)
    steps = effect.build_steps(xargatha_state, hero, card, stats)

    after_dest = next(
        s for s in steps if isinstance(s, SelectStep) and s.output_key == "charm_dest_after"
    )
    path_filters = [f for f in after_dest.filters if isinstance(f, MovementPathFilter)]
    assert path_filters, f"{effect_id} after-destination has no MovementPathFilter"
    for pf in path_filters:
        assert pf.unit_key == "charmed_minion_after", (
            f"{effect_id} after-move destination must path from the after-selected minion, "
            f"not '{pf.unit_key}' (falls back to Xargatha when empty)"
        )

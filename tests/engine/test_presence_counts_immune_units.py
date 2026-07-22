"""Audit §1.4: immune units count for presence conditions but stay untargetable.

An immune unit (a heavy minion with friendly support in the Battle Zone) still
satisfies "a space adjacent to an enemy unit" — the charge-and-attack family may
land next to it. It remains excluded from target selection.
"""

import pytest

import goa2.scripts.brogan_effects  # noqa: F401 — registers effects
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardTier,
    Hero,
    Minion,
    MinionType,
    Team,
    TeamColor,
)
from goa2.domain.state import GameState
from goa2.engine import rules
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.handler import process_stack, push_steps


def _mad_dash_card():
    return Card(
        id="mad_dash",
        name="Mad Dash",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=4,
        range_value=1,
        effect_id="mad_dash",
        effect_text="Move 2 spaces in a straight line to a space adjacent to an enemy unit.",
        is_facedown=False,
    )


@pytest.fixture
def dash_state():
    """Brogan at (0,0,0); the only reachable enemy is an immune heavy minion.

    Layout on the q axis: brogan(0) . (1) dest(2) heavy(3) support(4)
    """
    board = Board()
    hexes = {Hex(q=q, r=0, s=-q) for q in range(6)}
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    brogan = Hero(id="brogan", name="Brogan", team=TeamColor.RED, deck=[], level=1)
    brogan.current_turn_card = _mad_dash_card()
    heavy = Minion(id="m_heavy", name="Heavy", type=MinionType.HEAVY, team=TeamColor.BLUE)
    support = Minion(id="m_supp", name="Support", type=MinionType.MELEE, team=TeamColor.BLUE)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[brogan], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[heavy, support]),
        },
        current_actor_id="brogan",
        active_zone_id="z1",
    )
    state.place_entity("brogan", Hex(q=0, r=0, s=0))
    state.place_entity("m_heavy", Hex(q=3, r=0, s=-3))
    state.place_entity("m_supp", Hex(q=4, r=0, s=-4))
    return state


def test_the_heavy_minion_is_immune(dash_state):
    assert rules.is_immune(dash_state.get_unit("m_heavy"), dash_state)


def test_charge_may_land_adjacent_to_an_immune_enemy(dash_state):
    """Audit §1.4: the immune heavy still satisfies "adjacent to an enemy unit"."""
    effect = CardEffectRegistry.get("mad_dash")
    brogan = dash_state.get_hero("brogan")
    steps = effect.get_steps(dash_state, brogan, brogan.current_turn_card)
    push_steps(dash_state, steps)

    req = process_stack(dash_state).input_request

    assert req is not None
    assert req["type"] == "SELECT_HEX"
    assert Hex(q=2, r=0, s=-2).model_dump() in req["valid_options"]


def test_the_immune_enemy_still_cannot_be_targeted(dash_state):
    """...but it is not offered as an attack target once Brogan lands."""
    effect = CardEffectRegistry.get("mad_dash")
    brogan = dash_state.get_hero("brogan")
    push_steps(dash_state, effect.get_steps(dash_state, brogan, brogan.current_turn_card))

    req = process_stack(dash_state).input_request
    assert req is not None
    dash_state.execution_stack[-1].pending_input = {"selection": Hex(q=2, r=0, s=-2).model_dump()}

    req = process_stack(dash_state).input_request

    assert dash_state.get_position("brogan") == Hex(q=2, r=0, s=-2)
    # No legal attack target: the only adjacent enemy is immune.
    assert req is None or "m_heavy" not in req.get("candidates", [])

import pytest
from goa2.domain.models import (
    Hero,
    Card,
    CardTier,
    CardColor,
    ActionType,
    Minion,
    MinionType,
    Team,
    TeamColor,
)
from goa2.domain.types import HeroID, UnitID
from goa2.domain.state import GameState
from goa2.domain.hex import Hex
from goa2.domain.board import Board
from goa2.engine.steps import SelectStep, SwapUnitsStep, CheckAdjacencyStep, StepResult
from goa2.scripts.arien_effects import EbbAndFlowEffect


@pytest.fixture
def empty_state():
    return GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        current_actor_id="hero_arien",
    )


def test_ebb_and_flow_distant(empty_state: GameState):
    state = empty_state
    arien_id = "hero_arien"
    minion_id = "minion_distant"

    # Setup Entities
    arien = Hero(id=HeroID(arien_id), name="Arien", deck=[], team=TeamColor.RED)
    minion = Minion(
        id=UnitID(minion_id), name="Minion", type=MinionType.MELEE, team=TeamColor.BLUE
    )

    state.teams[TeamColor.RED].heroes.append(arien)
    state.teams[TeamColor.BLUE].minions.append(minion)

    # Positions: Distance 2
    state.entity_locations[UnitID(arien_id)] = Hex(q=0, r=0, s=0)
    state.entity_locations[UnitID(minion_id)] = Hex(q=2, r=-2, s=0)
    state.rebuild_occupancy_cache()

    card = Card(
        id="ebb_and_flow",
        name="Ebb and Flow",
        tier=CardTier.III,
        color=CardColor.GREEN,
        initiative=3,
        primary_action=ActionType.SKILL,
        effect_id="ebb_and_flow",
        effect_text="...",
        range_value=4,
        is_facedown=False,
    )

    effect = EbbAndFlowEffect()
    steps = effect.get_steps(state, arien, card)

    # Mock Selection of Minion 1
    state.execution_context["swap_target_1"] = minion_id

    # Run CheckAdjacencyStep
    check_step = next(s for s in steps if isinstance(s, CheckAdjacencyStep))
    check_step.resolve(state, state.execution_context)

    # Check MayRepeatOnceStep
    from goa2.engine.steps import MayRepeatOnceStep

    repeat_step = next(s for s in steps if isinstance(s, MayRepeatOnceStep))

    # It should be active (can_repeat=True)
    res = repeat_step.resolve(state, state.execution_context)
    assert res.requires_input is True
    assert res.input_request["type"] == "SELECT_OPTION"


def test_ebb_and_flow_adjacent(empty_state: GameState):
    state = empty_state
    arien_id = "hero_arien"
    minion_id = "minion_adj"

    # Setup Entities
    arien = Hero(id=HeroID(arien_id), name="Arien", deck=[], team=TeamColor.RED)
    minion = Minion(
        id=UnitID(minion_id), name="Minion", type=MinionType.MELEE, team=TeamColor.BLUE
    )

    state.teams[TeamColor.RED].heroes.append(arien)
    state.teams[TeamColor.BLUE].minions.append(minion)

    # Positions: Adjacent
    state.entity_locations[UnitID(arien_id)] = Hex(q=0, r=0, s=0)
    state.entity_locations[UnitID(minion_id)] = Hex(q=1, r=-1, s=0)
    state.rebuild_occupancy_cache()

    card = Card(
        id="ebb_and_flow",
        name="Ebb and Flow",
        tier=CardTier.III,
        color=CardColor.GREEN,
        initiative=3,
        primary_action=ActionType.SKILL,
        effect_id="ebb_and_flow",
        effect_text="...",
        range_value=4,
        is_facedown=False,
    )

    effect = EbbAndFlowEffect()
    steps = effect.get_steps(state, arien, card)

    # Mock Selection of Minion 1
    state.execution_context["swap_target_1"] = minion_id

    # Run CheckAdjacencyStep
    check_step = next(s for s in steps if isinstance(s, CheckAdjacencyStep))
    check_step.resolve(state, state.execution_context)

    # Run MayRepeatOnceStep
    from goa2.engine.steps import MayRepeatOnceStep

    repeat_step = next(s for s in steps if isinstance(s, MayRepeatOnceStep))

    # It should be active (can_repeat=True)
    res = repeat_step.resolve(state, state.execution_context)
    assert res.requires_input is True
    assert res.input_request["type"] == "SELECT_OPTION"

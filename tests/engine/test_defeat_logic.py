import pytest

from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import Hero, Minion, MinionType, Team, TeamColor
from goa2.domain.state import GameState
from goa2.domain.types import HeroID, UnitID
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import DefeatUnitStep, ForceDiscardOrDefeatStep, RemoveUnitStep


def create_hero(id_str, team):
    hero = Hero(id=HeroID(id_str), name=id_str, team=team, deck=[])
    hero.gold = 0
    return hero


def create_minion(id_str, team, m_type):
    return Minion(id=UnitID(id_str), name=id_str, team=team, type=m_type)


@pytest.fixture
def combat_state():
    hero_killer = create_hero("Killer", TeamColor.RED)
    minion_victim = create_minion("MinionV", TeamColor.BLUE, MinionType.MELEE)
    hero_victim = create_hero("HeroV", TeamColor.BLUE)
    hero_victim.level = 3  # Worth 3 gold

    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero_killer], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[hero_victim], minions=[minion_victim]
            ),
        },
    )
    # Place units
    # but move_unit expects Hex objects usually or steps handle conversion.
    # Here we are testing Steps which do NOT use move_unit for 'remove'.
    # But state.remove_unit needs unit_locations entry.
    state.move_unit(hero_killer.id, Hex(q=0, r=0, s=0))
    state.move_unit(minion_victim.id, Hex(q=1, r=0, s=-1))
    state.move_unit(hero_victim.id, Hex(q=2, r=0, s=-2))

    return state, hero_killer, minion_victim, hero_victim


def test_defeat_minion_rewards(combat_state):
    state, killer, minion, _ = combat_state

    # Minion Melee value is 2
    step = DefeatUnitStep(victim_id=minion.id, killer_id=killer.id)
    push_steps(state, [step])

    _ = process_stack(state).input_request

    # 1. Check Gold
    assert killer.gold == 2

    # 2. Check Removal
    assert minion.id not in state.unit_locations


def test_defeat_heavy_minion_rewards(combat_state):
    state, killer, _, _ = combat_state
    heavy = create_minion("HeavyV", TeamColor.BLUE, MinionType.HEAVY)
    state.teams[TeamColor.BLUE].minions.append(heavy)
    state.move_unit(heavy.id, Hex(q=5, r=0, s=-5))

    # Heavy value is 4
    step = DefeatUnitStep(victim_id=heavy.id, killer_id=killer.id)
    push_steps(state, [step])

    _ = process_stack(state).input_request

    assert killer.gold == 4
    assert heavy.id not in state.unit_locations


def test_defeat_hero_rewards(combat_state):
    state, killer, _, hero_v = combat_state

    # Hero Level 3 -> Reward 3
    step = DefeatUnitStep(victim_id=hero_v.id, killer_id=killer.id)
    push_steps(state, [step])

    _ = process_stack(state).input_request

    # 1. Check Gold
    assert killer.gold == 3

    # 2. Check Removal
    assert hero_v.id not in state.unit_locations


def test_remove_unit_no_rewards(combat_state):
    state, killer, minion, _ = combat_state

    # Direct RemoveUnitStep (e.g. from a "Remove" card effect)
    step = RemoveUnitStep(unit_id=minion.id)
    push_steps(state, [step])

    _ = process_stack(state).input_request

    # 1. Check Gold (Should be 0)
    assert killer.gold == 0

    # 2. Check Removal
    assert minion.id not in state.unit_locations


def test_force_discard_or_defeat_credits_acting_hero(combat_state):
    """A 'discard or be defeated' kill credits the acting hero (current actor).

    Every caller of ForceDiscardOrDefeatStep runs during the actor's own action
    chain, so current_actor_id is the source hero who should get the bounty.
    """
    state, killer, _, hero_v = combat_state
    hero_v.hand = []  # no cards -> must be defeated
    state.current_actor_id = killer.id

    state.execution_context["v"] = str(hero_v.id)
    push_steps(state, [ForceDiscardOrDefeatStep(victim_key="v")])

    result = process_stack(state)
    while state.execution_stack and result.input_request is None:
        result = process_stack(state)

    assert hero_v.id not in state.unit_locations
    # Level-3 victim -> 3 gold to the acting hero.
    assert killer.gold == 3
    defeated = [e for e in result.events if e.event_type.value == "UNIT_DEFEATED"]
    assert defeated and defeated[-1].actor_id == str(killer.id)


def test_force_discard_or_defeat_killer_override(combat_state):
    """killer_id overrides the current-actor default for callers where the
    acting hero is not the source (e.g. an effect firing on the victim's turn)."""
    state, killer, _, hero_v = combat_state
    hero_v.hand = []
    # Victim is the current actor (as it would be for a disruptor-style trigger),
    # but the kill should still be credited to the overridden source hero.
    state.current_actor_id = hero_v.id

    state.execution_context["v"] = str(hero_v.id)
    push_steps(state, [ForceDiscardOrDefeatStep(victim_key="v", killer_id=str(killer.id))])

    result = process_stack(state)
    while state.execution_stack and result.input_request is None:
        result = process_stack(state)

    assert hero_v.id not in state.unit_locations
    assert killer.gold == 3
    assert hero_v.gold == 0  # the victim/current-actor is not credited


def test_defeat_without_killer_awards_no_gold(combat_state):
    """`killer_id=None` deliberately credits no one — gold needs an explicit killer.

    This pins the contract so nobody "fixes" the default to silently use
    current_actor_id: that would mis-credit effects (e.g. Trinkets' disruptor)
    where the current actor is the *victim*, not the source. Effects that defeat
    a unit must pass killer_id explicitly to award the kill.
    """
    state, killer, minion, _ = combat_state

    step = DefeatUnitStep(victim_id=minion.id)  # no killer_id
    push_steps(state, [step])

    _ = process_stack(state).input_request

    assert killer.gold == 0
    assert minion.id not in state.unit_locations


def test_defeat_unknown_unit_raises_error():
    state = GameState(board=Board(), teams={})

    # "Ghost" unit not in any team
    step = DefeatUnitStep(victim_id="ghost_unit")
    push_steps(state, [step])

    with pytest.raises(ValueError, match="Cannot defeat unknown unit: ghost_unit"):
        _ = process_stack(state).input_request

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, Minion, MinionType, Hero
from goa2.domain.types import HeroID, UnitID
from goa2.domain.hex import Hex
from goa2.engine.steps import DefeatUnitStep, RemoveUnitStep
from goa2.engine.handler import process_resolution_stack, push_steps

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
    hero_victim.level = 3 # Worth 3 gold
    
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero_killer], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[hero_victim], minions=[minion_victim])
        }
    )
    # Place units
    # but move_unit expects Hex objects usually or steps handle conversion.
    # Here we are testing Steps which do NOT use move_unit for 'remove'.
    # But state.remove_unit needs unit_locations entry.
    state.move_unit(hero_killer.id, Hex(q=0,r=0,s=0))
    state.move_unit(minion_victim.id, Hex(q=1,r=0,s=-1))
    state.move_unit(hero_victim.id, Hex(q=2,r=0,s=-2))
    
    return state, hero_killer, minion_victim, hero_victim

def test_defeat_minion_rewards(combat_state):
    state, killer, minion, _ = combat_state
    
    # Minion Melee value is 2
    step = DefeatUnitStep(victim_id=minion.id, killer_id=killer.id)
    push_steps(state, [step])
    
    process_resolution_stack(state)
    
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
    
    process_resolution_stack(state)
    
    assert killer.gold == 4
    assert heavy.id not in state.unit_locations

def test_defeat_hero_rewards(combat_state):
    state, killer, _, hero_v = combat_state
    
    # Hero Level 3 -> Reward 3
    step = DefeatUnitStep(victim_id=hero_v.id, killer_id=killer.id)
    push_steps(state, [step])
    
    process_resolution_stack(state)
    
    # 1. Check Gold
    assert killer.gold == 3
    
    # 2. Check Removal
    assert hero_v.id not in state.unit_locations

def test_remove_unit_no_rewards(combat_state):
    state, killer, minion, _ = combat_state
    
    # Direct RemoveUnitStep (e.g. from a "Remove" card effect)
    step = RemoveUnitStep(unit_id=minion.id)
    push_steps(state, [step])
    
    process_resolution_stack(state)
    
    # 1. Check Gold (Should be 0)
    assert killer.gold == 0
    
    # 2. Check Removal
    assert minion.id not in state.unit_locations

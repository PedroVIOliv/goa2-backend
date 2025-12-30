import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, Hero
from goa2.domain.types import HeroID
from goa2.engine.steps import DefeatUnitStep
from goa2.engine.handler import process_resolution_stack, push_steps

def create_hero(id_str, team, level=1):
    hero = Hero(id=HeroID(id_str), name=id_str, team=team, deck=[])
    hero.level = level
    hero.gold = 0
    return hero

@pytest.fixture
def death_state():
    # Team Red: Killer, Ally
    killer = create_hero("Killer", TeamColor.RED, level=1)
    ally = create_hero("Ally", TeamColor.RED, level=1)
    
    # Team Blue: Victim
    victim = create_hero("Victim", TeamColor.BLUE, level=1)
    
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[killer, ally], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[victim], minions=[], life_counters=5)
        }
    )
    # Unit locations needed for removal check, but Defeat step looks up via get_unit which iterates teams.
    # But RemoveUnitStep needs unit_locations entry to clear board.
    from goa2.domain.hex import Hex
    state.move_unit(victim.id, Hex(q=0,r=0,s=0))
    
    return state, killer, ally, victim

def test_hero_death_level_1_rewards(death_state):
    state, killer, ally, victim = death_state
    
    # Victim Level 1 (Default)
    # Killer Reward: 1
    # Assist Reward: 1
    # Death Penalty: 1
    
    step = DefeatUnitStep(victim_id=victim.id, killer_id=killer.id)
    push_steps(state, [step])
    process_resolution_stack(state)
    
    assert killer.gold == 1
    assert ally.gold == 1
    assert state.teams[TeamColor.BLUE].life_counters == 4 # 5 - 1

def test_hero_death_level_4_rewards(death_state):
    state, killer, ally, victim = death_state
    
    # Set Victim Level 4
    victim.level = 4
    
    # Killer Reward: 4
    # Assist Reward: 2
    # Death Penalty: 2
    
    step = DefeatUnitStep(victim_id=victim.id, killer_id=killer.id)
    push_steps(state, [step])
    process_resolution_stack(state)
    
    assert killer.gold == 4
    assert ally.gold == 2
    assert state.teams[TeamColor.BLUE].life_counters == 3 # 5 - 2

def test_annihilation_trigger(death_state):
    state, killer, _, victim = death_state
    
    # Set Life to 1
    state.teams[TeamColor.BLUE].life_counters = 1
    
    step = DefeatUnitStep(victim_id=victim.id, killer_id=killer.id)
    push_steps(state, [step])
    process_resolution_stack(state)
    
    assert state.teams[TeamColor.BLUE].life_counters == 0
    # Ideally we check for Game Over flag, but currently it's a print.
    # Just verifying counter drops correctly to 0 is enough for this Step unit test.

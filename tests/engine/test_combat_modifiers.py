import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, Minion, MinionType, Hero, ActionType
from goa2.domain.types import HeroID, UnitID
from goa2.engine.steps import ResolveCombatStep, DefeatUnitStep
from goa2.engine.handler import process_resolution_stack, push_steps

def create_hero(id_str, team):
    return Hero(id=HeroID(id_str), name=id_str, team=team, deck=[])

def create_minion(id_str, team, m_type):
    return Minion(id=UnitID(id_str), name=id_str, team=team, type=m_type)

from goa2.domain.tile import Tile

@pytest.fixture
def aura_state():
    hero_v = create_hero("Victim", TeamColor.BLUE)
    
    board = Board()
    # Pre-populate tiles used in tests:
    # 0,0,0 (Victim)
    # 1,-1,0 (Minion R1)
    # 2,-2,0 (Minion R2)
    hexes = [Hex(q=0,r=0,s=0), Hex(q=1,r=-1,s=0), Hex(q=2,r=-2,s=0)]
    for h in hexes:
        board.tiles[h] = Tile(hex=h)
        
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[hero_v], minions=[])
        },
        unit_locations={}
    )
    return state, hero_v

def test_combat_friendly_aura_save(aura_state):
    """
    Attack 4 vs Def 3.
    Normally Hit.
    But Friendly Minion (+1) makes it 4. Blocked.
    """
    state, victim = aura_state
    
    # Setup: Victim at 0,0,0
    state.move_unit(victim.id, Hex(q=0,r=0,s=0))
    
    # Add Friendly Minion at 1, -1, 0 (Adj)
    friend = create_minion("Friend", TeamColor.BLUE, MinionType.MELEE)
    state.teams[TeamColor.BLUE].minions.append(friend)
    state.move_unit(friend.id, Hex(q=1,r=-1,s=0))
    
    # Context
    state.execution_context["victim_id"] = victim.id
    state.execution_context["defense_value"] = 3
    
    # Step
    step = ResolveCombatStep(damage=4, target_key="victim_id")
    push_steps(state, [step])
    
    process_resolution_stack(state)
    
    # Check: Victim should be alive (Blocked)
    assert victim.id in state.unit_locations

def test_combat_enemy_debuff_kill(aura_state):
    """
    Attack 4 vs Def 4.
    Normally Blocked.
    But Enemy Minion (-1) makes it 3. Hit.
    """
    state, victim = aura_state
    
    # Setup: Victim at 0,0,0
    state.move_unit(victim.id, Hex(q=0,r=0,s=0))
    
    # Add Enemy Minion at 1, -1, 0 (Adj)
    enemy = create_minion("Enemy", TeamColor.RED, MinionType.MELEE)
    state.teams[TeamColor.RED].minions.append(enemy)
    state.move_unit(enemy.id, Hex(q=1,r=-1,s=0))
    
    # Context
    state.execution_context["victim_id"] = victim.id
    state.execution_context["defense_value"] = 4
    
    # Step
    step = ResolveCombatStep(damage=4, target_key="victim_id")
    push_steps(state, [step])
    
    process_resolution_stack(state)
    
    # Check: Victim should be dead (Hit -> Defeat -> Remove)
    assert victim.id not in state.unit_locations

def test_combat_ranged_debuff(aura_state):
    """
    Attack 4 vs Def 4.
    Enemy Ranged Minion at Dist 2 (-1).
    Result: 3 vs 4 -> Hit.
    """
    state, victim = aura_state
    state.move_unit(victim.id, Hex(q=0,r=0,s=0))
    
    # Enemy Ranged at 2, -2, 0 (Dist 2)
    enemy = create_minion("Sniper", TeamColor.RED, MinionType.RANGED)
    state.teams[TeamColor.RED].minions.append(enemy)
    state.move_unit(enemy.id, Hex(q=2,r=-2,s=0))
    
    state.execution_context["victim_id"] = victim.id
    state.execution_context["defense_value"] = 4
    
    step = ResolveCombatStep(damage=4, target_key="victim_id")
    push_steps(state, [step])
    process_resolution_stack(state)
    
    assert victim.id not in state.unit_locations

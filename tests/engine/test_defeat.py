import pytest
from goa2.domain.state import GameState
from goa2.domain.models import Hero, Minion, MinionType, Team, TeamColor, Card, CardTier, CardColor, ActionType, CardState
from goa2.domain.types import HeroID, UnitID, CardID
from goa2.domain.board import Board, Hex, Zone
from goa2.engine.defeat import defeat_unit, calculate_life_loss

@pytest.fixture
def defeat_state():
    board = Board(
        zones={"z1": Zone(id="z1", hexes={Hex(q=0,r=0,s=0), Hex(q=1,r=0,s=-1)})}
    )
    state = GameState(board=board, teams={})
    return state

def test_calculate_life_loss():
    assert calculate_life_loss(1) == 1
    assert calculate_life_loss(3) == 1
    assert calculate_life_loss(4) == 2
    assert calculate_life_loss(6) == 2
    assert calculate_life_loss(7) == 3
    assert calculate_life_loss(8) == 3

def test_minion_defeat(defeat_state):
    state = defeat_state
    
    # Heroes
    killer_id = HeroID("killer")
    killer = Hero(id=killer_id, name="Killer", deck=[], team=TeamColor.RED, gold=0)
    
    # Minion
    minion_id = UnitID("m1")
    minion = Minion(id=minion_id, name="M1", type=MinionType.MELEE, team=TeamColor.BLUE) # Value 2
    
    state.teams[TeamColor.RED] = Team(color=TeamColor.RED, heroes=[killer])
    state.teams[TeamColor.BLUE] = Team(color=TeamColor.BLUE, minions=[minion])
    
    state.move_unit(minion_id, Hex(q=0,r=0,s=0))
    state.move_unit(killer_id, Hex(q=1,r=0,s=-1))
    
    # Execute Defeat
    defeat_unit(state, minion_id, killer_id=killer_id)
    
    # 1. Minion Removed
    assert minion_id not in state.unit_locations
    assert minion_id not in [m.id for m in state.teams[TeamColor.BLUE].minions]
    
    # 2. Coins
    assert killer.gold == 2 # Melee Value

def test_hero_defeat(defeat_state):
    state = defeat_state
    
    # Killer Team
    killer_id = HeroID("killer")
    killer = Hero(id=killer_id, name="Killer", deck=[], team=TeamColor.RED, gold=0)
    ally = Hero(id=HeroID("ally"), name="Ally", deck=[], team=TeamColor.RED, gold=0)
    
    # Victim Team
    victim_id = HeroID("victim")
    victim = Hero(id=victim_id, name="Victim", deck=[], team=TeamColor.BLUE, level=4, gold=0) # Level 4 -> Loss 2
    enemy_ally = Hero(id=HeroID("e_ally"), name="EnemyAlly", deck=[], team=TeamColor.BLUE, gold=0)
    
    state.teams[TeamColor.RED] = Team(color=TeamColor.RED, heroes=[killer, ally])
    state.teams[TeamColor.BLUE] = Team(color=TeamColor.BLUE, heroes=[victim, enemy_ally], life_counters=5)
    
    state.move_unit(victim_id, Hex(q=0,r=0,s=0))
    state.move_unit(killer_id, Hex(q=1,r=0,s=-1))
    
    # Setup Card in Queue for Victim (To check cancel)
    card = Card(id="c1", name="C1", tier=CardTier.I, color=CardColor.BLUE, initiative=1, primary_action=ActionType.ATTACK, effect_id="", effect_text="")
    state.resolution_queue = [(victim_id, card)]
    
    # Execute Defeat
    defeat_unit(state, victim_id, killer_id=killer_id)
    
    # 1. Life Loss (Level 4 -> 2)
    assert state.teams[TeamColor.BLUE].life_counters == 3 # 5 - 2
    
    # 2. Card Cancelled
    # Queue should be empty (popped)
    assert len(state.resolution_queue) == 0
    assert card.state == CardState.RESOLVED
    
    # 3. Rewards
    # Killer gets Victim Level (4)
    assert killer.gold == 4
    
    # Ally (Red Team) gets Life Loss (2)
    assert ally.gold == 2
    
    # Victim Ally (Blue Team) gets nothing
    assert enemy_ally.gold == 0
    
    # 4. Global Payout Logic Check
    # Rule: "Give coins to every OTHER ENEMY HERO... equal to life counters lost"
    # Enemy of Victim is Red Team.
    # Killer is Red. Ally is Red.
    # Killer got explicit reward. Does Killer ALSO get shared reward?
    # Logic in defeat.py:
    # "Iterate enemy team: If h != killer: h.gold += loss"
    # So Killer gets ONLY Kill Reward.
    # Ally gets Shared Reward.
    # My logic:
    #   Killer: +4
    #   Ally: +2
    # Verified above.


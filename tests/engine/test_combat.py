import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType, StatType, Card, CardTier, CardColor, ActionType
from goa2.engine.combat import calculate_attack_power, calculate_defense_power
from goa2.domain.hex import Hex
from goa2.domain.types import HeroID, UnitID, BoardEntityID
from goa2.domain.tile import Tile

@pytest.fixture
def combat_state():
    b = Board()
    state = GameState(board=b, teams={})
    
    # Red Team
    h_red = Hero(id="h_red", name="Red", team=TeamColor.RED, deck=[])
    m_red = Minion(id="m_red", name="RedMinion", type=MinionType.MELEE, team=TeamColor.RED)
    t_red = Team(color=TeamColor.RED, heroes=[h_red], minions=[m_red])
    state.teams[TeamColor.RED] = t_red
    
    # Blue Team
    h_blue = Hero(id="h_blue", name="Blue", team=TeamColor.BLUE, deck=[])
    t_blue = Team(color=TeamColor.BLUE, heroes=[h_blue])
    state.teams[TeamColor.BLUE] = t_blue
    
    return state

def test_attack_power_items(combat_state):
    s = combat_state
    h_red = s.teams[TeamColor.RED].heroes[0]
    
    # Base Attack (MVP assumption: 4)
    # With no items
    assert calculate_attack_power(card=None, attacker=h_red) == 4
    
    # With Item (+1)
    h_red.items[StatType.ATTACK] = 1
    assert calculate_attack_power(card=None, attacker=h_red) == 5

def test_defense_power_auras(combat_state):
    s = combat_state
    h_red = s.teams[TeamColor.RED].heroes[0] # Defender
    
    # Base Defense (MVP assumption: 3)
    assert calculate_defense_power(h_red, s) == 3
    
    # Position Hero at (0,0,0)
    center = Hex(q=0, r=0, s=0)
    s.unit_locations[UnitID("h_red")] = center
    
    # 1. Add Friendly Minion Adjacent
    # Hex (1, -1, 0) is neighbor
    adj_hex = Hex(q=1, r=-1, s=0)
    m_red = s.teams[TeamColor.RED].minions[0]
    s.unit_locations[UnitID("m_red")] = adj_hex
    
    # Populate Tile for lookup (Engine relies on Board Tiles)
    s.board.tiles[center] = Tile(hex=center, occupant_id=BoardEntityID("h_red"))
    s.board.tiles[adj_hex] = Tile(hex=adj_hex, occupant_id=BoardEntityID("m_red"))
    
    # Now Defense should be 3 + 1 (Aura) = 4
    assert calculate_defense_power(h_red, s) == 4
    
    # 2. Move Minion away (Not adjacent)
    far_hex = Hex(q=10, r=0, s=-10)
    s.unit_locations[UnitID("m_red")] = far_hex
    del s.board.tiles[adj_hex] # Clear old tile
    s.board.tiles[far_hex] = Tile(hex=far_hex, occupant_id=BoardEntityID("m_red"))
    
    assert calculate_defense_power(h_red, s) == 3

def test_defense_items(combat_state):
    s = combat_state
    h = s.teams[TeamColor.BLUE].heroes[0]
    
    # Base 3
    assert calculate_defense_power(h, s) == 3
    
    # Add Item
    h.items[StatType.DEFENSE] = 2
    assert calculate_defense_power(h, s) == 5

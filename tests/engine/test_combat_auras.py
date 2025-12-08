import pytest
from goa2.domain.models import Hero, Minion, MinionType, TeamColor, Team, StatType, Unit
from goa2.domain.state import GameState
from goa2.domain.board import Board, Tile
from goa2.domain.hex import Hex
from goa2.engine.combat import calculate_defense_power
from goa2.domain.types import HeroID, UnitID, BoardEntityID

@pytest.fixture
def aura_state():
    b = Board()
    red_hero = Hero(id=HeroID("h1"), name="RedH", deck=[], team=TeamColor.RED)
    blue_hero = Hero(id=HeroID("h2"), name="BlueH", deck=[], team=TeamColor.BLUE)
    
    t_red = Team(color=TeamColor.RED, heroes=[red_hero])
    t_blue = Team(color=TeamColor.BLUE, heroes=[blue_hero])
    
    state = GameState(board=b, teams={TeamColor.RED: t_red, TeamColor.BLUE: t_blue})
    
    # Place Red Hero at Center
    state.unit_locations[HeroID("h1")] = Hex(q=0, r=0, s=0)
    
    return state, red_hero

def place_minion(state, minion_id, m_type, team_color, q, r, s):
    m = Minion(id=UnitID(minion_id), type=m_type, team=team_color, name=minion_id)
    state.teams[team_color].minions.append(m)
    
    loc = Hex(q=q, r=r, s=s)
    state.unit_locations[m.id] = loc
    state.board.tiles[loc] = Tile(hex=loc, zone_id="z1", occupant_id=BoardEntityID(minion_id))
    return m

def test_no_aura(aura_state):
    state, hero = aura_state
    # Base 3
    assert calculate_defense_power(hero, state) == 3

def test_friendly_melee_aura(aura_state):
    state, hero = aura_state
    # Place Friendly Melee Adjacent (Ring 1)
    place_minion(state, "m1", MinionType.MELEE, TeamColor.RED, 1, -1, 0)
    
    # Base 3 + 1 = 4
    assert calculate_defense_power(hero, state) == 4

def test_friendly_melee_dist2(aura_state):
    state, hero = aura_state
    # Place Friendly Melee at Dist 2 (Ring 2)
    place_minion(state, "m1", MinionType.MELEE, TeamColor.RED, 2, -2, 0)
    
    # Base 3 + 0 = 3
    assert calculate_defense_power(hero, state) == 3

def test_enemy_melee_aura(aura_state):
    state, hero = aura_state
    # Place Enemy Melee Adjacent (Ring 1)
    place_minion(state, "m1", MinionType.MELEE, TeamColor.BLUE, 1, -1, 0)
    
    # Base 3 - 1 = 2
    assert calculate_defense_power(hero, state) == 2

def test_friendly_ranged_aura(aura_state):
    state, hero = aura_state
    # Place Friendly Ranged Adjacent (Ring 1)
    place_minion(state, "m1", MinionType.RANGED, TeamColor.RED, 1, -1, 0)
    
    # Base 3 + 0 (Ranged provide no defense) = 3
    assert calculate_defense_power(hero, state) == 3

def test_enemy_ranged_aura_ring1(aura_state):
    state, hero = aura_state
    # Place Enemy Ranged Adjacent (Ring 1)
    place_minion(state, "m1", MinionType.RANGED, TeamColor.BLUE, 1, -1, 0)
    
    # Base 3 - 1 = 2
    assert calculate_defense_power(hero, state) == 2

def test_enemy_ranged_aura_ring2(aura_state):
    state, hero = aura_state
    # Place Enemy Ranged Dist 2 (Ring 2)
    place_minion(state, "m1", MinionType.RANGED, TeamColor.BLUE, 2, -2, 0)
    
    # Base 3 - 1 = 2
    assert calculate_defense_power(hero, state) == 2

def test_enemy_ranged_aura_ring3(aura_state):
    state, hero = aura_state
    # Place Enemy Ranged Dist 3 (Ring 3)
    place_minion(state, "m1", MinionType.RANGED, TeamColor.BLUE, 3, -3, 0)
    
    # Base 3 + 0 = 3
    assert calculate_defense_power(hero, state) == 3

def test_stacking_auras(aura_state):
    state, hero = aura_state
    # Friendly Melee (+1)
    place_minion(state, "m1", MinionType.MELEE, TeamColor.RED, 1, 0, -1)
    # Enemy Melee (-1)
    place_minion(state, "m2", MinionType.MELEE, TeamColor.BLUE, -1, 0, 1)
    # Enemy Ranged Dist 2 (-1)
    place_minion(state, "m3", MinionType.RANGED, TeamColor.BLUE, 0, 2, -2)
    
    # Base 3 + 1 - 1 - 1 = 2
    assert calculate_defense_power(hero, state) == 2

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType
from goa2.domain.hex import Hex
from goa2.engine.stats import calculate_minion_defense_modifier

@pytest.fixture
def aura_state():
    # Setup: 
    # Hero (RED) at 0,0,0
    # Ally Melee (RED) at 1,0,-1 (Range 1) -> +1
    # Ally Ranged (RED) at -1,1,0 (Range 1) -> 0
    # Enemy Melee (BLUE) at 0,1,-1 (Range 1) -> -1
    # Enemy Ranged (BLUE) at 2,0,-2 (Range 2) -> -1
    
    h1 = Hero(id="H1", name="Hero", team=TeamColor.RED, deck=[])
    m_ally_melee = Minion(id="M1", name="AllyMelee", team=TeamColor.RED, type=MinionType.MELEE)
    m_ally_ranged = Minion(id="M2", name="AllyRanged", team=TeamColor.RED, type=MinionType.RANGED)
    m_enemy_melee = Minion(id="M3", name="EnemyMelee", team=TeamColor.BLUE, type=MinionType.MELEE)
    m_enemy_ranged = Minion(id="M4", name="EnemyRanged", team=TeamColor.BLUE, type=MinionType.RANGED)
    
    # Create Board with tiles
    board = Board()
    locations = {
        "H1": Hex(q=0, r=0, s=0),
        "M1": Hex(q=1, r=0, s=-1),
        "M2": Hex(q=-1, r=1, s=0),
        "M3": Hex(q=0, r=1, s=-1),
        "M4": Hex(q=2, r=0, s=-2)
    }
    
    from goa2.domain.tile import Tile
    for uid, h in locations.items():
        board.tiles[h] = Tile(hex=h, occupant_id=uid)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[m_ally_melee, m_ally_ranged]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[m_enemy_melee, m_enemy_ranged])
        },
        unit_locations=locations
    )
    return state

def test_minion_aura_calculation(aura_state):
    # Total expected: (+1 from M1) + (0 from M2) + (-1 from M3) + (-1 from M4) = -1
    modifier = calculate_minion_defense_modifier(aura_state, "H1")
    assert modifier == -1

def test_minion_aura_enemy_ranged_at_range_1(aura_state):
    # If enemy ranged is at range 1, it should still give -1 (it's an enemy minion at range 1)
    aura_state.unit_locations["M4"] = Hex(q=1, r=-1, s=0) # Move M4 to Range 1
    # Expected: (+1 M1) + (0 M2) + (-1 M3) + (-1 M4) = -1
    modifier = calculate_minion_defense_modifier(aura_state, "H1")
    assert modifier == -1

def test_minion_aura_no_hero_location(aura_state):
    del aura_state.unit_locations["H1"]
    assert calculate_minion_defense_modifier(aura_state, "H1") == 0

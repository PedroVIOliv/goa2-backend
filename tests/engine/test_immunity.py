import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType
from goa2.domain.hex import Hex
from goa2.engine.steps import SelectStep
from goa2.engine.filters import TeamFilter, ImmunityFilter
from goa2.engine import rules

@pytest.fixture
def immunity_state():
    board = Board()
    # Zone 1 (Battle Zone)
    z1 = Zone(id="z1", name="Battle", hexes=[Hex(q=0,r=0,s=0), Hex(q=1,r=0,s=-1), Hex(q=2,r=0,s=-2)])
    board.zones["z1"] = z1
    
    for h in z1.hexes:
        board.tiles[h] = Tile(hex=h)
        
    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, deck=[])
    
    # Heavy Minion (Target)
    m_heavy = Minion(id="m_heavy", name="Heavy", type=MinionType.HEAVY, team=TeamColor.BLUE)
    
    # Support Minion
    m_support = Minion(id="m_supp", name="Support", type=MinionType.MELEE, team=TeamColor.BLUE)
    
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[m_heavy, m_support])
        },
        entity_locations={},
        current_actor_id="h1",
        active_zone_id="z1"
    )
    # Sync board
    state.place_entity("h1", Hex(q=0, r=0, s=0))
    state.place_entity("m_heavy", Hex(q=1, r=0, s=-1))
    state.place_entity("m_supp", Hex(q=2, r=0, s=-2))
    
    return state

def test_heavy_immunity_rule_logic(immunity_state):
    # Verify the rule logic itself
    target = immunity_state.get_unit("m_heavy")
    
    # Should be Immune because m_supp is in zone
    assert rules.is_immune(target, immunity_state) == True
    
    # Remove Support
    immunity_state.remove_unit("m_supp")
    
    # Should NOT be Immune now
    assert rules.is_immune(target, immunity_state) == False

def test_select_step_respects_immunity(immunity_state):
    # This test simulates an attack selection.
    # We want to ensure 'm_heavy' is filtered out when immune.
    
    # 1. With Support Minion (Immunity Active)
    step = SelectStep(
        target_type="UNIT",
        prompt="Attack",
        filters=[TeamFilter(relation="ENEMY"), ImmunityFilter()]
    )
    
    # Resolve
    res = step.resolve(immunity_state, {})
    
    # Check candidates
    valid = res.input_request["valid_options"]
    
    # m_heavy should NOT be there
    assert "m_heavy" not in valid
    # m_supp should be there (not heavy)
    assert "m_supp" in valid
    
    # 2. Remove Support (Immunity Inactive)
    immunity_state.remove_unit("m_supp")
    
    res2 = step.resolve(immunity_state, {})
    valid2 = res2.input_request["valid_options"]
    
    # m_heavy SHOULD be there now
    assert "m_heavy" in valid2
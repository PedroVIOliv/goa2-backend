import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, Minion, MinionType
from goa2.domain.types import UnitID
from goa2.engine.steps import EndPhaseStep
from goa2.engine.handler import process_resolution_stack, push_steps

def create_minion(id_str, team, m_type):
    return Minion(
        id=UnitID(id_str), 
        name=id_str, 
        team=team, 
        type=m_type
    )

@pytest.fixture
def battle_state():
    board = Board()
    # Define a Zone
    zone_hexes = [Hex(q=0,r=0,s=0), Hex(q=1,r=-1,s=0), Hex(q=1,r=0,s=-1)]
    board.zones["zone1"] = Zone(id="zone1", name="Test Zone", hexes=set(zone_hexes))
    
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[])
        },
        active_zone_id="zone1"
    )
    return state

def test_minion_battle_simple_removal(battle_state):
    """
    Red: 2 Minions
    Blue: 1 Minion
    Result: Blue loses 1 (Wiped out).
    """
    m_red1 = create_minion("r1", TeamColor.RED, MinionType.MELEE)
    m_red2 = create_minion("r2", TeamColor.RED, MinionType.MELEE)
    m_blue1 = create_minion("b1", TeamColor.BLUE, MinionType.MELEE)
    
    # Place on board in Zone
    battle_state.teams[TeamColor.RED].minions.extend([m_red1, m_red2])
    battle_state.teams[TeamColor.BLUE].minions.append(m_blue1)
    
    battle_state.move_unit(m_red1.id, Hex(q=0,r=0,s=0))
    battle_state.move_unit(m_red2.id, Hex(q=1,r=-1,s=0))
    battle_state.move_unit(m_blue1.id, Hex(q=1,r=0,s=-1))
    
    # Run Step
    step = EndPhaseStep()
    push_steps(battle_state, [step])
    process_resolution_stack(battle_state)
    
    # Verify Blue minion removed
    assert m_blue1.id not in battle_state.unit_locations
    # Red minions remain
    assert m_red1.id in battle_state.unit_locations
    assert m_red2.id in battle_state.unit_locations

def test_minion_battle_heavy_constraint(battle_state):
    """
    Red: 3 Minions (1 Heavy, 2 Melee)
    Blue: 2 Minions (2 Melee)
    Result: Blue loses (Diff 1).
    Scenario B (Reverse): 
    Blue: 3 Minions (1 Heavy, 2 Melee)
    Red: 1 Minion
    Result: Red loses (Diff 2). Red has 0.
    
    Real Test:
    Red: 2 Minions (1 Heavy, 1 Melee)
    Blue: 1 Minion (1 Melee)
    Diff: 1.
    Blue is loser (Count 1 vs 2). Blue loses 1.
    
    Let's test the CONSTRAINT on the loser.
    Loser has: 1 Heavy, 1 Melee.
    Winner has: 4 Minions.
    Diff: 2.
    Loser must remove 2.
    Constraint: Heavy must be last.
    So remove Melee first, then Heavy.
    """
    # Loser (Red)
    m_red_heavy = create_minion("r_heavy", TeamColor.RED, MinionType.HEAVY)
    m_red_melee = create_minion("r_melee", TeamColor.RED, MinionType.MELEE)
    
    # Winner (Blue) - 4 Minions
    blues = [create_minion(f"b{i}", TeamColor.BLUE, MinionType.MELEE) for i in range(4)]
    
    battle_state.teams[TeamColor.RED].minions.extend([m_red_heavy, m_red_melee])
    battle_state.teams[TeamColor.BLUE].minions.extend(blues)
    
    # Place Red (Loser)
    battle_state.move_unit(m_red_heavy.id, Hex(q=0,r=0,s=0))
    battle_state.move_unit(m_red_melee.id, Hex(q=1,r=-1,s=0))
    
    # Place Blue (Winner) - Just put them all on same tile for count logic (hack but works for step)
    # Actually step checks keys.
    # Note: State.move_unit overwrites tile occupant. 
    # But Minion Battle checks unit_locations list.
    # So we can put them on dummy hexes even if they overlap in 'logic' (invalid state but valid for this test func)
    # BUT MoveUnit clears old.
    # Let's put them on distinct hexes in zone.
    # Zone only has 3 hexes. We need more for 6 units.
    # Expand zone
    extra_hexes = [Hex(q=10, r=i, s=-10-i) for i in range(10)]
    battle_state.board.zones["zone1"].hexes.update(extra_hexes)
    
    # Place Blues
    for i, m in enumerate(blues):
        battle_state.move_unit(m.id, extra_hexes[i])
        
    # Run Step
    # Red (2) vs Blue (4). Diff = 2.
    # Red must remove 2.
    # Should remove Melee, then Heavy. Both removed.
    
    step = EndPhaseStep()
    push_steps(battle_state, [step])
    process_resolution_stack(battle_state)
    
    assert m_red_melee.id not in battle_state.unit_locations
    assert m_red_heavy.id not in battle_state.unit_locations

def test_minion_battle_heavy_protection(battle_state):
    """
    Loser (Red) has: 1 Heavy, 2 Melee.
    Winner (Blue) has: 4 Minions.
    Diff = 1.
    Red must remove 1.
    MUST remove Melee (Heavy is protected).
    """
    m_red_heavy = create_minion("r_heavy", TeamColor.RED, MinionType.HEAVY)
    m_red_melee1 = create_minion("r_melee1", TeamColor.RED, MinionType.MELEE)
    m_red_melee2 = create_minion("r_melee2", TeamColor.RED, MinionType.MELEE)
    
    # Winner (Blue) - 4 Minions
    blues = [create_minion(f"b{i}", TeamColor.BLUE, MinionType.MELEE) for i in range(4)]
    
    # Register in Teams
    battle_state.teams[TeamColor.RED].minions.extend([m_red_heavy, m_red_melee1, m_red_melee2])
    battle_state.teams[TeamColor.BLUE].minions.extend(blues)

    # Expand zone
    extra_hexes = [Hex(q=10, r=i, s=-10-i) for i in range(10)]
    battle_state.board.zones["zone1"].hexes.update(extra_hexes)
    
    battle_state.move_unit(m_red_heavy.id, Hex(q=0,r=0,s=0))
    battle_state.move_unit(m_red_melee1.id, Hex(q=1,r=-1,s=0))
    battle_state.move_unit(m_red_melee2.id, Hex(q=1,r=0,s=-1))
    
    for i, m in enumerate(blues):
        battle_state.move_unit(m.id, extra_hexes[i])
        
    # Run Step
    step = EndPhaseStep()
    push_steps(battle_state, [step])
    process_resolution_stack(battle_state)
    
    # Verify: One melee gone, Heavy REMAINS.
    # Since we sort [Melee, Melee, Heavy], the first Melee is removed.
    # Note: Sorting is stable? or dependent on ID?
    # Key is is_heavy (False < True).
    # So list is [Melee1, Melee2, Heavy].
    # Removes [0].
    
    assert m_red_heavy.id in battle_state.unit_locations
    # At least one melee gone
    remaining = [m for m in [m_red_melee1, m_red_melee2] if m.id in battle_state.unit_locations]
    assert len(remaining) == 1

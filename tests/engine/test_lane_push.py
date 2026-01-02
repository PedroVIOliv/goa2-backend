import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, Minion, MinionType
from goa2.domain.types import UnitID
from goa2.engine.steps import EndPhaseStep, DefeatUnitStep
from goa2.engine.handler import process_resolution_stack, push_steps

def create_minion(id_str, team):
    return Minion(id=UnitID(id_str), name=id_str, team=team, type=MinionType.MELEE)

@pytest.fixture
def push_state():
    board = Board()
    # Lane: RedBase -> Mid -> BlueBase
    board.lane = ["z_red", "z_mid", "z_blue"]
    
    # Define Zones
    # Mid Zone hexes
    mid_hexes = [Hex(q=0,r=0,s=0), Hex(q=1,r=-1,s=0)]
    board.zones["z_mid"] = Zone(id="z_mid", name="Mid", hexes=set(mid_hexes))
    
    board.zones["z_red"] = Zone(id="z_red", name="Red Base", hexes=set())
    board.zones["z_blue"] = Zone(id="z_blue", name="Blue Base", hexes=set())
    
    from goa2.domain.tile import Tile
    for h in mid_hexes:
        board.tiles[h] = Tile(hex=h, zone_id="z_mid")
    
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[])
        },
        active_zone_id="z_mid",
        wave_counter=5
    )
    return state

def test_end_phase_push_trigger(push_state):
    """
    Minion Battle: Red 0 vs Blue 1.
    Red Loses. Blue Pushes.
    Target: Red Base (Index 0).
    """
    # Setup: 1 Blue Minion in Mid
    m_blue = create_minion("b1", TeamColor.BLUE)
    push_state.teams[TeamColor.BLUE].minions.append(m_blue)
    push_state.move_unit(m_blue.id, Hex(q=0,r=0,s=0))
    
    # End Phase
    step = EndPhaseStep()
    push_steps(push_state, [step])
    process_resolution_stack(push_state)
    
    # 1. Wave Counter Removed
    assert push_state.wave_counter == 4
    
    # 2. Zone Moved Towards Red (z_red is index 0, z_mid is 1)
    # Blue Pushes -> Index - 1 -> 0 -> z_red
    assert push_state.active_zone_id == "z_red"
    
    # 3. Minion Removed (Wiped from old zone)
    assert m_blue.id not in push_state.unit_locations

def test_combat_push_trigger(push_state):
    """
    Combat: Red Minion kills Blue Minion (Last one).
    Blue count -> 0. Blue Loses. Red Pushes.
    Target: Blue Base (Index 2).
    """
    # Setup: 1 Red Minion, 1 Blue Minion
    # Red Minion kills Blue
    m_red = create_minion("r1", TeamColor.RED)
    m_blue = create_minion("b1", TeamColor.BLUE)
    
    push_state.teams[TeamColor.RED].minions.append(m_red)
    push_state.teams[TeamColor.BLUE].minions.append(m_blue)
    
    push_state.move_unit(m_red.id, Hex(q=0,r=0,s=0))
    push_state.move_unit(m_blue.id, Hex(q=1,r=-1,s=0))
    
    # Kill Step
    step = DefeatUnitStep(victim_id=m_blue.id, killer_id=m_red.id)
    push_steps(push_state, [step])
    process_resolution_stack(push_state)
    
    # Blue died. Blue Count = 0. Red > 0.
    # Red Pushes -> Index + 1 -> 2 -> z_blue
    
    assert push_state.active_zone_id == "z_blue"
    assert push_state.wave_counter == 4
    
    # Red Minion Wiped?
    # Yes, push wipes old zone.
    assert m_red.id not in push_state.unit_locations

def test_last_push_victory(push_state):
    """
    Wave Counter = 1.
    Push Triggered.
    Wave Counter -> 0.
    Game Over? (Handled by step returning finished, we check counter)
    """
    push_state.wave_counter = 1
    
    # Trigger Push (Red 0, Blue 1)
    m_blue = create_minion("b1", TeamColor.BLUE)
    push_state.teams[TeamColor.BLUE].minions.append(m_blue)
    push_state.move_unit(m_blue.id, Hex(q=0,r=0,s=0))
    
    step = EndPhaseStep()
    push_steps(push_state, [step])
    process_resolution_stack(push_state)
    
    assert push_state.wave_counter == 0
    # We don't have explicit Game Over state yet, but counter is 0.

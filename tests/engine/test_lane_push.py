import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, Minion, MinionType
from goa2.domain.models.spawn import SpawnPoint, SpawnType
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


def test_lane_push_spawns_minions_in_new_zone():
    """
    After a lane push, minions should spawn at the new zone's spawn points.
    """
    from goa2.domain.tile import Tile

    board = Board()
    board.lane = ["z_red", "z_mid", "z_blue"]

    # Mid zone hexes (current battle zone)
    mid_hexes = [Hex(q=0, r=0, s=0)]
    # Red zone hexes (push target) with spawn points
    red_hex_1 = Hex(q=-2, r=1, s=1)
    red_hex_2 = Hex(q=-3, r=1, s=2)
    red_hexes = [red_hex_1, red_hex_2]

    red_spawn_1 = SpawnPoint(
        location=red_hex_1, team=TeamColor.RED, type=SpawnType.MINION, minion_type=MinionType.MELEE
    )
    red_spawn_2 = SpawnPoint(
        location=red_hex_2, team=TeamColor.BLUE, type=SpawnType.MINION, minion_type=MinionType.MELEE
    )

    board.zones["z_mid"] = Zone(id="z_mid", name="Mid", hexes=set(mid_hexes))
    board.zones["z_red"] = Zone(
        id="z_red", name="Red Base", hexes=set(red_hexes),
        spawn_points=[red_spawn_1, red_spawn_2],
    )
    board.zones["z_blue"] = Zone(id="z_blue", name="Blue Base", hexes=set())

    for h in mid_hexes:
        board.tiles[h] = Tile(hex=h, zone_id="z_mid")
    for h in red_hexes:
        board.tiles[h] = Tile(hex=h, zone_id="z_red")

    # Create minions for both teams (unplaced, available for spawning)
    m_red = Minion(id=UnitID("r_melee"), name="r_melee", team=TeamColor.RED, type=MinionType.MELEE)
    m_blue_spawnable = Minion(id=UnitID("b_melee"), name="b_melee", team=TeamColor.BLUE, type=MinionType.MELEE)

    # Place one blue minion in mid to trigger the push (blue wins, red loses)
    m_blue_in_mid = create_minion("b1", TeamColor.BLUE)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[m_red]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[m_blue_in_mid, m_blue_spawnable]),
        },
        active_zone_id="z_mid",
        wave_counter=5,
    )
    state.move_unit(m_blue_in_mid.id, Hex(q=0, r=0, s=0))

    step = EndPhaseStep()
    push_steps(state, [step])
    process_resolution_stack(state)

    # Zone should have pushed towards red
    assert state.active_zone_id == "z_red"

    # Minions should have spawned at the red zone spawn points
    assert state.unit_locations.get(m_red.id) == red_hex_1
    # b1 was wiped from old zone and is first available blue melee, so it respawns
    assert state.unit_locations.get(m_blue_in_mid.id) == red_hex_2

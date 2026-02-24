import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, Minion, MinionType, GamePhase
from goa2.domain.models.spawn import SpawnPoint, SpawnType
from goa2.domain.types import UnitID
from goa2.engine.steps import EndPhaseStep, DefeatUnitStep
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.session import GameSession, SessionResultType
from goa2.engine.map_logic import get_push_target_zone_id

def create_minion(id_str, team):
    return Minion(id=UnitID(id_str), name=id_str, team=team, type=MinionType.MELEE)

@pytest.fixture
def push_state():
    """5-zone lane: RedBase -> RedBeach -> Mid -> BlueBeach -> BlueBase"""
    from goa2.domain.tile import Tile

    board = Board()
    board.lane = ["z_red_base", "z_red_beach", "z_mid", "z_blue_beach", "z_blue_base"]

    mid_hexes = [Hex(q=0, r=0, s=0), Hex(q=1, r=-1, s=0)]
    red_beach_hexes = [Hex(q=-1, r=0, s=1), Hex(q=-1, r=1, s=0)]
    blue_beach_hexes = [Hex(q=2, r=-1, s=-1), Hex(q=2, r=0, s=-2)]

    board.zones["z_red_base"] = Zone(id="z_red_base", name="Red Base", hexes=set())
    board.zones["z_red_beach"] = Zone(id="z_red_beach", name="Red Beach", hexes=set(red_beach_hexes))
    board.zones["z_mid"] = Zone(id="z_mid", name="Mid", hexes=set(mid_hexes))
    board.zones["z_blue_beach"] = Zone(id="z_blue_beach", name="Blue Beach", hexes=set(blue_beach_hexes))
    board.zones["z_blue_base"] = Zone(id="z_blue_base", name="Blue Base", hexes=set())

    for h in mid_hexes:
        board.tiles[h] = Tile(hex=h, zone_id="z_mid")
    for h in red_beach_hexes:
        board.tiles[h] = Tile(hex=h, zone_id="z_red_beach")
    for h in blue_beach_hexes:
        board.tiles[h] = Tile(hex=h, zone_id="z_blue_beach")

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
    Minion Battle at Mid: Red 0 vs Blue 1.
    Red Loses. Push towards Red Beach.
    """
    m_blue = create_minion("b1", TeamColor.BLUE)
    push_state.teams[TeamColor.BLUE].minions.append(m_blue)
    push_state.move_unit(m_blue.id, Hex(q=0, r=0, s=0))

    step = EndPhaseStep()
    push_steps(push_state, [step])
    process_resolution_stack(push_state)

    assert push_state.wave_counter == 4
    assert push_state.active_zone_id == "z_red_beach"
    assert m_blue.id not in push_state.unit_locations

def test_combat_push_trigger(push_state):
    """
    Combat at Mid: Red kills last Blue minion.
    Blue Loses. Push towards Blue Beach.
    """
    m_red = create_minion("r1", TeamColor.RED)
    m_blue = create_minion("b1", TeamColor.BLUE)

    push_state.teams[TeamColor.RED].minions.append(m_red)
    push_state.teams[TeamColor.BLUE].minions.append(m_blue)

    push_state.move_unit(m_red.id, Hex(q=0, r=0, s=0))
    push_state.move_unit(m_blue.id, Hex(q=1, r=-1, s=0))

    step = DefeatUnitStep(victim_id=m_blue.id, killer_id=m_red.id)
    push_steps(push_state, [step])
    process_resolution_stack(push_state)

    assert push_state.active_zone_id == "z_blue_beach"
    assert push_state.wave_counter == 4
    assert m_red.id not in push_state.unit_locations

def test_last_push_victory(push_state):
    """
    Wave Counter = 1. Push triggers LAST_PUSH game over.
    """
    push_state.wave_counter = 1

    m_blue = create_minion("b1", TeamColor.BLUE)
    push_state.teams[TeamColor.BLUE].minions.append(m_blue)
    push_state.move_unit(m_blue.id, Hex(q=0, r=0, s=0))

    step = EndPhaseStep()
    push_steps(push_state, [step])
    process_resolution_stack(push_state)

    assert push_state.wave_counter == 0
    assert push_state.phase == GamePhase.GAME_OVER
    assert push_state.victory_condition == "LAST_PUSH"


def test_lane_push_spawns_minions_in_new_zone():
    """
    After a lane push from Mid, minions should spawn at the new Beach zone's spawn points.
    """
    from goa2.domain.tile import Tile

    board = Board()
    board.lane = ["z_red_base", "z_red_beach", "z_mid", "z_blue_beach", "z_blue_base"]

    mid_hexes = [Hex(q=0, r=0, s=0)]
    red_beach_hex_1 = Hex(q=-2, r=1, s=1)
    red_beach_hex_2 = Hex(q=-3, r=1, s=2)
    red_beach_hexes = [red_beach_hex_1, red_beach_hex_2]

    red_spawn_1 = SpawnPoint(
        location=red_beach_hex_1, team=TeamColor.RED, type=SpawnType.MINION, minion_type=MinionType.MELEE
    )
    red_spawn_2 = SpawnPoint(
        location=red_beach_hex_2, team=TeamColor.BLUE, type=SpawnType.MINION, minion_type=MinionType.MELEE
    )

    board.zones["z_red_base"] = Zone(id="z_red_base", name="Red Base", hexes=set())
    board.zones["z_red_beach"] = Zone(
        id="z_red_beach", name="Red Beach", hexes=set(red_beach_hexes),
        spawn_points=[red_spawn_1, red_spawn_2],
    )
    board.zones["z_mid"] = Zone(id="z_mid", name="Mid", hexes=set(mid_hexes))
    board.zones["z_blue_beach"] = Zone(id="z_blue_beach", name="Blue Beach", hexes=set())
    board.zones["z_blue_base"] = Zone(id="z_blue_base", name="Blue Base", hexes=set())

    for h in mid_hexes:
        board.tiles[h] = Tile(hex=h, zone_id="z_mid")
    for h in red_beach_hexes:
        board.tiles[h] = Tile(hex=h, zone_id="z_red_beach")

    m_red = Minion(id=UnitID("r_melee"), name="r_melee", team=TeamColor.RED, type=MinionType.MELEE)
    m_blue_spawnable = Minion(id=UnitID("b_melee"), name="b_melee", team=TeamColor.BLUE, type=MinionType.MELEE)
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

    assert state.active_zone_id == "z_red_beach"
    assert state.unit_locations.get(m_red.id) == red_beach_hex_1
    assert state.unit_locations.get(m_blue_in_mid.id) == red_beach_hex_2


# --- Game-over boundary tests ---

def test_push_from_blue_beach_triggers_game_over(push_state):
    """
    Blue loses at BlueBeach → push reaches BlueBase → game over.
    """
    push_state.active_zone_id = "z_blue_beach"

    m_red = create_minion("r1", TeamColor.RED)
    push_state.teams[TeamColor.RED].minions.append(m_red)
    push_state.move_unit(m_red.id, Hex(q=2, r=-1, s=-1))

    step = EndPhaseStep()
    push_steps(push_state, [step])
    process_resolution_stack(push_state)

    assert push_state.phase == GamePhase.GAME_OVER
    assert push_state.winner == TeamColor.RED
    assert push_state.victory_condition == "LANE_PUSH"

def test_push_from_red_beach_triggers_game_over(push_state):
    """
    Red loses at RedBeach → push reaches RedBase → game over.
    """
    push_state.active_zone_id = "z_red_beach"

    m_blue = create_minion("b1", TeamColor.BLUE)
    push_state.teams[TeamColor.BLUE].minions.append(m_blue)
    push_state.move_unit(m_blue.id, Hex(q=-1, r=0, s=1))

    step = EndPhaseStep()
    push_steps(push_state, [step])
    process_resolution_stack(push_state)

    assert push_state.phase == GamePhase.GAME_OVER
    assert push_state.winner == TeamColor.BLUE
    assert push_state.victory_condition == "LANE_PUSH"

def test_push_from_mid_not_game_over(push_state):
    """
    Push from Mid goes to a Beach zone, NOT game over.
    """
    # Red loses at Mid → pushes toward RedBeach
    target, is_over = get_push_target_zone_id(push_state, TeamColor.RED)
    assert target == "z_red_beach"
    assert is_over is False

    # Blue loses at Mid → pushes toward BlueBeach
    target, is_over = get_push_target_zone_id(push_state, TeamColor.BLUE)
    assert target == "z_blue_beach"
    assert is_over is False

def test_get_push_target_zone_id_beach_to_base_is_game_over(push_state):
    """
    Direct unit test: pushing from Beach toward Base returns game over.
    """
    # Red loses at RedBeach (idx 1) → new_idx=0 (RedBase) → game over
    push_state.active_zone_id = "z_red_beach"
    target, is_over = get_push_target_zone_id(push_state, TeamColor.RED)
    assert target is None
    assert is_over is True

    # Blue loses at BlueBeach (idx 3) → new_idx=4 (BlueBase) → game over
    push_state.active_zone_id = "z_blue_beach"
    target, is_over = get_push_target_zone_id(push_state, TeamColor.BLUE)
    assert target is None
    assert is_over is True


# --- SessionResult.winner tests ---

def test_session_winner_set_for_lane_push(push_state):
    """GameSession.advance() returns winner for lane push game over."""
    push_state.active_zone_id = "z_blue_beach"

    m_red = create_minion("r1", TeamColor.RED)
    push_state.teams[TeamColor.RED].minions.append(m_red)
    push_state.move_unit(m_red.id, Hex(q=2, r=-1, s=-1))

    session = GameSession(push_state)
    push_steps(push_state, [EndPhaseStep()])
    result = session.advance()

    assert result.result_type == SessionResultType.GAME_OVER
    assert result.winner == "RED"


def test_session_winner_set_for_last_push(push_state):
    """GameSession.advance() returns winner for last push game over."""
    push_state.wave_counter = 1

    m_blue = create_minion("b1", TeamColor.BLUE)
    push_state.teams[TeamColor.BLUE].minions.append(m_blue)
    push_state.move_unit(m_blue.id, Hex(q=0, r=0, s=0))

    session = GameSession(push_state)
    push_steps(push_state, [EndPhaseStep()])
    result = session.advance()

    assert result.result_type == SessionResultType.GAME_OVER
    assert result.winner is not None

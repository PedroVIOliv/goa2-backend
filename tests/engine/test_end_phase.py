import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, Minion, MinionType
from goa2.domain.types import UnitID
from goa2.domain.input import InputResponse
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
    Diff: 1, Blue has 1 minion total.
    to_remove (1) >= N-1 (0) => auto-skip, removes the minion.
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

    # Run Step — auto-skips (to_remove=1 >= N-1=0)
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
    Red (loser): 2 Minions (1 Heavy, 1 Melee)
    Blue (winner): 4 Minions
    Diff: 2, Red has 2 minions.
    to_remove (2) >= N-1 (1) => auto-skip, removes all sorted non-heavy first.
    """
    # Loser (Red)
    m_red_heavy = create_minion("r_heavy", TeamColor.RED, MinionType.HEAVY)
    m_red_melee = create_minion("r_melee", TeamColor.RED, MinionType.MELEE)

    # Winner (Blue) - 4 Minions
    blues = [create_minion(f"b{i}", TeamColor.BLUE, MinionType.MELEE) for i in range(4)]

    battle_state.teams[TeamColor.RED].minions.extend([m_red_heavy, m_red_melee])
    battle_state.teams[TeamColor.BLUE].minions.extend(blues)

    # Expand zone for all units
    extra_hexes = [Hex(q=10, r=i, s=-10-i) for i in range(10)]
    battle_state.board.zones["zone1"].hexes.update(extra_hexes)

    battle_state.move_unit(m_red_heavy.id, Hex(q=0,r=0,s=0))
    battle_state.move_unit(m_red_melee.id, Hex(q=1,r=-1,s=0))
    for i, m in enumerate(blues):
        battle_state.move_unit(m.id, extra_hexes[i])

    # Run Step — auto-skips (to_remove=2 >= N-1=1)
    step = EndPhaseStep()
    push_steps(battle_state, [step])
    process_resolution_stack(battle_state)

    assert m_red_melee.id not in battle_state.unit_locations
    assert m_red_heavy.id not in battle_state.unit_locations

def test_minion_battle_heavy_protection(battle_state):
    """
    Red (loser): 3 Minions (1 Heavy, 2 Melee)
    Blue (winner): 4 Minions
    Diff: 1, Red has 3 minions.
    to_remove (1) < N-1 (2) => player choice required.
    Only non-heavy minions should be offered as options.
    """
    m_red_heavy = create_minion("r_heavy", TeamColor.RED, MinionType.HEAVY)
    m_red_melee1 = create_minion("r_melee1", TeamColor.RED, MinionType.MELEE)
    m_red_melee2 = create_minion("r_melee2", TeamColor.RED, MinionType.MELEE)

    # Winner (Blue) - 4 Minions
    blues = [create_minion(f"b{i}", TeamColor.BLUE, MinionType.MELEE) for i in range(4)]

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

    # Run Step — requires input (to_remove=1 < N-1=2)
    step = EndPhaseStep()
    push_steps(battle_state, [step])
    req = process_resolution_stack(battle_state)

    # Verify input request
    assert req is not None
    assert req["type"] == "SELECT_UNIT"
    assert req["player_id"] == "team:RED"

    # Only non-heavy minions should be offered
    valid = req["valid_options"]
    assert "r_heavy" not in valid
    assert "r_melee1" in valid
    assert "r_melee2" in valid

    # Submit choice
    resp = InputResponse(selection="r_melee1")
    battle_state.execution_stack[-1].pending_input = {"selection": "r_melee1"}
    process_resolution_stack(battle_state)

    # Verify: chosen melee gone, heavy remains, other melee remains
    assert "r_melee1" not in battle_state.unit_locations
    assert m_red_heavy.id in battle_state.unit_locations
    assert m_red_melee2.id in battle_state.unit_locations


def test_minion_battle_team_validation(battle_state):
    """
    Verify that the input request uses team:RED convention for team-level input.
    """
    m_red_heavy = create_minion("r_heavy", TeamColor.RED, MinionType.HEAVY)
    m_red_melee1 = create_minion("r_melee1", TeamColor.RED, MinionType.MELEE)
    m_red_melee2 = create_minion("r_melee2", TeamColor.RED, MinionType.MELEE)

    blues = [create_minion(f"b{i}", TeamColor.BLUE, MinionType.MELEE) for i in range(4)]

    battle_state.teams[TeamColor.RED].minions.extend([m_red_heavy, m_red_melee1, m_red_melee2])
    battle_state.teams[TeamColor.BLUE].minions.extend(blues)

    extra_hexes = [Hex(q=10, r=i, s=-10-i) for i in range(10)]
    battle_state.board.zones["zone1"].hexes.update(extra_hexes)

    battle_state.move_unit(m_red_heavy.id, Hex(q=0,r=0,s=0))
    battle_state.move_unit(m_red_melee1.id, Hex(q=1,r=-1,s=0))
    battle_state.move_unit(m_red_melee2.id, Hex(q=1,r=0,s=-1))
    for i, m in enumerate(blues):
        battle_state.move_unit(m.id, extra_hexes[i])

    step = EndPhaseStep()
    push_steps(battle_state, [step])
    req = process_resolution_stack(battle_state)

    assert req is not None
    assert req["player_id"] == "team:RED"


def test_minion_battle_multi_removal_choice(battle_state):
    """
    Red (loser): 4 Minions (1 Heavy, 3 Melee)
    Blue (winner): 6 Minions
    Diff: 2, Red has 4 minions.
    to_remove (2) < N-1 (3) => two rounds of player selection.
    Heavy should never be offered while non-heavy minions exist.
    """
    m_red_heavy = create_minion("r_heavy", TeamColor.RED, MinionType.HEAVY)
    m_red_melee1 = create_minion("r_melee1", TeamColor.RED, MinionType.MELEE)
    m_red_melee2 = create_minion("r_melee2", TeamColor.RED, MinionType.MELEE)
    m_red_melee3 = create_minion("r_melee3", TeamColor.RED, MinionType.MELEE)

    blues = [create_minion(f"b{i}", TeamColor.BLUE, MinionType.MELEE) for i in range(6)]

    battle_state.teams[TeamColor.RED].minions.extend([m_red_heavy, m_red_melee1, m_red_melee2, m_red_melee3])
    battle_state.teams[TeamColor.BLUE].minions.extend(blues)

    extra_hexes = [Hex(q=10, r=i, s=-10-i) for i in range(10)]
    battle_state.board.zones["zone1"].hexes.update(extra_hexes)

    battle_state.move_unit(m_red_heavy.id, Hex(q=0,r=0,s=0))
    battle_state.move_unit(m_red_melee1.id, Hex(q=1,r=-1,s=0))
    battle_state.move_unit(m_red_melee2.id, Hex(q=1,r=0,s=-1))
    battle_state.move_unit(m_red_melee3.id, extra_hexes[6])
    for i, m in enumerate(blues):
        battle_state.move_unit(m.id, extra_hexes[i])

    step = EndPhaseStep()
    push_steps(battle_state, [step])

    # Round 1: choose first minion to remove
    req = process_resolution_stack(battle_state)
    assert req is not None
    assert req["type"] == "SELECT_UNIT"
    valid1 = req["valid_options"]
    assert "r_heavy" not in valid1
    assert len(valid1) == 3  # 3 melee options

    # Choose to remove melee1
    battle_state.execution_stack[-1].pending_input = {"selection": "r_melee1"}

    # Round 2: choose second minion to remove
    req2 = process_resolution_stack(battle_state)
    assert req2 is not None
    assert req2["type"] == "SELECT_UNIT"
    valid2 = req2["valid_options"]
    assert "r_heavy" not in valid2
    assert "r_melee1" not in valid2  # already removed
    assert len(valid2) == 2  # melee2, melee3

    # Choose to remove melee2
    battle_state.execution_stack[-1].pending_input = {"selection": "r_melee2"}
    process_resolution_stack(battle_state)

    # Verify final state
    assert "r_melee1" not in battle_state.unit_locations
    assert "r_melee2" not in battle_state.unit_locations
    assert m_red_heavy.id in battle_state.unit_locations
    assert m_red_melee3.id in battle_state.unit_locations

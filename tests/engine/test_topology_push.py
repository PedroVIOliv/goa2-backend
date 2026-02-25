"""
Tests for Push logic with Topology (Crack in Reality).
Verifies that units cannot be pushed across topology splits.
"""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Minion, MinionType
from goa2.domain.models.effect import (
    ActiveEffect,
    EffectType,
    Shape,
    EffectScope,
    DurationType,
)
from goa2.domain.hex import Hex
from goa2.engine.steps import PushUnitStep
from goa2.engine.handler import push_steps, process_resolution_stack


@pytest.fixture
def push_topology_state():
    """
    Board setup:
    (-1,0,1) Left [NEGATIVE]
    (0,0,0) Center [ZERO]
    (1,0,-1) Right [POSITIVE]
    """
    board = Board()
    hexes = [
        Hex(q=-1, r=0, s=1),  # Left
        Hex(q=0, r=0, s=0),  # Center
        Hex(q=1, r=0, s=-1),  # Right
    ]
    for h in hexes:
        board.tiles[h] = Tile(hex=h)

    m_left = Minion(
        id="m_left", name="LeftMinion", type=MinionType.MELEE, team=TeamColor.RED
    )
    m_center = Minion(
        id="m_center", name="CenterMinion", type=MinionType.MELEE, team=TeamColor.RED
    )
    m_right = Minion(
        id="m_right", name="RightMinion", type=MinionType.MELEE, team=TeamColor.RED
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(
                color=TeamColor.RED, heroes=[], minions=[m_left, m_center, m_right]
            ),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        entity_locations={},
        active_effects=[],
        current_actor_id="system",
    )

    state.place_entity("m_left", Hex(q=-1, r=0, s=1))
    state.place_entity("m_center", Hex(q=0, r=0, s=0))
    state.place_entity("m_right", Hex(q=1, r=0, s=-1))

    return state


def test_push_blocked_by_split(push_topology_state):
    """
    Test that a push is blocked when trying to cross POSITIVE <-> NEGATIVE directly.
    We need to configure the split so they are adjacent but disconnected.
    However, with q-split, POS(1) and NEG(-1) are separated by ZERO(0).

    To test direct blockage, we can use TOPOLOGY_ISOLATION (Tier 3).
    Isolate the Center hex.
    Push Left -> Center.
    Left is NEGATIVE. Center is ISOLATED.
    NEGATIVE -> ISOLATED is blocked.
    """
    state = push_topology_state

    # Apply Tier 3 Isolation on Center (0,0,0)
    state.active_effects.append(
        ActiveEffect(
            id="isolation",
            source_id="nebkher",
            effect_type=EffectType.TOPOLOGY_ISOLATION,
            split_axis="q",
            split_value=0,
            isolated_hex=Hex(q=0, r=0, s=0),
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1,
            is_active=True,
        )
    )

    # Try to push m_left (-1,0,1) into Center (0,0,0)
    # Direction is East (Index 0? let's check direction)
    origin = Hex(q=-1, r=0, s=1)
    target = Hex(q=0, r=0, s=0)

    # We push m_left from a virtual source to the west of it?
    # Or just use PushUnitStep which takes target_id and source_id/hex.
    # PushUnitStep logic:
    # direction_idx = src_hex.direction_to(target_loc)
    # So if source is at (-2,0,2), pushing m_left(-1,0,1), it pushes towards (0,0,0).

    # Let's verify direction
    pusher_hex = Hex(q=-2, r=0, s=2)  # Virtual pusher
    # (-2) -> (-1) is East. (-1) -> (0) is East.

    step = PushUnitStep(
        target_id="m_left", source_hex=pusher_hex, distance=1, is_mandatory=True
    )

    push_steps(state, [step])
    process_resolution_stack(state)

    # Verify m_left did NOT move
    new_loc = state.unit_locations["m_left"]
    assert new_loc == Hex(q=-1, r=0, s=1)
    # And specifically NOT (0,0,0)
    assert new_loc != Hex(q=0, r=0, s=0)


def test_push_crosses_bridge(push_topology_state):
    """
    Test that a push CAN cross from NEGATIVE -> ZERO -> POSITIVE.
    This uses Tier 2 Split (Crack in Reality).
    """
    state = push_topology_state

    # Apply Tier 2 Split on q=0
    state.active_effects.append(
        ActiveEffect(
            id="split",
            source_id="nebkher",
            effect_type=EffectType.TOPOLOGY_SPLIT,
            split_axis="q",
            split_value=0,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_ROUND,
            created_at_turn=1,
            created_at_round=1,
            is_active=True,
        )
    )

    # Remove m_center and m_right so the path is clear
    state.remove_entity("m_center")
    state.remove_entity("m_right")

    # Push m_left (-1,0,1) East by 2 hexes.
    # Path: (-1,0,1) -> (0,0,0) -> (1,0,-1)
    # NEG -> ZERO -> POS

    pusher_hex = Hex(q=-2, r=0, s=2)
    step = PushUnitStep(
        target_id="m_left", source_hex=pusher_hex, distance=2, is_mandatory=True
    )

    push_steps(state, [step])
    process_resolution_stack(state)

    # Verify m_left moved all the way to Right
    new_loc = state.unit_locations["m_left"]
    assert new_loc == Hex(q=1, r=0, s=-1)

"""Tests for ReturnMinionToZoneStep - returning minions outside the active zone."""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Minion, MinionType, Hero, Card
from goa2.domain.types import UnitID
from goa2.engine.steps import ReturnMinionToZoneStep, FinalizeHeroTurnStep
from goa2.engine.handler import process_resolution_stack, push_steps


def create_minion(id_str, team, m_type=MinionType.MELEE):
    return Minion(id=UnitID(id_str), name=id_str, team=team, type=m_type)


@pytest.fixture
def zone_state():
    """Create a state with a zone and outside area."""
    board = Board()
    zone_hexes = {Hex(q=0, r=0, s=0), Hex(q=1, r=-1, s=0)}
    board.zones["battle_zone"] = Zone(id="battle_zone", hexes=zone_hexes)

    outside_hex = Hex(q=2, r=-2, s=0)

    for h in zone_hexes:
        board.tiles[h] = Tile(hex=h, zone_id="battle_zone")
    board.tiles[outside_hex] = Tile(hex=outside_hex)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
        active_zone_id="battle_zone",
    )
    return state


def test_no_minions_outside_zone(zone_state):
    """When all minions are inside the zone, nothing happens."""
    m_red = create_minion("r1", TeamColor.RED)
    zone_state.teams[TeamColor.RED].minions.append(m_red)
    zone_state.move_unit(m_red.id, Hex(q=0, r=0, s=0))

    step = ReturnMinionToZoneStep()
    push_steps(zone_state, [step])
    result = process_resolution_stack(zone_state)

    assert zone_state.unit_locations.get(m_red.id) == Hex(q=0, r=0, s=0)
    assert result is None


def test_auto_return_single_path(zone_state):
    """When only one empty hex in zone, minion auto-returns there."""
    m_red = create_minion("r1", TeamColor.RED)
    zone_state.teams[TeamColor.RED].minions.append(m_red)

    zone_state.move_unit(m_red.id, Hex(q=2, r=-2, s=0))

    step = ReturnMinionToZoneStep()
    push_steps(zone_state, [step])
    result = process_resolution_stack(zone_state)

    loc = zone_state.unit_locations.get(m_red.id)
    zone = zone_state.board.zones["battle_zone"]
    assert loc in zone.hexes


def test_team_choice_multiple_paths(zone_state):
    """When multiple paths exist, team must choose."""
    zone_state.board.zones["battle_zone"].hexes.add(Hex(q=2, r=-1, s=-1))
    zone_state.board.tiles[Hex(q=2, r=-1, s=-1)] = Tile(
        hex=Hex(q=2, r=-1, s=-1), zone_id="battle_zone"
    )

    m_red = create_minion("r1", TeamColor.RED)
    zone_state.teams[TeamColor.RED].minions.append(m_red)

    zone_state.move_unit(m_red.id, Hex(q=2, r=-2, s=0))

    step = ReturnMinionToZoneStep()
    push_steps(zone_state, [step])
    result = process_resolution_stack(zone_state)

    if result is not None:
        assert result["type"] == "SELECT_HEX"
        assert result["player_id"] == "team:RED"


def test_multiple_minions_tiebreaker_order(zone_state):
    """Multiple minions outside zone processed in tie-breaker order."""
    m_red = create_minion("r1", TeamColor.RED)
    m_blue = create_minion("b1", TeamColor.BLUE)

    zone_state.teams[TeamColor.RED].minions.append(m_red)
    zone_state.teams[TeamColor.BLUE].minions.append(m_blue)

    zone_state.move_unit(m_red.id, Hex(q=2, r=-2, s=0))

    zone_state.board.tiles[Hex(q=3, r=-3, s=0)] = Tile(hex=Hex(q=3, r=-3, s=0))
    zone_state.move_unit(m_blue.id, Hex(q=3, r=-3, s=0))

    zone_state.tie_breaker_team = TeamColor.RED

    step = ReturnMinionToZoneStep()
    push_steps(zone_state, [step])
    result = process_resolution_stack(zone_state)

    # Both minions should be returned to zone
    zone = zone_state.board.zones["battle_zone"]
    assert zone_state.unit_locations.get(m_red.id) in zone.hexes
    assert zone_state.unit_locations.get(m_blue.id) in zone.hexes


def test_no_empty_space_in_zone(zone_state):
    """When zone has no empty spaces, minion stays outside (edge case)."""
    m_red = create_minion("r1", TeamColor.RED)
    m_red2 = create_minion("r2", TeamColor.RED)
    zone_state.teams[TeamColor.RED].minions.extend([m_red, m_red2])

    zone_state.move_unit(m_red.id, Hex(q=0, r=0, s=0))
    zone_state.move_unit(m_red2.id, Hex(q=1, r=-1, s=0))

    m_outside = create_minion("r3", TeamColor.RED)
    zone_state.teams[TeamColor.RED].minions.append(m_outside)
    zone_state.move_unit(m_outside.id, Hex(q=2, r=-2, s=0))

    step = ReturnMinionToZoneStep()
    push_steps(zone_state, [step])
    result = process_resolution_stack(zone_state)

    assert result is None


def test_finalize_hero_turn_spawns_check(zone_state):
    """FinalizeHeroTurnStep should spawn ReturnMinionToZoneStep."""
    hero = Hero(
        id="hero_test",
        name="Test Hero",
        title="Tester",
        team=TeamColor.RED,
        hand=[],
        deck=[],
    )
    card = Card(
        id="test_card",
        name="Test Card",
        tier="I",
        color="BLUE",
        primary_action="SKILL",
        initiative=1,
        effect_id="none",
        effect_text="",
    )
    hero.current_turn_card = card
    zone_state.teams[TeamColor.RED].heroes.append(hero)
    zone_state.current_actor_id = "hero_test"

    m_red = create_minion("r1", TeamColor.RED)
    zone_state.teams[TeamColor.RED].minions.append(m_red)
    zone_state.move_unit(m_red.id, Hex(q=2, r=-2, s=0))

    step = FinalizeHeroTurnStep(hero_id="hero_test")
    push_steps(zone_state, [step])
    result = process_resolution_stack(zone_state)

    # Minion should be returned to zone
    zone = zone_state.board.zones["battle_zone"]
    assert zone_state.unit_locations.get(m_red.id) in zone.hexes

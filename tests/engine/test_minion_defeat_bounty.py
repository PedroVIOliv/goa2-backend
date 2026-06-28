"""Tests for the MINION_DEFEAT_BOUNTY listener used by Swift's Mark for Death
and Hunting Season ("Next turn: the first N times an enemy minion in radius is
defeated, gain 1 coin").

Any player's defeat of an enemy minion within radius of the beneficiary (Swift)
counts, up to N times. Radius is measured from the beneficiary's current hex.
"""

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import DurationType, Hero, Minion, MinionType, Team, TeamColor
from goa2.domain.models.effect import ActiveEffect, EffectScope, EffectType, Shape
from goa2.domain.state import GameState
from goa2.domain.tile import Tile
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import DefeatUnitStep


def _state_with_bounty(max_value: int, radius: int = 3):
    board = Board()
    hexes = [Hex(q=q, r=0, s=-q) for q in range(8)]
    for h in hexes:
        board.tiles[h] = Tile(hex=h)
    board.zones["Mid"] = Zone(id="Mid", label="Mid", hexes=set(hexes))

    swift = Hero(id="hero_swift", name="Swift", team=TeamColor.RED, deck=[])
    ally = Hero(id="hero_ally", name="Ally", team=TeamColor.RED, deck=[])
    m1 = Minion(id="m1", name="M1", type=MinionType.MELEE, team=TeamColor.BLUE)
    m2 = Minion(id="m2", name="M2", type=MinionType.MELEE, team=TeamColor.BLUE)
    m_far = Minion(id="m_far", name="MF", type=MinionType.MELEE, team=TeamColor.BLUE)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[swift, ally], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[m1, m2, m_far]),
        },
        current_actor_id="hero_ally",
        active_zone_id="Mid",
    )
    state.place_entity("hero_swift", Hex(q=0, r=0, s=0))
    state.place_entity("hero_ally", Hex(q=6, r=0, s=-6))
    state.place_entity("m1", Hex(q=1, r=0, s=-1))  # within radius of Swift
    state.place_entity("m2", Hex(q=2, r=0, s=-2))  # within radius of Swift
    state.place_entity("m_far", Hex(q=7, r=0, s=-7))  # outside Swift's radius

    state.active_effects.append(
        ActiveEffect(
            id="bounty_1",
            source_id="hero_swift",
            effect_type=EffectType.MINION_DEFEAT_BOUNTY,
            scope=EffectScope(shape=Shape.RADIUS, range=radius, origin_id="hero_swift"),
            duration=DurationType.THIS_TURN,
            created_at_turn=state.turn,
            created_at_round=state.round,
            is_active=True,
            max_value=max_value,
        )
    )
    return state


def test_enemy_minion_defeated_in_radius_grants_swift_one_coin():
    state = _state_with_bounty(max_value=1)
    swift = state.get_hero("hero_swift")
    before = swift.gold

    push_steps(state, [DefeatUnitStep(victim_id="m1", killer_id="hero_ally")])
    process_stack(state)

    assert swift.gold == before + 1


def test_bounty_count_caps_total_coins():
    state = _state_with_bounty(max_value=1)
    swift = state.get_hero("hero_swift")
    before = swift.gold

    push_steps(state, [DefeatUnitStep(victim_id="m1", killer_id="hero_ally")])
    process_stack(state)
    push_steps(state, [DefeatUnitStep(victim_id="m2", killer_id="hero_ally")])
    process_stack(state)

    # Only the first defeat pays out (N=1).
    assert swift.gold == before + 1


def test_minion_defeated_outside_radius_grants_nothing():
    state = _state_with_bounty(max_value=2)
    swift = state.get_hero("hero_swift")
    before = swift.gold

    push_steps(state, [DefeatUnitStep(victim_id="m_far", killer_id="hero_ally")])
    process_stack(state)

    assert swift.gold == before


def test_hunting_season_pays_twice():
    state = _state_with_bounty(max_value=2)
    swift = state.get_hero("hero_swift")
    before = swift.gold

    push_steps(state, [DefeatUnitStep(victim_id="m1", killer_id="hero_ally")])
    process_stack(state)
    push_steps(state, [DefeatUnitStep(victim_id="m2", killer_id="hero_ally")])
    process_stack(state)

    assert swift.gold == before + 2

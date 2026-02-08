"""Tests for hero defeat cleanup and respawn mechanics."""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import Team, TeamColor, Hero, Card, CardState
from goa2.domain.models.card import ActionType, CardTier, CardColor
from goa2.domain.models.effect import (
    ActiveEffect,
    EffectType,
    EffectScope,
    Shape,
    DurationType,
    AffectsFilter,
)
from goa2.domain.models.spawn import SpawnPoint, SpawnType
from goa2.domain.types import HeroID, UnitID
from goa2.domain.hex import Hex
from goa2.engine.steps import (
    DefeatUnitStep,
    RespawnHeroStep,
    ResolveCardStep,
    FinalizeHeroTurnStep,
)
from goa2.engine.handler import process_resolution_stack, push_steps


def make_card(card_id="card_1", initiative=5):
    return Card(
        id=card_id,
        name=card_id,
        tier=CardTier.I,
        color=CardColor.RED,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        secondary_actions={},
        effect_id="none",
        effect_text="Test card",
        initiative=initiative,
    )


def make_hero(hero_id, team, level=1):
    hero = Hero(id=HeroID(hero_id), name=hero_id, team=team, deck=[])
    hero.level = level
    hero.gold = 0
    return hero


# ---------------------------------------------------------------------------
# 1. Defeat cancels active effects from the defeated hero
# ---------------------------------------------------------------------------


def test_defeat_cancels_active_effects():
    victim = make_hero("Victim", TeamColor.BLUE)
    killer = make_hero("Killer", TeamColor.RED)

    state = GameState(
        board=Board(),
        teams={
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[victim], minions=[], life_counters=5
            ),
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[killer], minions=[]),
        },
    )
    state.move_unit(victim.id, Hex(q=0, r=0, s=0))
    state.move_unit(killer.id, Hex(q=1, r=0, s=-1))

    # Add effects from the victim
    effect = ActiveEffect(
        id="eff_1",
        source_id="Victim",
        effect_type=EffectType.AREA_STAT_MODIFIER,
        scope=EffectScope(shape=Shape.RADIUS, range=2),
        duration=DurationType.THIS_TURN,
        created_at_turn=1,
        created_at_round=1,
        is_active=True,
    )
    state.active_effects.append(effect)
    assert len(state.active_effects) == 1

    push_steps(state, [DefeatUnitStep(victim_id="Victim", killer_id="Killer")])
    process_resolution_stack(state)

    assert len(state.active_effects) == 0


# ---------------------------------------------------------------------------
# 2. Defeat resolves unresolved card without action
# ---------------------------------------------------------------------------


def test_defeat_resolves_unresolved_card():
    victim = make_hero("Victim", TeamColor.BLUE)
    killer = make_hero("Killer", TeamColor.RED)

    card = make_card("card_1")
    victim.hand.append(card)
    victim.play_card(card)
    assert victim.current_turn_card is not None

    state = GameState(
        board=Board(),
        teams={
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[victim], minions=[], life_counters=5
            ),
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[killer], minions=[]),
        },
    )
    state.move_unit(victim.id, Hex(q=0, r=0, s=0))

    push_steps(state, [DefeatUnitStep(victim_id="Victim", killer_id="Killer")])
    process_resolution_stack(state)

    assert victim.current_turn_card is None
    assert len(victim.played_cards) == 1
    assert victim.played_cards[0].state == CardState.RESOLVED


# ---------------------------------------------------------------------------
# 3. Defeat removes hero from unresolved_hero_ids
# ---------------------------------------------------------------------------


def test_defeat_removes_from_unresolved_hero_ids():
    victim = make_hero("Victim", TeamColor.BLUE)
    killer = make_hero("Killer", TeamColor.RED)

    state = GameState(
        board=Board(),
        teams={
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[victim], minions=[], life_counters=5
            ),
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[killer], minions=[]),
        },
    )
    state.move_unit(victim.id, Hex(q=0, r=0, s=0))
    state.unresolved_hero_ids = [HeroID("Victim"), HeroID("Killer")]

    push_steps(state, [DefeatUnitStep(victim_id="Victim", killer_id="Killer")])
    process_resolution_stack(state)

    assert HeroID("Victim") not in state.unresolved_hero_ids
    assert HeroID("Killer") in state.unresolved_hero_ids


# ---------------------------------------------------------------------------
# 4. Respawn uses is_obstacle_for_actor to filter spawn points
# ---------------------------------------------------------------------------


def _make_respawn_state(spawn_hex, hero_team=TeamColor.BLUE):
    """Helper to create a state with one hero spawn point."""
    hero = make_hero("Hero", hero_team)
    zone = Zone(
        id="base",
        hexes={spawn_hex, Hex(q=0, r=1, s=-1), Hex(q=1, r=0, s=-1)},
        spawn_points=[
            SpawnPoint(location=spawn_hex, team=hero_team, type=SpawnType.HERO)
        ],
    )
    board = Board(
        zones={"base": zone},
        spawn_points=[
            SpawnPoint(location=spawn_hex, team=hero_team, type=SpawnType.HERO)
        ],
    )
    board.populate_tiles_from_zones()

    state = GameState(
        board=board,
        teams={
            hero_team: Team(
                color=hero_team, heroes=[hero], minions=[], life_counters=5
            ),
        },
    )
    # Hero is NOT on the board (defeated)
    return state, hero


def test_respawn_filters_occupied_spawn_points():
    spawn_hex = Hex(q=0, r=0, s=0)
    state, hero = _make_respawn_state(spawn_hex)

    # Place another unit on the spawn point to block it
    blocker = make_hero("Blocker", TeamColor.RED)
    state.teams[TeamColor.RED] = Team(color=TeamColor.RED, heroes=[blocker], minions=[])
    state.move_unit(blocker.id, spawn_hex)

    step = RespawnHeroStep(hero_id="Hero")
    result = step.resolve(state, {})

    # Spawn point is blocked, but BFS fallback finds nearby hexes
    assert result.requires_input is True
    assert spawn_hex not in result.input_request["valid_hexes"]


def test_respawn_offers_empty_spawn_point():
    spawn_hex = Hex(q=0, r=0, s=0)
    state, hero = _make_respawn_state(spawn_hex)

    step = RespawnHeroStep(hero_id="Hero")
    result = step.resolve(state, {})

    assert result.requires_input is True
    assert result.input_request["type"] == "CHOOSE_RESPAWN"
    assert spawn_hex.model_dump() in result.input_request["valid_hexes"]


# ---------------------------------------------------------------------------
# 5. Respawn BFS fallback when all spawn points are obstacles
# ---------------------------------------------------------------------------


def test_respawn_bfs_fallback():
    spawn_hex = Hex(q=0, r=0, s=0)
    nearby_hex = Hex(q=0, r=1, s=-1)
    hero = make_hero("Hero", TeamColor.BLUE)

    zone = Zone(
        id="base",
        hexes={spawn_hex, nearby_hex, Hex(q=1, r=0, s=-1)},
        spawn_points=[
            SpawnPoint(location=spawn_hex, team=TeamColor.BLUE, type=SpawnType.HERO)
        ],
    )
    board = Board(
        zones={"base": zone},
        spawn_points=[
            SpawnPoint(location=spawn_hex, team=TeamColor.BLUE, type=SpawnType.HERO)
        ],
    )
    board.populate_tiles_from_zones()

    blocker = make_hero("Blocker", TeamColor.RED)
    state = GameState(
        board=board,
        teams={
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[hero], minions=[], life_counters=5
            ),
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[blocker], minions=[]),
        },
    )
    # Block the spawn point
    state.move_unit(blocker.id, spawn_hex)

    step = RespawnHeroStep(hero_id="Hero")
    result = step.resolve(state, {})

    # BFS should find a nearby empty hex
    assert result.requires_input is True
    assert len(result.input_request["valid_hexes"]) > 0
    # The valid hexes should NOT include the blocked spawn point
    assert spawn_hex not in result.input_request["valid_hexes"]


# ---------------------------------------------------------------------------
# 6. Hero who skips respawn resolves card without action
# ---------------------------------------------------------------------------


def test_skip_respawn_skips_card_action():
    hero = make_hero("Hero", TeamColor.BLUE)
    card = make_card("card_1")
    hero.hand.append(card)
    hero.play_card(card)

    state = GameState(
        board=Board(),
        teams={
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[hero], minions=[], life_counters=5
            ),
        },
    )
    # Hero is NOT on the board (didn't respawn)

    step = ResolveCardStep(hero_id="Hero")
    result = step.resolve(state, {})

    # Should skip without requiring input or spawning action steps
    assert result.is_finished is True
    assert result.requires_input is False
    assert not result.new_steps


# ---------------------------------------------------------------------------
# 7. Full flow: defeat → respawn offered → act
# ---------------------------------------------------------------------------


def test_full_defeat_respawn_flow():
    """
    Defeat a hero, then on their next turn they should get a respawn step
    before ResolveCardStep.
    """
    spawn_hex = Hex(q=0, r=0, s=0)
    hero = make_hero("Hero", TeamColor.BLUE)
    card = make_card("card_1")
    hero.hand.append(card)
    hero.play_card(card)

    zone = Zone(
        id="base",
        hexes={spawn_hex, Hex(q=1, r=0, s=-1)},
        spawn_points=[
            SpawnPoint(location=spawn_hex, team=TeamColor.BLUE, type=SpawnType.HERO)
        ],
    )
    board = Board(
        zones={"base": zone},
        spawn_points=[
            SpawnPoint(location=spawn_hex, team=TeamColor.BLUE, type=SpawnType.HERO)
        ],
    )
    board.populate_tiles_from_zones()

    state = GameState(
        board=board,
        teams={
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[hero], minions=[], life_counters=5
            ),
        },
    )
    # Hero is off board (defeated) — simulate the respawn→resolve→finalize flow
    push_steps(
        state,
        [
            RespawnHeroStep(hero_id="Hero"),
            ResolveCardStep(hero_id="Hero"),
            FinalizeHeroTurnStep(hero_id="Hero"),
        ],
    )

    # First process should hit RespawnHeroStep and request input
    result = process_resolution_stack(state)
    assert result is not None
    assert result["type"] == "CHOOSE_RESPAWN"

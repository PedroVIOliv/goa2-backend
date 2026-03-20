"""Tests for Dodger's Darkest Ritual card effect (GainItemStep)."""

import pytest

import goa2.scripts.dodger_effects  # noqa: F401 — registers effects

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardTier,
    Hero,
    Team,
    TeamColor,
)
from goa2.domain.models.enums import StatType
from goa2.domain.models.spawn import MinionType, SpawnPoint, SpawnType
from goa2.domain.state import GameState
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.stats import compute_card_stats


def _make_skill_card():
    return Card(
        id="darkest_ritual_card",
        name="Darkest Ritual",
        tier=CardTier.III,
        color=CardColor.GREEN,
        initiative=3,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        is_ranged=False,
        radius_value=3,
        effect_id="darkest_ritual",
        effect_text="",
        is_facedown=False,
    )


def _make_state(*, num_empty_spawns: int = 2, hero_level: int = 1):
    """Build a state with a configurable number of empty spawn points near the hero."""
    board = Board()
    hexes = set()
    for q in range(-4, 5):
        for r in range(-4, 5):
            s = -q - r
            if abs(s) <= 4:
                hexes.add(Hex(q=q, r=r, s=s))
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    # Place spawn points on tiles near the origin (within radius 3)
    spawn_hexes = [
        Hex(q=1, r=0, s=-1),
        Hex(q=0, r=1, s=-1),
        Hex(q=-1, r=1, s=0),
    ]
    for i, h in enumerate(spawn_hexes):
        sp = SpawnPoint(
            location=h,
            team=TeamColor.RED,
            type=SpawnType.MINION,
            minion_type=MinionType.MELEE,
        )
        board.tiles[h].spawn_point = sp
        board.spawn_points.append(sp)

    card = _make_skill_card()
    hero = Hero(
        id="hero_dodger",
        name="Dodger",
        team=TeamColor.RED,
        deck=[],
        level=hero_level,
    )
    hero.current_turn_card = card

    enemy = Hero(
        id="enemy",
        name="Enemy",
        team=TeamColor.BLUE,
        deck=[],
        level=1,
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.place_entity("hero_dodger", Hex(q=0, r=0, s=0))
    state.place_entity("enemy", Hex(q=3, r=0, s=-3))
    state.active_zone_id = "z1"
    state.current_actor_id = "hero_dodger"

    # Occupy some spawn points to control count
    # We have 3 spawn points; occupy (3 - num_empty_spawns) of them
    occupy_count = max(0, 3 - num_empty_spawns)
    for i in range(occupy_count):
        # Place a dummy entity on the spawn hex to mark it occupied
        dummy_id = f"blocker_{i}"
        dummy = Hero(
            id=dummy_id,
            name=f"Blocker {i}",
            team=TeamColor.BLUE,
            deck=[],
            level=1,
        )
        state.teams[TeamColor.BLUE].heroes.append(dummy)
        state.place_entity(dummy_id, spawn_hexes[i])

    return state


def _run_effect(state):
    """Build and execute the darkest_ritual effect steps."""
    hero = state.get_hero("hero_dodger")
    card = hero.current_turn_card
    effect = CardEffectRegistry.get("darkest_ritual")
    stats = compute_card_stats(state, hero.id, card)
    steps = effect.build_steps(state, hero, card, stats)
    if not steps:
        return
    push_steps(state, steps)
    result = process_resolution_stack(state)
    while result is not None:
        result = process_resolution_stack(state)


class TestDarkestRitualCoins:
    def test_gains_2_coins_with_2_empty_spawns(self):
        state = _make_state(num_empty_spawns=2, hero_level=1)
        hero = state.get_hero("hero_dodger")
        assert hero.gold == 0

        _run_effect(state)

        assert hero.gold == 2

    def test_gains_2_coins_with_3_empty_spawns(self):
        state = _make_state(num_empty_spawns=3, hero_level=1)
        hero = state.get_hero("hero_dodger")

        _run_effect(state)

        assert hero.gold == 2

    def test_no_coins_with_1_empty_spawn(self):
        state = _make_state(num_empty_spawns=1, hero_level=1)
        hero = state.get_hero("hero_dodger")

        _run_effect(state)

        assert hero.gold == 0

    def test_no_coins_with_0_empty_spawns(self):
        state = _make_state(num_empty_spawns=0, hero_level=1)
        hero = state.get_hero("hero_dodger")

        _run_effect(state)

        assert hero.gold == 0


class TestDarkestRitualItem:
    def test_gains_attack_item_at_level_8(self):
        state = _make_state(num_empty_spawns=2, hero_level=8)
        hero = state.get_hero("hero_dodger")
        assert hero.items.get(StatType.ATTACK, 0) == 0

        _run_effect(state)

        assert hero.items[StatType.ATTACK] == 1
        assert hero.gold == 2  # coins too

    def test_no_item_at_level_7(self):
        state = _make_state(num_empty_spawns=2, hero_level=7)
        hero = state.get_hero("hero_dodger")

        _run_effect(state)

        assert hero.items.get(StatType.ATTACK, 0) == 0
        assert hero.gold == 2  # still gets coins

    def test_no_item_at_level_1(self):
        state = _make_state(num_empty_spawns=2, hero_level=1)
        hero = state.get_hero("hero_dodger")

        _run_effect(state)

        assert hero.items.get(StatType.ATTACK, 0) == 0

    def test_no_item_when_not_enough_spawns(self):
        """Even at level 8, no item if the spawn condition isn't met."""
        state = _make_state(num_empty_spawns=1, hero_level=8)
        hero = state.get_hero("hero_dodger")

        _run_effect(state)

        assert hero.items.get(StatType.ATTACK, 0) == 0
        assert hero.gold == 0


class TestGainItemStep:
    def test_gain_item_step_directly(self):
        """Test GainItemStep in isolation."""
        from goa2.engine.steps import GainItemStep, SetContextFlagStep

        state = _make_state(num_empty_spawns=0, hero_level=1)
        hero = state.get_hero("hero_dodger")

        push_steps(
            state,
            [
                SetContextFlagStep(key="self", value="hero_dodger"),
                GainItemStep(hero_key="self", stat_type=StatType.ATTACK),
            ],
        )
        result = process_resolution_stack(state)
        while result is not None:
            result = process_resolution_stack(state)

        assert hero.items[StatType.ATTACK] == 1

    def test_gain_item_step_stacks(self):
        """Running GainItemStep twice increments the item count."""
        from goa2.engine.steps import GainItemStep, SetContextFlagStep

        state = _make_state(num_empty_spawns=0, hero_level=1)
        hero = state.get_hero("hero_dodger")

        push_steps(
            state,
            [
                SetContextFlagStep(key="self", value="hero_dodger"),
                GainItemStep(hero_key="self", stat_type=StatType.ATTACK),
                GainItemStep(hero_key="self", stat_type=StatType.DEFENSE),
            ],
        )
        result = process_resolution_stack(state)
        while result is not None:
            result = process_resolution_stack(state)

        assert hero.items[StatType.ATTACK] == 1
        assert hero.items[StatType.DEFENSE] == 1

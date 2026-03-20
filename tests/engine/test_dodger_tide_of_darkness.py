"""Tests for Dodger's Tide of Darkness ultimate card effect."""

import pytest

import goa2.scripts.dodger_effects  # noqa: F401 — registers effects
from goa2.scripts.dodger_effects import (
    _has_tide_of_darkness,
    _count_empty_spawn_points,
    _is_adjacent_to_empty_spawn_in_battle_zone,
)

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardState,
    CardTier,
    Hero,
    Team,
    TeamColor,
)
from goa2.domain.models.enums import StatType
from goa2.domain.models.spawn import MinionType, SpawnPoint, SpawnType
from goa2.domain.state import GameState
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.filters import BattleZoneFilter, SpawnPointTeamFilter
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.stats import compute_card_stats


def _make_ultimate_card():
    return Card(
        id="tide_of_darkness",
        name="Tide of Darkness",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        is_ranged=False,
        effect_id="tide_of_darkness",
        effect_text="",
        is_facedown=False,
        state=CardState.PASSIVE,
    )


def _make_state(*, hero_level: int = 8, num_spawn_points: int = 0, with_ultimate: bool = True):
    """Build a state with configurable spawn points and hero level.

    By default: Dodger at level 8 with ultimate, NO spawn points on the board,
    so any spawn-point behavior must come from the Tide override.
    """
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

    # Optionally place spawn points near origin
    spawn_hexes = [
        Hex(q=1, r=0, s=-1),
        Hex(q=0, r=1, s=-1),
        Hex(q=-1, r=1, s=0),
    ]
    for i in range(min(num_spawn_points, len(spawn_hexes))):
        h = spawn_hexes[i]
        sp = SpawnPoint(
            location=h,
            team=TeamColor.RED,
            type=SpawnType.MINION,
            minion_type=MinionType.MELEE,
        )
        board.tiles[h].spawn_point = sp
        board.spawn_points.append(sp)

    hero = Hero(
        id="hero_dodger",
        name="Dodger",
        team=TeamColor.RED,
        deck=[],
        level=hero_level,
    )
    if with_ultimate:
        hero.ultimate_card = _make_ultimate_card()

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

    return state


# =============================================================================
# _has_tide_of_darkness utility
# =============================================================================


class TestHasTideOfDarkness:
    def test_true_when_dodger_level_8_with_ultimate(self):
        state = _make_state(hero_level=8, with_ultimate=True)
        assert _has_tide_of_darkness(state) is True

    def test_true_at_level_9(self):
        state = _make_state(hero_level=9, with_ultimate=True)
        assert _has_tide_of_darkness(state) is True

    def test_false_at_level_7(self):
        state = _make_state(hero_level=7, with_ultimate=True)
        assert _has_tide_of_darkness(state) is False

    def test_false_without_ultimate_card(self):
        state = _make_state(hero_level=8, with_ultimate=False)
        assert _has_tide_of_darkness(state) is False

    def test_false_when_no_current_actor(self):
        state = _make_state(hero_level=8, with_ultimate=True)
        state.current_actor_id = None
        assert _has_tide_of_darkness(state) is False

    def test_false_for_different_hero_as_actor(self):
        """Even if Dodger is level 8 with ult, override doesn't apply for other actors."""
        state = _make_state(hero_level=8, with_ultimate=True)
        state.current_actor_id = "enemy"
        assert _has_tide_of_darkness(state) is False


# =============================================================================
# _count_empty_spawn_points with override
# =============================================================================


class TestCountEmptySpawnPointsWithOverride:
    def test_counts_all_empty_hexes_with_override(self):
        """With Tide active and no spawn points, all unoccupied non-terrain hexes count."""
        state = _make_state(hero_level=8, num_spawn_points=0)
        # radius=1 around origin: 6 neighbors + origin itself is occupied by hero
        # So 6 empty hexes within radius 1
        count = _count_empty_spawn_points(state, "hero_dodger", radius=1)
        assert count == 6

    def test_excludes_occupied_hexes(self):
        """Occupied hexes don't count even with override."""
        state = _make_state(hero_level=8, num_spawn_points=0)
        # Place a blocker on an adjacent hex
        blocker = Hero(id="blocker", name="Blocker", team=TeamColor.BLUE, deck=[], level=1)
        state.teams[TeamColor.BLUE].heroes.append(blocker)
        state.place_entity("blocker", Hex(q=1, r=0, s=-1))
        count = _count_empty_spawn_points(state, "hero_dodger", radius=1)
        assert count == 5  # 6 - 1 occupied

    def test_without_override_only_counts_spawn_points(self):
        """Without Tide active, normal behavior: only spawn points in zone."""
        state = _make_state(hero_level=7, num_spawn_points=3)
        count = _count_empty_spawn_points(state, "hero_dodger", radius=3)
        assert count == 3

    def test_without_override_no_zone_returns_zero(self):
        state = _make_state(hero_level=7, num_spawn_points=3)
        state.active_zone_id = None
        count = _count_empty_spawn_points(state, "hero_dodger", radius=3)
        assert count == 0

    def test_with_override_no_zone_still_counts(self):
        """With Tide active, zone doesn't matter."""
        state = _make_state(hero_level=8, num_spawn_points=0)
        state.active_zone_id = None
        count = _count_empty_spawn_points(state, "hero_dodger", radius=1)
        assert count == 6


# =============================================================================
# _is_adjacent_to_empty_spawn_in_battle_zone with override
# =============================================================================


class TestIsAdjacentToEmptySpawnWithOverride:
    def test_any_empty_neighbor_qualifies_with_override(self):
        """With Tide active, any non-occupied non-terrain neighbor qualifies."""
        state = _make_state(hero_level=8, num_spawn_points=0)
        hero_hex = Hex(q=0, r=0, s=0)
        assert _is_adjacent_to_empty_spawn_in_battle_zone(state, hero_hex, "z1") is True

    def test_false_when_all_neighbors_occupied_with_override(self):
        """Even with Tide, if all neighbors are occupied, returns False."""
        state = _make_state(hero_level=8, num_spawn_points=0)
        hero_hex = Hex(q=0, r=0, s=0)
        # Occupy all 6 neighbors
        neighbors = [
            Hex(q=1, r=0, s=-1), Hex(q=0, r=1, s=-1), Hex(q=-1, r=1, s=0),
            Hex(q=-1, r=0, s=1), Hex(q=0, r=-1, s=1), Hex(q=1, r=-1, s=0),
        ]
        for i, n in enumerate(neighbors):
            bid = f"block_{i}"
            b = Hero(id=bid, name=bid, team=TeamColor.BLUE, deck=[], level=1)
            state.teams[TeamColor.BLUE].heroes.append(b)
            state.place_entity(bid, n)
        assert _is_adjacent_to_empty_spawn_in_battle_zone(state, hero_hex, "z1") is False

    def test_without_override_needs_spawn_point(self):
        """Without Tide, only spawn points qualify."""
        state = _make_state(hero_level=7, num_spawn_points=0)
        hero_hex = Hex(q=0, r=0, s=0)
        # No spawn points, so should be False even though neighbors are empty
        assert _is_adjacent_to_empty_spawn_in_battle_zone(state, hero_hex, "z1") is False

    def test_without_override_with_spawn_point(self):
        state = _make_state(hero_level=7, num_spawn_points=1)
        hero_hex = Hex(q=0, r=0, s=0)
        # spawn point at (1,0,-1) which is adjacent
        assert _is_adjacent_to_empty_spawn_in_battle_zone(state, hero_hex, "z1") is True


# =============================================================================
# BattleZoneFilter with override
# =============================================================================


class TestBattleZoneFilterWithOverride:
    def test_passes_any_hex_with_tile_when_override(self):
        state = _make_state(hero_level=8, num_spawn_points=0)
        f = BattleZoneFilter()
        # A hex far from any zone still passes with override
        h = Hex(q=4, r=0, s=-4)
        assert f.apply(h, state, {}) is True

    def test_fails_for_non_hex(self):
        state = _make_state(hero_level=8, num_spawn_points=0)
        f = BattleZoneFilter()
        assert f.apply("not_a_hex", state, {}) is False

    def test_without_override_normal_zone_check(self):
        state = _make_state(hero_level=7, num_spawn_points=0)
        f = BattleZoneFilter()
        # Hex in z1 should pass
        h = Hex(q=1, r=0, s=-1)
        assert f.apply(h, state, {}) is True

    def test_without_override_no_zone_fails(self):
        state = _make_state(hero_level=7, num_spawn_points=0)
        state.active_zone_id = None
        f = BattleZoneFilter()
        h = Hex(q=1, r=0, s=-1)
        assert f.apply(h, state, {}) is False


# =============================================================================
# SpawnPointTeamFilter with override
# =============================================================================


class TestSpawnPointTeamFilterWithOverride:
    def test_friendly_passes_any_non_terrain_hex_with_override(self):
        state = _make_state(hero_level=8, num_spawn_points=0)
        f = SpawnPointTeamFilter(relation="FRIENDLY")
        h = Hex(q=2, r=0, s=-2)  # No spawn point here
        assert f.apply(h, state, {}) is True

    def test_enemy_fails_with_override(self):
        """Under override, no enemy spawn points exist."""
        state = _make_state(hero_level=8, num_spawn_points=0)
        f = SpawnPointTeamFilter(relation="ENEMY")
        h = Hex(q=2, r=0, s=-2)
        assert f.apply(h, state, {}) is False

    def test_friendly_without_override_needs_spawn_point(self):
        state = _make_state(hero_level=7, num_spawn_points=0)
        f = SpawnPointTeamFilter(relation="FRIENDLY")
        h = Hex(q=2, r=0, s=-2)  # No spawn point
        assert f.apply(h, state, {}) is False

    def test_friendly_without_override_with_matching_spawn(self):
        state = _make_state(hero_level=7, num_spawn_points=1)
        f = SpawnPointTeamFilter(relation="FRIENDLY")
        h = Hex(q=1, r=0, s=-1)  # Has RED spawn point
        assert f.apply(h, state, {}) is True

    def test_fails_for_non_hex(self):
        state = _make_state(hero_level=8, num_spawn_points=0)
        f = SpawnPointTeamFilter(relation="FRIENDLY")
        assert f.apply("not_a_hex", state, {}) is False


# =============================================================================
# Integration: Dark Ritual with Tide active
# =============================================================================


class TestDarkRitualWithTide:
    def test_gains_coins_with_no_actual_spawn_points(self):
        """With Tide active, Dark Ritual should succeed even with 0 spawn points."""
        state = _make_state(hero_level=8, num_spawn_points=0)
        hero = state.get_hero("hero_dodger")
        hero.current_turn_card = Card(
            id="dark_ritual_card",
            name="Dark Ritual",
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=3,
            primary_action=ActionType.SKILL,
            secondary_actions={},
            is_ranged=False,
            radius_value=3,
            effect_id="dark_ritual",
            effect_text="",
            is_facedown=False,
        )
        card = hero.current_turn_card
        assert hero.gold == 0

        effect = CardEffectRegistry.get("dark_ritual")
        stats = compute_card_stats(state, hero.id, card)
        steps = effect.build_steps(state, hero, card, stats)
        assert len(steps) > 0, "Should produce steps with Tide override"

        push_steps(state, steps)
        result = process_resolution_stack(state)
        while result is not None:
            result = process_resolution_stack(state)

        assert hero.gold == 1

    def test_no_coins_without_tide(self):
        """Without Tide, Dark Ritual fails when there are no spawn points."""
        state = _make_state(hero_level=7, num_spawn_points=0)
        hero = state.get_hero("hero_dodger")
        hero.current_turn_card = Card(
            id="dark_ritual_card",
            name="Dark Ritual",
            tier=CardTier.II,
            color=CardColor.GREEN,
            initiative=3,
            primary_action=ActionType.SKILL,
            secondary_actions={},
            is_ranged=False,
            radius_value=3,
            effect_id="dark_ritual",
            effect_text="",
            is_facedown=False,
        )
        card = hero.current_turn_card

        effect = CardEffectRegistry.get("dark_ritual")
        stats = compute_card_stats(state, hero.id, card)
        steps = effect.build_steps(state, hero, card, stats)
        assert len(steps) == 0


# =============================================================================
# Integration: Darkest Ritual with Tide active
# =============================================================================


class TestDarkestRitualWithTide:
    def test_gains_coins_and_item_with_no_spawn_points(self):
        """With Tide active at level 8, Darkest Ritual gains coins + item."""
        state = _make_state(hero_level=8, num_spawn_points=0)
        hero = state.get_hero("hero_dodger")
        hero.current_turn_card = Card(
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
        card = hero.current_turn_card
        assert hero.gold == 0

        effect = CardEffectRegistry.get("darkest_ritual")
        stats = compute_card_stats(state, hero.id, card)
        steps = effect.build_steps(state, hero, card, stats)
        assert len(steps) > 0

        push_steps(state, steps)
        result = process_resolution_stack(state)
        while result is not None:
            result = process_resolution_stack(state)

        assert hero.gold == 2
        assert hero.items[StatType.ATTACK] == 1


# =============================================================================
# Scoping: override does not apply to other heroes
# =============================================================================


class TestTideScopingToCurrentActor:
    def test_override_inactive_for_other_hero_acting(self):
        """When another hero is current actor, Tide doesn't apply."""
        state = _make_state(hero_level=8, num_spawn_points=0)
        state.current_actor_id = "enemy"  # Enemy is acting, not Dodger

        # _has_tide_of_darkness should be False
        assert _has_tide_of_darkness(state) is False

        # Spawn point filter should use normal path
        f = SpawnPointTeamFilter(relation="FRIENDLY")
        h = Hex(q=2, r=0, s=-2)
        assert f.apply(h, state, {}) is False

    def test_count_uses_normal_path_for_other_actor(self):
        """_count_empty_spawn_points uses normal logic when actor isn't Dodger."""
        state = _make_state(hero_level=8, num_spawn_points=0)
        state.current_actor_id = "enemy"
        # No spawn points, no zone override → 0
        count = _count_empty_spawn_points(state, "enemy", radius=3)
        assert count == 0


# =============================================================================
# Effect registration
# =============================================================================


class TestTideOfDarknessEffectRegistration:
    def test_effect_is_registered(self):
        effect = CardEffectRegistry.get("tide_of_darkness")
        assert effect is not None

    def test_build_steps_returns_empty(self):
        """Tide is a passive — build_steps returns empty list."""
        state = _make_state(hero_level=8)
        hero = state.get_hero("hero_dodger")
        card = _make_ultimate_card()
        effect = CardEffectRegistry.get("tide_of_darkness")
        stats = compute_card_stats(state, hero.id, card)
        steps = effect.build_steps(state, hero, card, stats)
        assert steps == []

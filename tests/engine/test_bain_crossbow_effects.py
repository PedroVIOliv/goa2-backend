"""
Tests for Bain's crossbow cards (Light Crossbow, Heavy Crossbow, Arbalest)
and Perfect Getaway defense card.
"""

import pytest
import goa2.scripts.bain_effects  # noqa: F401 — registers effects

from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Minion,
    MinionType,
    Card,
    CardTier,
    CardColor,
    ActionType,
)
from goa2.domain.hex import Hex
from goa2.domain.models.marker import MarkerType
from goa2.engine.steps import ResolveCardStep, SelectStep
from goa2.engine.filters import (
    ClearLineOfSightFilter,
    InStraightLineFilter,
    RangeFilter,
    TeamFilter,
)
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.stats import CardStats


# =============================================================================
# Card Factories
# =============================================================================


def _make_crossbow_card(card_id, name, effect_id, range_value=2, primary_value=5):
    return Card(
        id=card_id,
        name=name,
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=8,
        primary_action=ActionType.ATTACK,
        primary_action_value=primary_value,
        secondary_actions={},
        is_ranged=True,
        range_value=range_value,
        effect_id=effect_id,
        effect_text="",
        is_facedown=False,
    )


def _make_defense_card(card_id, name, effect_id):
    return Card(
        id=card_id,
        name=name,
        tier=CardTier.III,
        color=CardColor.GREEN,
        initiative=3,
        primary_action=ActionType.DEFENSE,
        secondary_actions={},
        is_ranged=False,
        effect_id=effect_id,
        effect_text="",
        is_facedown=False,
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def crossbow_state():
    """Board with enough hexes for ranged tests."""
    board = Board()
    hexes = set()
    for q in range(-2, 6):
        for r in range(-2, 3):
            s = -q - r
            if abs(s) <= 5:
                hexes.add(Hex(q=q, r=r, s=s))
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    hero = Hero(
        id="hero_bain", name="Bain", team=TeamColor.RED, deck=[], level=1
    )
    enemy = Hero(
        id="enemy_hero", name="Enemy", team=TeamColor.BLUE, deck=[], level=1
    )
    minion = Minion(
        id="minion_1", name="Blocker", team=TeamColor.BLUE, type=MinionType.MELEE
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[enemy], minions=[minion]
            ),
        },
    )
    state.place_entity("hero_bain", Hex(q=0, r=0, s=0))
    state.current_actor_id = "hero_bain"
    return state


def _get_crossbow_candidates(state, range_val=2):
    """Push a crossbow-style SelectStep and return the candidates list."""
    from goa2.domain.models.enums import TargetType

    push_steps(
        state,
        [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select target",
                output_key="victim_id",
                is_mandatory=True,
                filters=[
                    TeamFilter(relation="ENEMY"),
                    RangeFilter(max_range=range_val),
                    InStraightLineFilter(),
                    ClearLineOfSightFilter(
                        blocked_by_units=True, blocked_by_terrain=True
                    ),
                ],
            ),
        ],
    )
    req = process_resolution_stack(state)
    if req is None:
        return []
    return req.get("candidates", [])


# =============================================================================
# Crossbow Tests — Targeting via SelectStep
# =============================================================================


def test_crossbow_clear_line_target(crossbow_state):
    """Enemy in straight line with no obstacles → valid target."""
    crossbow_state.place_entity("enemy_hero", Hex(q=2, r=0, s=-2))
    candidates = _get_crossbow_candidates(crossbow_state)
    assert "enemy_hero" in candidates


def test_crossbow_blocked_by_unit(crossbow_state):
    """Unit on intermediate hex blocks targeting beyond it."""
    crossbow_state.place_entity("minion_1", Hex(q=1, r=0, s=-1))
    crossbow_state.place_entity("enemy_hero", Hex(q=2, r=0, s=-2))
    candidates = _get_crossbow_candidates(crossbow_state)
    assert "enemy_hero" not in candidates
    assert "minion_1" in candidates


def test_crossbow_blocked_by_terrain(crossbow_state):
    """Terrain on intermediate hex blocks targeting beyond it."""
    crossbow_state.board.tiles[Hex(q=1, r=0, s=-1)].is_terrain = True
    crossbow_state.place_entity("enemy_hero", Hex(q=2, r=0, s=-2))
    candidates = _get_crossbow_candidates(crossbow_state)
    assert "enemy_hero" not in candidates


def test_crossbow_off_axis_rejected(crossbow_state):
    """Unit not in a straight line → rejected."""
    crossbow_state.place_entity("enemy_hero", Hex(q=1, r=1, s=-2))
    candidates = _get_crossbow_candidates(crossbow_state)
    assert "enemy_hero" not in candidates


def test_crossbow_adjacent_always_valid(crossbow_state):
    """Adjacent target (no intermediates) → always valid."""
    crossbow_state.place_entity("enemy_hero", Hex(q=1, r=0, s=-1))
    candidates = _get_crossbow_candidates(crossbow_state)
    assert "enemy_hero" in candidates


def test_crossbow_out_of_range(crossbow_state):
    """Target beyond range → rejected even if line is clear."""
    crossbow_state.place_entity("enemy_hero", Hex(q=3, r=0, s=-3))
    candidates = _get_crossbow_candidates(crossbow_state, range_val=2)
    assert "enemy_hero" not in candidates


def test_arbalest_longer_range(crossbow_state):
    """Arbalest with range 4 can hit distant targets in clear line."""
    crossbow_state.place_entity("enemy_hero", Hex(q=4, r=0, s=-4))
    candidates = _get_crossbow_candidates(crossbow_state, range_val=4)
    assert "enemy_hero" in candidates


# =============================================================================
# Crossbow build_steps integration — verify effect produces correct filters
# =============================================================================


def test_crossbow_effect_builds_correct_steps(crossbow_state):
    """Light Crossbow effect produces AttackSequenceStep with line-of-sight filters."""
    from goa2.scripts.bain_effects import LightCrossbowEffect

    effect = LightCrossbowEffect()
    hero = crossbow_state.get_hero("hero_bain")
    card = _make_crossbow_card("lc", "Light Crossbow", "light_crossbow")
    stats = CardStats(primary_value=5, range=2)

    steps = effect.build_steps(crossbow_state, hero, card, stats)

    assert len(steps) == 1
    attack_step = steps[0]
    filter_types = [type(f) for f in attack_step.target_filters]
    assert InStraightLineFilter in filter_types
    assert ClearLineOfSightFilter in filter_types


# =============================================================================
# Perfect Getaway Tests
# =============================================================================


def test_perfect_getaway_blocks_when_bounty_in_play(crossbow_state):
    """Perfect Getaway auto-blocks if any hero has a bounty marker."""
    from goa2.scripts.bain_effects import PerfectGetawayEffect

    state = crossbow_state
    marker = state.get_marker(MarkerType.BOUNTY)
    marker.place(target_id="enemy_hero", value=0, source_id="hero_bain")

    effect = PerfectGetawayEffect()
    hero = state.get_hero("hero_bain")
    card = _make_defense_card("pg", "Perfect Getaway", "perfect_getaway")
    stats = CardStats(primary_value=0, range=1)
    context = {"attack_is_ranged": True, "attacker_id": "enemy_hero"}

    steps = effect.build_defense_steps(state, hero, card, stats, context)

    assert len(steps) == 1
    assert steps[0].key == "auto_block"
    assert steps[0].value is True


def test_perfect_getaway_invalid_without_bounty(crossbow_state):
    """Perfect Getaway is invalid when no bounty marker in play."""
    from goa2.scripts.bain_effects import PerfectGetawayEffect

    state = crossbow_state

    effect = PerfectGetawayEffect()
    hero = state.get_hero("hero_bain")
    card = _make_defense_card("pg", "Perfect Getaway", "perfect_getaway")
    stats = CardStats(primary_value=0, range=1)
    context = {"attack_is_ranged": True, "attacker_id": "enemy_hero"}

    steps = effect.build_defense_steps(state, hero, card, stats, context)

    assert len(steps) == 1
    assert steps[0].key == "defense_invalid"
    assert steps[0].value is True


def test_perfect_getaway_blocks_when_bounty_on_different_hero(crossbow_state):
    """Perfect Getaway works when bounty is on ANY hero, not just attacker."""
    from goa2.scripts.bain_effects import PerfectGetawayEffect

    state = crossbow_state
    other = Hero(id="other", name="Other", team=TeamColor.RED, deck=[], level=1)
    state.teams[TeamColor.RED].heroes.append(other)
    state.place_entity("other", Hex(q=-1, r=0, s=1))

    marker = state.get_marker(MarkerType.BOUNTY)
    marker.place(target_id="other", value=0, source_id="hero_bain")

    effect = PerfectGetawayEffect()
    hero = state.get_hero("hero_bain")
    card = _make_defense_card("pg", "Perfect Getaway", "perfect_getaway")
    stats = CardStats(primary_value=0, range=1)
    context = {"attack_is_ranged": False, "attacker_id": "enemy_hero"}

    steps = effect.build_defense_steps(state, hero, card, stats, context)

    assert len(steps) == 1
    assert steps[0].key == "auto_block"
    assert steps[0].value is True


def test_perfect_getaway_blocks_regardless_of_ranged(crossbow_state):
    """Perfect Getaway blocks both ranged and non-ranged attacks."""
    from goa2.scripts.bain_effects import PerfectGetawayEffect

    state = crossbow_state
    marker = state.get_marker(MarkerType.BOUNTY)
    marker.place(target_id="enemy_hero", value=0, source_id="hero_bain")

    effect = PerfectGetawayEffect()
    hero = state.get_hero("hero_bain")
    card = _make_defense_card("pg", "Perfect Getaway", "perfect_getaway")
    stats = CardStats(primary_value=0, range=1)

    # Non-ranged
    steps = effect.build_defense_steps(
        state, hero, card, stats, {"attack_is_ranged": False}
    )
    assert steps[0].key == "auto_block"

    # Ranged
    steps = effect.build_defense_steps(
        state, hero, card, stats, {"attack_is_ranged": True}
    )
    assert steps[0].key == "auto_block"

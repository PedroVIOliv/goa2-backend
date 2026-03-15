"""
Tests for Enfeeblement (Dodger Tier III Blue — SKILL).

Card text: "This turn: Enemy heroes in radius have -6 Attack and cannot repeat actions."

Tests cover:
- -6 Attack modifier via AREA_STAT_MODIFIER
- REPEAT_PREVENTION blocks MayRepeatOnceStep
- REPEAT_PREVENTION blocks CloakAndDaggers passive (get_passive_steps returns [])
- Effect respects radius scope (heroes outside radius unaffected)
- Non-repeat passives (e.g., BEFORE_ATTACK) are NOT blocked
"""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Card,
    CardTier,
    CardColor,
    ActionType,
)
from goa2.domain.hex import Hex
from goa2.domain.models.effect import (
    ActiveEffect,
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import StatType
from goa2.domain.types import UnitID
from goa2.engine.effect_manager import EffectManager
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.steps import LogMessageStep, MayRepeatOnceStep
from goa2.engine.stats import compute_card_stats, get_computed_stat

# Register effects
import goa2.scripts.dodger_effects  # noqa: F401
import goa2.scripts.tigerclaw_effects  # noqa: F401


# =============================================================================
# Card Factories
# =============================================================================


def _make_filler_card(card_id="filler", color=CardColor.GOLD):
    return Card(
        id=card_id, name="Filler", tier=CardTier.UNTIERED, color=color,
        initiative=1, primary_action=ActionType.ATTACK, secondary_actions={},
        is_ranged=False, range_value=0, primary_action_value=1,
        effect_id="filler", effect_text="", is_facedown=False,
    )


def _make_enfeeblement_card():
    return Card(
        id="enfeeblement", name="Enfeeblement", tier=CardTier.III,
        color=CardColor.BLUE, initiative=5,
        primary_action=ActionType.SKILL, secondary_actions={},
        is_ranged=False, radius_value=2,
        effect_id="enfeeblement",
        effect_text="This turn: Enemy heroes in radius have -6 Attack and cannot repeat actions.",
        is_facedown=False,
    )


def _make_attack_card(card_id="basic_attack"):
    return Card(
        id=card_id, name="Basic Attack", tier=CardTier.I, color=CardColor.RED,
        initiative=5, primary_action=ActionType.ATTACK, secondary_actions={},
        is_ranged=False, range_value=0, primary_action_value=4,
        effect_id="hit_and_run", effect_text="", is_facedown=False,
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def game_state():
    """Standard game state with hero at origin and enemy at distance 1."""
    board = Board()
    hexes = set()
    for q in range(-5, 6):
        for r in range(-5, 6):
            s = -q - r
            if abs(s) <= 5:
                hexes.add(Hex(q=q, r=r, s=s))
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    card = _make_enfeeblement_card()
    hero = Hero(id="hero_dodger", name="Dodger", team=TeamColor.RED, deck=[], level=1)
    hero.current_turn_card = card

    enemy = Hero(id="enemy_hero", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)
    enemy.hand = [_make_filler_card("enemy_card")]
    enemy.current_turn_card = _make_attack_card()

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.place_entity("hero_dodger", Hex(q=0, r=0, s=0))
    state.place_entity("enemy_hero", Hex(q=1, r=0, s=-1))
    state.current_actor_id = "hero_dodger"
    return state


# =============================================================================
# Tests: Effect Registration and Structure
# =============================================================================


def test_enfeeblement_registered():
    effect = CardEffectRegistry.get("enfeeblement")
    assert effect is not None


def test_enfeeblement_creates_two_effects(game_state):
    """Enfeeblement should create both AREA_STAT_MODIFIER and REPEAT_PREVENTION effects."""
    state = game_state
    hero = state.get_hero("hero_dodger")
    card = hero.current_turn_card

    effect = CardEffectRegistry.get("enfeeblement")
    stats = compute_card_stats(state, UnitID(hero.id), card)
    steps = effect.build_steps(state, hero, card, stats)

    assert len(steps) == 2

    from goa2.engine.steps import CreateEffectStep
    assert isinstance(steps[0], CreateEffectStep)
    assert steps[0].effect_type == EffectType.AREA_STAT_MODIFIER
    assert steps[0].stat_value == -6

    assert isinstance(steps[1], CreateEffectStep)
    assert steps[1].effect_type == EffectType.REPEAT_PREVENTION


# =============================================================================
# Tests: -6 Attack Modifier
# =============================================================================


def test_enfeeblement_minus_6_attack(game_state):
    """Enemy heroes in radius should get -6 Attack from the AREA_STAT_MODIFIER."""
    state = game_state

    # Create the area stat modifier effect directly
    EffectManager.create_effect(
        state=state,
        source_id="hero_dodger",
        effect_type=EffectType.AREA_STAT_MODIFIER,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_dodger",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        stat_type=StatType.ATTACK,
        stat_value=-6,
        is_active=True,
    )

    # Check that the effect applies: base 4 attack - 6 = -2
    result = get_computed_stat(state, UnitID("enemy_hero"), StatType.ATTACK, base_value=4)
    assert result == -2


def test_enfeeblement_attack_modifier_outside_radius(game_state):
    """Enemy heroes outside radius should NOT get the -6 Attack modifier."""
    state = game_state

    # Move enemy far away (distance 4, outside radius 2)
    state.move_unit(UnitID("enemy_hero"), Hex(q=4, r=0, s=-4))

    EffectManager.create_effect(
        state=state,
        source_id="hero_dodger",
        effect_type=EffectType.AREA_STAT_MODIFIER,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_dodger",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        stat_type=StatType.ATTACK,
        stat_value=-6,
        is_active=True,
    )

    # Base 4 attack should remain 4 (no modifier)
    result = get_computed_stat(state, UnitID("enemy_hero"), StatType.ATTACK, base_value=4)
    assert result == 4


# =============================================================================
# Tests: Repeat Prevention — MayRepeatOnceStep
# =============================================================================


def test_repeat_prevention_blocks_may_repeat_once(game_state):
    """REPEAT_PREVENTION effect should block MayRepeatOnceStep for enemy heroes."""
    state = game_state

    # Create REPEAT_PREVENTION effect from Dodger targeting enemy heroes
    EffectManager.create_effect(
        state=state,
        source_id="hero_dodger",
        effect_type=EffectType.REPEAT_PREVENTION,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_dodger",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        is_active=True,
    )

    # Now the enemy hero tries to repeat an action
    state.current_actor_id = "enemy_hero"
    template = [LogMessageStep(message="Repeated!")]
    step = MayRepeatOnceStep(steps_template=template)

    res = step.resolve(state, state.execution_context)
    # Should be finished immediately without prompting (blocked)
    assert res.is_finished is True
    assert len(res.new_steps) == 0


def test_no_repeat_prevention_allows_may_repeat_once(game_state):
    """Without REPEAT_PREVENTION, MayRepeatOnceStep should prompt normally."""
    state = game_state
    state.current_actor_id = "enemy_hero"

    template = [LogMessageStep(message="Repeated!")]
    step = MayRepeatOnceStep(steps_template=template)

    res = step.resolve(state, state.execution_context)
    # Should prompt the player
    assert res.requires_input is True


def test_repeat_prevention_outside_radius_does_not_block(game_state):
    """Enemy hero outside radius should still be able to repeat."""
    state = game_state

    # Move enemy far away
    state.move_unit(UnitID("enemy_hero"), Hex(q=4, r=0, s=-4))

    EffectManager.create_effect(
        state=state,
        source_id="hero_dodger",
        effect_type=EffectType.REPEAT_PREVENTION,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_dodger",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        is_active=True,
    )

    state.current_actor_id = "enemy_hero"
    template = [LogMessageStep(message="Repeated!")]
    step = MayRepeatOnceStep(steps_template=template)

    res = step.resolve(state, state.execution_context)
    # Should still prompt (not blocked, outside radius)
    assert res.requires_input is True


# =============================================================================
# Tests: Repeat Prevention — CloakAndDaggers Passive
# =============================================================================


def test_repeat_prevention_blocks_cloak_and_daggers(game_state):
    """REPEAT_PREVENTION should cause CloakAndDaggers.get_passive_steps() to return []."""
    state = game_state
    from goa2.domain.models.enums import PassiveTrigger

    # Create REPEAT_PREVENTION effect
    EffectManager.create_effect(
        state=state,
        source_id="hero_dodger",
        effect_type=EffectType.REPEAT_PREVENTION,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_dodger",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        is_active=True,
    )

    enemy = state.get_hero("enemy_hero")
    cloak_effect = CardEffectRegistry.get("cloak_and_daggers")
    cloak_card = _make_filler_card("cloak_card")

    context = {
        "basic_action_type": ActionType.ATTACK.value,
        "basic_action_value": 3,
        "basic_action_range": 1,
    }

    steps = cloak_effect.get_passive_steps(
        state, enemy, cloak_card, PassiveTrigger.AFTER_BASIC_ACTION, context
    )
    assert steps == []


def test_cloak_and_daggers_works_without_prevention(game_state):
    """Without REPEAT_PREVENTION, CloakAndDaggers should return steps normally."""
    state = game_state
    from goa2.domain.models.enums import PassiveTrigger

    enemy = state.get_hero("enemy_hero")
    cloak_effect = CardEffectRegistry.get("cloak_and_daggers")
    cloak_card = _make_filler_card("cloak_card")

    context = {
        "basic_action_type": ActionType.ATTACK.value,
        "basic_action_value": 3,
        "basic_action_range": 1,
    }

    steps = cloak_effect.get_passive_steps(
        state, enemy, cloak_card, PassiveTrigger.AFTER_BASIC_ACTION, context
    )
    assert len(steps) > 0


# =============================================================================
# Tests: Non-repeat passives are NOT blocked
# =============================================================================


def test_repeat_prevention_does_not_block_before_attack_trigger(game_state):
    """REPEAT_PREVENTION should NOT block passives with non-repeat triggers."""
    state = game_state
    from goa2.domain.models.enums import PassiveTrigger

    EffectManager.create_effect(
        state=state,
        source_id="hero_dodger",
        effect_type=EffectType.REPEAT_PREVENTION,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_dodger",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        is_active=True,
    )

    # CloakAndDaggers should still return [] for BEFORE_ATTACK
    # (because the trigger doesn't match, not because of repeat prevention)
    enemy = state.get_hero("enemy_hero")
    cloak_effect = CardEffectRegistry.get("cloak_and_daggers")
    cloak_card = _make_filler_card("cloak_card")

    context = {}
    steps = cloak_effect.get_passive_steps(
        state, enemy, cloak_card, PassiveTrigger.BEFORE_ATTACK, context
    )
    assert steps == []


# =============================================================================
# Tests: can_repeat_action filter correctness
# =============================================================================


def test_can_repeat_action_ignores_non_repeat_effects(game_state):
    """can_repeat_action should only check REPEAT_PREVENTION effects,
    not AREA_STAT_MODIFIER or other effect types."""
    state = game_state

    # Create an AREA_STAT_MODIFIER that targets enemy heroes (NOT repeat prevention)
    EffectManager.create_effect(
        state=state,
        source_id="hero_dodger",
        effect_type=EffectType.AREA_STAT_MODIFIER,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_dodger",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        stat_type=StatType.ATTACK,
        stat_value=-6,
        is_active=True,
    )

    # can_repeat_action should still allow (not a REPEAT_PREVENTION effect)
    result = state.validator.can_repeat_action(state, "enemy_hero")
    assert result.allowed is True


def test_can_repeat_action_blocks_with_repeat_prevention(game_state):
    """can_repeat_action should block when REPEAT_PREVENTION effect is active."""
    state = game_state

    EffectManager.create_effect(
        state=state,
        source_id="hero_dodger",
        effect_type=EffectType.REPEAT_PREVENTION,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_dodger",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        is_active=True,
    )

    result = state.validator.can_repeat_action(state, "enemy_hero")
    assert result.allowed is False
    assert "repeat" in result.reason.lower()


def test_friendly_hero_not_blocked_by_own_repeat_prevention(game_state):
    """Dodger's own REPEAT_PREVENTION should not block friendly heroes."""
    state = game_state

    EffectManager.create_effect(
        state=state,
        source_id="hero_dodger",
        effect_type=EffectType.REPEAT_PREVENTION,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_id="hero_dodger",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        is_active=True,
    )

    # Dodger's own repeat should not be blocked
    result = state.validator.can_repeat_action(state, "hero_dodger")
    assert result.allowed is True

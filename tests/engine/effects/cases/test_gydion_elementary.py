from __future__ import annotations

from goa2.domain.hex import Hex
from goa2.domain.models import CardState, EffectType, StatType
from goa2.domain.models.effect import DurationType
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.filters_geometry import InStraightLineFilter, StraightLinePathFilter
from goa2.engine.filters_hex import MovementPathFilter, ObstacleFilter, RangeFilter
from goa2.engine.filters_units import TeamFilter, UnitTypeFilter
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import (
    AttackSequenceStep,
    CreateEffectStep,
    ForceDiscardStep,
    MoveUnitStep,
    SelectStep,
)
from goa2.scripts.brogan_effects import ShieldEffect as BroganShieldEffect
from goa2.scripts.gydion_effects import BurningHandsEffect, ShieldEffect, SuggestionEffect

from ..builders import EffectScenarioBuilder
from ..gydion_common import gydion_spell


def _state(spell_id: str):
    spell = gydion_spell(spell_id)
    spell.state = CardState.OUTSIDE_SPELLBOOK
    return (
        EffectScenarioBuilder()
        .with_hexes(
            [
                (0, 0, 0),
                (1, 0, -1),
                (2, 0, -2),
                (3, 0, -3),
                (4, 0, -4),
                (0, 1, -1),
                (0, 2, -2),
                (0, 3, -3),
            ]
        )
        .red_hero("hero_caster", at=(0, 0, 0), current_card=spell)
        .blue_hero("hero_target", at=(1, 0, -1))
        .blue_hero("hero_other", at=(2, 0, -2))
        .with_actor("hero_caster")
        .build()
    ), spell


def test_elementary_spell_effects_are_registered() -> None:
    assert isinstance(
        CardEffectRegistry.get_for_card(gydion_spell("burning_hands")), BurningHandsEffect
    )
    assert isinstance(CardEffectRegistry.get_for_card(gydion_spell("suggestion")), SuggestionEffect)
    assert isinstance(CardEffectRegistry.get_for_card(gydion_spell("shield")), ShieldEffect)
    assert isinstance(CardEffectRegistry.get("shield"), BroganShieldEffect)


def test_burning_hands_orders_target_discard_rider_before_non_basic_attack() -> None:
    state, spell = _state("burning_hands")
    hero = state.get_hero("hero_caster")
    hero.items[StatType.ATTACK] = 2
    effect = CardEffectRegistry.get_for_card(spell)

    steps = effect.get_steps(state, hero, spell)

    assert [type(step) for step in steps] == [
        SelectStep,
        SelectStep,
        ForceDiscardStep,
        AttackSequenceStep,
    ]
    target, victim, discard, attack = steps
    assert target.is_mandatory is True
    assert attack.target_id_key == target.output_key
    assert attack.damage == 7
    assert discard.victim_key == victim.output_key
    assert discard.active_if_key == victim.output_key
    assert victim.is_mandatory is False
    assert any(isinstance(item, TeamFilter) and item.relation == "ENEMY" for item in victim.filters)
    assert any(
        isinstance(item, UnitTypeFilter) and item.unit_type == "HERO" for item in victim.filters
    )
    assert any(
        isinstance(item, RangeFilter)
        and item.min_range == 1
        and item.max_range == 1
        and item.origin_key == target.output_key
        for item in victim.filters
    )


def test_suggestion_uses_radius_target_then_exact_three_straight_forced_move() -> None:
    state, spell = _state("suggestion")
    hero = state.get_hero("hero_caster")
    hero.items[StatType.RADIUS] = 1
    effect = CardEffectRegistry.get_for_card(spell)

    steps = effect.get_steps(state, hero, spell)

    assert [type(step) for step in steps] == [SelectStep, SelectStep, MoveUnitStep]
    target, destination, move = steps
    assert target.is_mandatory is True
    assert any(isinstance(item, RangeFilter) and item.max_range == 4 for item in target.filters)
    assert any(
        isinstance(item, UnitTypeFilter) and item.unit_type == "HERO" for item in target.filters
    )
    assert destination.is_mandatory is True
    assert any(
        isinstance(item, RangeFilter)
        and item.min_range == 3
        and item.max_range == 3
        and item.origin_key == target.output_key
        for item in destination.filters
    )
    assert any(isinstance(item, InStraightLineFilter) for item in destination.filters)
    assert any(isinstance(item, StraightLinePathFilter) for item in destination.filters)
    assert any(isinstance(item, ObstacleFilter) for item in destination.filters)
    assert any(isinstance(item, MovementPathFilter) for item in destination.filters)
    assert move.unit_key == target.output_key
    assert move.range_val == 3
    assert move.is_movement_action is False


def test_suggestion_offers_target_before_destination_feasibility_and_then_fizzles() -> None:
    state, spell = _state("suggestion")
    effect = CardEffectRegistry.get_for_card(spell)
    steps = effect.get_steps(state, state.get_hero("hero_caster"), spell)
    push_steps(state, steps)

    target_request = process_stack(state)
    assert target_request.input_request is not None
    assert {option.id for option in target_request.input_request.options} == {
        "hero_target",
        "hero_other",
    }
    state.execution_stack[-1].pending_input = {"selection": "hero_other"}
    destination = process_stack(state)
    assert destination.input_request is None


def test_shield_creates_one_active_card_bound_basic_only_immunity() -> None:
    state, spell = _state("shield")
    hero = state.get_hero("hero_caster")
    effect = CardEffectRegistry.get_for_card(spell)

    first = effect.get_steps(state, hero, spell)
    assert len(first) == 1
    assert isinstance(first[0], CreateEffectStep)
    push_steps(state, first)
    process_stack(state)

    immunity = state.active_effects[0]
    assert immunity.effect_type == EffectType.ATTACK_IMMUNITY
    assert immunity.duration == DurationType.THIS_ROUND
    assert immunity.source_id == hero.id
    assert immunity.source_card_id == spell.id
    assert immunity.basic_attacks_only is True
    assert immunity.is_active is True

    repeated = effect.get_steps(state, hero, spell)
    push_steps(state, repeated)
    process_stack(state)
    assert len(state.active_effects) == 1


def _line_state(spell_id: str):
    spell = gydion_spell(spell_id)
    spell.state = CardState.OUTSIDE_SPELLBOOK
    return (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3), (4, 0, -4)])
        .red_hero("hero_caster", at=(0, 0, 0), current_card=spell)
        .blue_hero("hero_target", at=(1, 0, -1))
        .with_actor("hero_caster")
        .build()
    ), spell


def test_suggestion_lets_the_moved_hero_choose_their_own_destination() -> None:
    state, spell = _line_state("suggestion")
    effect = CardEffectRegistry.get_for_card(spell)
    push_steps(state, effect.get_steps(state, state.get_hero("hero_caster"), spell))

    target_request = process_stack(state)
    assert target_request.input_request.player_id == "hero_caster"
    state.execution_stack[-1].pending_input = {"selection": "hero_target"}

    destination = process_stack(state)
    assert destination.input_request is not None
    assert destination.input_request.player_id == "hero_target"

    state.execution_stack[-1].pending_input = {"selection": {"q": 4, "r": 0, "s": -4}}
    process_stack(state)
    assert state.get_position("hero_target") == Hex(q=4, r=0, s=-4)

from __future__ import annotations

import pytest

import goa2.scripts.gydion_effects  # noqa: F401
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import CardState, StatType, TeamColor
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.filters_hex import MovementPathFilter, ObstacleFilter, RangeFilter
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import (
    AttackSequenceStep,
    MoveSequenceStep,
    MoveUnitStep,
    SelectStep,
)
from goa2.scripts.gydion_effects import (
    ExpeditiousRetreatEffect,
    MagicMissileEffect,
    ShockingGraspEffect,
)

from ..builders import EffectScenarioBuilder
from ..gydion_common import fresh_gydion, gydion_spell


def _state(spell_id: str, *, hexes=None):
    spell = gydion_spell(spell_id)
    spell.state = CardState.OUTSIDE_SPELLBOOK
    spell.is_facedown = False
    builder = EffectScenarioBuilder().with_hexes(
        hexes
        or [
            (0, 0, 0),
            (1, 0, -1),
            (2, 0, -2),
            (3, 0, -3),
            (4, 0, -4),
            (0, 1, -1),
            (1, 1, -2),
        ]
    )
    state = (
        builder.red_hero("hero_caster", at=(0, 0, 0), current_card=spell)
        .blue_hero("enemy_adjacent", at=(1, 0, -1))
        .blue_hero("enemy_far", at=(3, 0, -3))
        .with_actor("hero_caster")
        .build()
    )
    state.get_hero("hero_caster").spells = [
        item.model_copy(deep=True) for item in fresh_gydion().spells
    ]
    return state, spell


@pytest.mark.effect_contract
def test_cantrip_spell_effects_are_registered() -> None:
    assert isinstance(
        CardEffectRegistry.get_for_card(gydion_spell("shocking_grasp")), ShockingGraspEffect
    )
    assert isinstance(
        CardEffectRegistry.get_for_card(gydion_spell("magic_missile")), MagicMissileEffect
    )
    assert isinstance(
        CardEffectRegistry.get_for_card(gydion_spell("expeditious_retreat")),
        ExpeditiousRetreatEffect,
    )


@pytest.mark.effect_contract
def test_shocking_grasp_assembles_stable_attack_then_optional_target_move() -> None:
    state, spell = _state("shocking_grasp")
    hero = state.get_hero("hero_caster")
    hero.items[StatType.ATTACK] = 2
    effect = CardEffectRegistry.get_for_card(spell)

    steps = effect.get_steps(state, hero, spell)

    assert [type(step) for step in steps] == [
        SelectStep,
        AttackSequenceStep,
        SelectStep,
        MoveUnitStep,
    ]
    target, attack, destination, move = steps
    assert target.output_key == "shocking_grasp_target"
    assert target.is_mandatory is True
    assert attack.target_id_key == target.output_key
    assert attack.damage == 5
    assert attack.range_val == 1
    assert destination.target_type.value == "HEX"
    assert destination.is_mandatory is False
    assert destination.active_if_key == target.output_key
    assert any(
        isinstance(item, RangeFilter)
        and item.max_range == 1
        and item.origin_key == target.output_key
        for item in destination.filters
    )
    assert any(
        isinstance(item, ObstacleFilter) and item.exclude_id_key == target.output_key
        for item in destination.filters
    )
    assert any(
        isinstance(item, MovementPathFilter) and item.unit_key == target.output_key
        for item in destination.filters
    )
    assert move.unit_key == target.output_key
    assert move.is_movement_action is False
    assert move.is_mandatory is False


@pytest.mark.effect_flow
def test_shocking_grasp_target_selection_is_adjacent_and_does_not_require_mobility() -> None:
    state, spell = _state("shocking_grasp")
    effect = CardEffectRegistry.get_for_card(spell)
    steps = effect.get_steps(state, state.get_hero("hero_caster"), spell)
    push_steps(state, [steps[0]])

    result = process_stack(state)

    assert result.input_request is not None
    assert {option.id for option in result.input_request.options} == {"enemy_adjacent"}


@pytest.mark.effect_contract
def test_magic_missile_uses_computed_attack_and_range_with_non_adjacent_filter() -> None:
    state, spell = _state("magic_missile")
    hero = state.get_hero("hero_caster")
    hero.items[StatType.ATTACK] = 2
    hero.items[StatType.RANGE] = 1
    effect = CardEffectRegistry.get_for_card(spell)

    steps = effect.get_steps(state, hero, spell)

    assert len(steps) == 1
    attack = steps[0]
    assert isinstance(attack, AttackSequenceStep)
    assert attack.damage == 3
    assert attack.range_val == 4
    assert attack.is_ranged is True
    assert any(
        isinstance(item, RangeFilter) and item.min_range == 2 and item.max_range == 4
        for item in attack.target_filters
    )


@pytest.mark.effect_flow
def test_magic_missile_live_target_options_exclude_adjacent_and_beyond_computed_range() -> None:
    state, spell = _state("magic_missile")
    state.teams[TeamColor.BLUE].heroes.append(
        state.teams[TeamColor.BLUE]
        .heroes[-1]
        .model_copy(
            deep=True,
            update={"id": "enemy_too_far"},
        )
    )
    state.place_entity("enemy_too_far", Hex(q=4, r=0, s=-4))
    effect = CardEffectRegistry.get_for_card(spell)
    attack = effect.get_steps(state, state.get_hero("hero_caster"), spell)[0]
    state.execution_context["current_action_type"] = "ATTACK"
    push_steps(state, [attack])

    result = process_stack(state)

    assert result.input_request is not None
    assert {option.id for option in result.input_request.options} == {"enemy_far"}
    assert state.execution_context["attack_is_ranged"] is True
    assert state.execution_context["attack_is_basic"] is True


@pytest.mark.effect_contract
def test_expeditious_retreat_uses_computed_movement_and_straight_line_sequence() -> None:
    state, spell = _state("expeditious_retreat")
    hero = state.get_hero("hero_caster")
    hero.items[StatType.MOVEMENT] = 2
    effect = CardEffectRegistry.get_for_card(spell)

    steps = effect.get_steps(state, hero, spell)

    assert len(steps) == 1
    movement = steps[0]
    assert isinstance(movement, MoveSequenceStep)
    assert movement.unit_id == hero.id
    assert movement.range_val == 7
    assert movement.force_straight_line is True
    assert movement.force_full_distance is False


@pytest.mark.effect_flow
def test_expeditious_retreat_live_options_include_zero_and_axes_but_exclude_bent_hexes() -> None:
    state, spell = _state("expeditious_retreat")
    effect = CardEffectRegistry.get_for_card(spell)
    movement = effect.get_steps(state, state.get_hero("hero_caster"), spell)[0]
    push_steps(state, [movement])

    result = process_stack(state)

    assert result.input_request is not None
    assert result.input_request.request_type == InputRequestType.SELECT_HEX
    options = {
        (option.metadata["hex"]["q"], option.metadata["hex"]["r"], option.metadata["hex"]["s"])
        for option in result.input_request.options
    }
    assert (0, 0, 0) in options
    assert (0, 1, -1) in options
    assert (1, 1, -2) not in options

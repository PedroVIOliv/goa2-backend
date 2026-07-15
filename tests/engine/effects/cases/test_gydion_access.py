from __future__ import annotations

import pytest

import goa2.scripts.gydion_effects  # noqa: F401 — registers Gydion effects
from goa2.domain.events import GameEventType
from goa2.domain.input import InputRequestType
from goa2.domain.models import CardState
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import CastSpellStep, PrepareSpellbookStep
from goa2.scripts.gydion_effects import PrepareSpellsEffect, SpellAccessEffect

from ..builders import EffectScenarioBuilder
from ..gydion_common import fresh_gydion, gydion_card
from ..runner import run_card

ACCESS_MAP = {
    "cantrip": ("shocking_grasp", "magic_missile", "expeditious_retreat"),
    "elementary_evocation": ("burning_hands",),
    "lesser_evocation": ("burning_hands", "fireball"),
    "greater_evocation": ("burning_hands", "fireball", "sunburst"),
    "elementary_abjuration": ("shield",),
    "lesser_abjuration": ("shield", "banishment"),
    "greater_abjuration": ("shield", "banishment", "invulnerability"),
    "elementary_enchantment": ("suggestion",),
    "lesser_enchantment": ("suggestion", "dominate_person"),
    "greater_enchantment": ("suggestion", "dominate_person", "power_word_kill"),
    "lesser_necromancy": ("vampiric_touch", "create_undead"),
    "greater_necromancy": ("vampiric_touch", "create_undead", "energy_drain"),
    "lesser_conjuration": ("find_familiar", "dimension_door"),
    "greater_conjuration": ("find_familiar", "dimension_door", "cloud_kill"),
    "lesser_transmutation": ("midas_touch", "disintegrate"),
    "greater_transmutation": ("midas_touch", "disintegrate", "polymorph"),
}


def _state(card_id: str):
    card = gydion_card(card_id)
    card.state = CardState.UNRESOLVED
    card.is_facedown = False
    state = (
        EffectScenarioBuilder()
        .line_board()
        .red_hero("hero_gydion", at=(0, 0, 0), current_card=card)
        .blue_hero("hero_enemy", at=(3, 0, -3))
        .with_actor("hero_gydion")
        .build()
    )
    state.get_hero("hero_gydion").spells = [
        spell.model_copy(deep=True) for spell in fresh_gydion().spells
    ]
    return state


def _prepare(state, *spell_ids: str) -> None:
    for spell in state.get_hero("hero_gydion").spells:
        if spell.id in spell_ids:
            spell.state = CardState.SPELLBOOK
            spell.is_facedown = True


@pytest.mark.effect_contract
def test_all_printed_spell_access_effect_ids_are_registered_with_the_complete_map() -> None:
    state = _state("cantrip")
    hero = state.get_hero("hero_gydion")

    assert len(ACCESS_MAP) == 16
    for effect_id, expected_ids in ACCESS_MAP.items():
        effect = CardEffectRegistry.get(effect_id)
        assert isinstance(effect, SpellAccessEffect)
        card = gydion_card(effect_id)
        steps = effect.get_steps(state, hero, card)
        assert len(steps) == 1
        assert isinstance(steps[0], CastSpellStep)
        assert tuple(steps[0].allowed_spell_ids) == expected_ids
        assert steps[0].caster_id == hero.id


@pytest.mark.effect_contract
def test_prepare_spells_and_archwizard_registration_scope() -> None:
    prepare = CardEffectRegistry.get("prepare_spells")

    assert isinstance(prepare, PrepareSpellsEffect)
    state = _state("prepare_spells")
    steps = prepare.get_steps(
        state,
        state.get_hero("hero_gydion"),
        gydion_card("prepare_spells"),
    )
    assert len(steps) == 2
    assert isinstance(steps[1], PrepareSpellbookStep)
    assert CardEffectRegistry.get("the_archwizard") is not None


@pytest.mark.effect_contract
def test_spell_access_uses_the_current_performer_as_caster() -> None:
    state = _state("cantrip")
    copier = state.get_hero("hero_enemy")
    effect = CardEffectRegistry.get("cantrip")
    assert isinstance(effect, SpellAccessEffect)

    steps = effect.get_steps(state, copier, gydion_card("cantrip"))

    assert len(steps) == 1
    assert isinstance(steps[0], CastSpellStep)
    assert steps[0].caster_id == copier.id


@pytest.mark.effect_flow
def test_copied_cantrip_spends_gydions_spell_and_routes_actions_to_the_copier() -> None:
    state = _state("cantrip")
    copier = state.get_hero("hero_enemy")
    _prepare(state, "shield")
    effect = CardEffectRegistry.get("elementary_abjuration")
    assert isinstance(effect, SpellAccessEffect)
    state.current_actor_id = copier.id
    steps = effect.get_steps(state, copier, gydion_card("elementary_abjuration"))
    push_steps(state, steps)

    action_choice = process_stack(state)

    assert action_choice.input_request is not None
    assert action_choice.input_request.request_type == InputRequestType.CHOOSE_ACTION
    assert action_choice.input_request.player_id == copier.id
    assert state.get_card_by_id("shield").state == CardState.OUTSIDE_SPELLBOOK
    assert action_choice.events[0].metadata == {
        "spell_id": "shield",
        "owner_id": "hero_gydion",
        "caster_id": copier.id,
    }
    state.execution_stack[-1].pending_input = {"selection": "HOLD"}
    finished = process_stack(state)
    assert finished.input_request is None


@pytest.mark.effect_flow
def test_prepare_spells_primary_returns_all_spells_to_the_spellbook() -> None:
    state = _state("prepare_spells")
    run = run_card(state, "hero_gydion")

    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL").finish()

    gydion = state.get_hero("hero_gydion")
    assert len(gydion.spellbook) == 22
    assert all(spell.is_facedown for spell in gydion.spellbook)
    prepared_events = [
        event for event in run.events if event.event_type == GameEventType.SPELLBOOK_PREPARED
    ]
    assert len(prepared_events) == 1
    assert prepared_events[0].metadata["spellbook_count"] == 22


@pytest.mark.effect_flow
def test_cantrip_offers_only_its_three_currently_prepared_spells() -> None:
    state = _state("cantrip")
    _prepare(
        state,
        "shocking_grasp",
        "magic_missile",
        "expeditious_retreat",
        "shield",
    )
    run = run_card(state, "hero_gydion")

    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_CARD)

    assert {option.id for option in run.latest_request.options} == {
        "shocking_grasp",
        "magic_missile",
        "expeditious_retreat",
    }
    run.choose("shocking_grasp").expect_input(InputRequestType.CHOOSE_ACTION).choose("HOLD")
    run.finish()
    assert state.get_card_by_id("shocking_grasp").state == CardState.OUTSIDE_SPELLBOOK


@pytest.mark.parametrize(
    ("card_id", "spell_id"),
    [
        ("elementary_evocation", "burning_hands"),
        ("lesser_evocation", "burning_hands"),
        ("greater_evocation", "burning_hands"),
        ("elementary_abjuration", "shield"),
        ("lesser_abjuration", "shield"),
        ("greater_abjuration", "shield"),
        ("elementary_enchantment", "suggestion"),
        ("lesser_enchantment", "suggestion"),
        ("greater_enchantment", "suggestion"),
    ],
)
@pytest.mark.effect_flow
def test_available_first_six_school_spell_auto_casts(card_id: str, spell_id: str) -> None:
    state = _state(card_id)
    _prepare(state, spell_id)
    run = run_card(state, "hero_gydion")

    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CHOOSE_ACTION)

    assert state.get_card_by_id(spell_id).state == CardState.OUTSIDE_SPELLBOOK
    assert run.latest_request.player_id == "hero_gydion"
    run.choose("HOLD").finish()


@pytest.mark.parametrize(
    "card_id",
    [
        "lesser_necromancy",
        "greater_necromancy",
        "lesser_conjuration",
        "greater_conjuration",
        "lesser_transmutation",
        "greater_transmutation",
    ],
)
@pytest.mark.effect_flow
def test_new_school_primary_offers_only_its_prepared_spell_list(card_id: str) -> None:
    state = _state(card_id)
    _prepare(state, *(spell.id for spell in state.get_hero("hero_gydion").spells))
    run = run_card(state, "hero_gydion")

    run.expect_input(InputRequestType.CHOOSE_ACTION)
    assert {option.id for option in run.latest_request.options} >= {"SKILL", "MOVEMENT", "HOLD"}
    run.choose("SKILL").expect_input(InputRequestType.SELECT_CARD)
    assert {option.id for option in run.latest_request.options} == set(ACCESS_MAP[card_id])
    selected = ACCESS_MAP[card_id][0]
    run.choose(selected).expect_input(InputRequestType.CHOOSE_ACTION).choose("HOLD").finish()

    assert state.get_card_by_id(selected).state == CardState.OUTSIDE_SPELLBOOK
    assert any(event.event_type == GameEventType.SPELL_CAST for event in run.events)


@pytest.mark.effect_flow
def test_spent_allowed_spell_is_not_offered_and_outer_card_continues() -> None:
    state = _state("cantrip")
    _prepare(state, "shield")
    run = run_card(state, "hero_gydion")

    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL").finish()

    assert [spell.id for spell in state.get_hero("hero_gydion").spellbook] == ["shield"]
    assert all(event.event_type != GameEventType.SPELL_CAST for event in run.events)

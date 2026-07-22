from __future__ import annotations

import pytest

import goa2.scripts.gydion_effects  # noqa: F401
from goa2.domain.events import GameEventType
from goa2.domain.input import InputRequestType
from goa2.domain.models import CardState, GamePhase, PassiveTrigger, TeamColor
from goa2.domain.state import GameState
from goa2.domain.views import build_view
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import CheckPassiveAbilitiesStep, PrepareSpellbookStep

from ..builders import EffectScenarioBuilder
from ..gydion_common import fresh_gydion, gydion_card, gydion_spell
from ..runner import run_card


def _state(card_id: str = "prepare_spells"):
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
    gydion = state.get_hero("hero_gydion")
    template = fresh_gydion()
    gydion.spells = [spell.model_copy(deep=True) for spell in template.spells]
    gydion.ultimate_card = template.ultimate_card.model_copy(deep=True)
    gydion.level = 8
    return state, gydion


def _prepare(gydion, *spell_ids: str) -> None:
    for spell in gydion.spells:
        prepared = spell.id in spell_ids
        spell.state = CardState.SPELLBOOK if prepared else CardState.OUTSIDE_SPELLBOOK
        spell.is_facedown = prepared


def _wish_steps(state, caster):
    wish = gydion_spell("wish")
    effect = CardEffectRegistry.get_for_card(wish)
    assert effect is not None
    return effect.get_steps(state, caster, wish)


@pytest.mark.effect_contract
def test_archwizard_and_wish_are_registered() -> None:
    archwizard = CardEffectRegistry.get("the_archwizard")
    assert archwizard is not None
    assert archwizard.get_passive_config().trigger == PassiveTrigger.BEFORE_PREPARE_SPELLBOOK
    assert CardEffectRegistry.get_for_card(gydion_spell("wish")) is not None

    state, gydion = _state()
    prepare = CardEffectRegistry.get("prepare_spells")
    assert prepare is not None
    steps = prepare.get_steps(state, gydion, gydion_card("prepare_spells"))
    assert isinstance(steps[0], CheckPassiveAbilitiesStep)
    assert steps[0].trigger == PassiveTrigger.BEFORE_PREPARE_SPELLBOOK.value
    assert isinstance(steps[1], PrepareSpellbookStep)


@pytest.mark.effect_flow
def test_declining_archwizard_returns_all_spent_spells() -> None:
    state, gydion = _state()
    _prepare(gydion, "wish", "shield")
    run = run_card(state, gydion.id)

    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).choose("NO").finish()

    assert gydion.wish_cast_count == 0
    assert len(gydion.spellbook) == len(gydion.spells) == 22
    assert all(spell.is_facedown for spell in gydion.spellbook)
    assert any(event.event_type == GameEventType.SPELLBOOK_PREPARED for event in run.events)


@pytest.mark.effect_flow
def test_accepting_archwizard_casts_wish_instead_of_preparing() -> None:
    state, gydion = _state()
    _prepare(gydion, *(spell.id for spell in gydion.spells))
    run = run_card(state, gydion.id)

    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).confirm()
    run.expect_input(InputRequestType.SELECT_CARD)
    assert [option.id for option in run.latest_request.options] == ["wish"]
    run.choose("wish")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_CARD)
    assert "wish" not in {option.id for option in run.latest_request.options}
    assert "magic_missile" in {option.id for option in run.latest_request.options}
    run.choose("magic_missile").expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("HOLD").finish()

    assert gydion.wish_cast_count == 1
    assert state.get_card_by_id("wish").state == CardState.OUTSIDE_SPELLBOOK
    assert state.get_card_by_id("magic_missile").state == CardState.OUTSIDE_SPELLBOOK
    assert not any(event.event_type == GameEventType.SPELLBOOK_PREPARED for event in run.events)
    progress = [
        event for event in run.events if event.event_type == GameEventType.WISH_CAST_COUNT_CHANGED
    ]
    assert len(progress) == 1
    assert progress[0].metadata == {"count": 1, "required": 3}


@pytest.mark.effect_flow
def test_archwizard_wish_counts_even_when_caster_holds() -> None:
    state, gydion = _state()
    _prepare(gydion, *(spell.id for spell in gydion.spells))
    run = run_card(state, gydion.id)

    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).confirm()
    run.expect_input(InputRequestType.SELECT_CARD).choose("wish")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("HOLD").finish()

    assert gydion.wish_cast_count == 1
    assert state.get_card_by_id("wish").state == CardState.OUTSIDE_SPELLBOOK
    assert not any(event.event_type == GameEventType.SPELLBOOK_PREPARED for event in run.events)


@pytest.mark.effect_flow
def test_archwizard_is_not_offered_when_wish_is_outside_spellbook() -> None:
    state, gydion = _state()
    _prepare(gydion, "shield")
    run = run_card(state, gydion.id)

    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL").finish()

    assert len(gydion.spellbook) == len(gydion.spells)
    assert any(event.event_type == GameEventType.SPELLBOOK_PREPARED for event in run.events)


@pytest.mark.effect_flow
def test_archwizard_is_offered_when_no_spell_has_been_spent() -> None:
    """Audit §5.4: Wish is offered exactly when nothing has been spent."""
    state, gydion = _state()
    _prepare(gydion, *(spell.id for spell in gydion.spells))
    run = run_card(state, gydion.id)

    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).confirm()
    run.expect_input(InputRequestType.SELECT_CARD).choose("wish")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("HOLD").finish()

    assert gydion.wish_cast_count == 1


@pytest.mark.effect_flow
def test_archwizard_is_offered_when_a_spell_has_been_spent() -> None:
    """Wish may be cast whether or not spells have been spent.

    The only gate is that Wish itself is in the spellbook.
    """
    state, gydion = _state()
    _prepare(gydion, *(spell.id for spell in gydion.spells if spell.id != "shield"))
    run = run_card(state, gydion.id)

    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).confirm()
    run.expect_input(InputRequestType.SELECT_CARD).choose("wish")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("HOLD").finish()

    assert gydion.wish_cast_count == 1
    # Casting Wish replaces the preparation: the spent spell stays spent.
    assert state.get_card_by_id("shield").state == CardState.OUTSIDE_SPELLBOOK
    assert not any(event.event_type == GameEventType.SPELLBOOK_PREPARED for event in run.events)


@pytest.mark.effect_flow
def test_copied_prepare_spells_refills_normally_without_archwizard_offer() -> None:
    copied_prepare = gydion_card("prepare_spells")
    copied_prepare.state = CardState.UNRESOLVED
    copied_prepare.is_facedown = False
    state = (
        EffectScenarioBuilder()
        .line_board()
        .red_hero("hero_gydion", at=(0, 0, 0))
        .blue_hero("hero_copier", at=(3, 0, -3), current_card=copied_prepare)
        .with_actor("hero_copier")
        .build()
    )
    gydion = state.get_hero("hero_gydion")
    template = fresh_gydion()
    gydion.spells = [spell.model_copy(deep=True) for spell in template.spells]
    gydion.ultimate_card = template.ultimate_card.model_copy(deep=True)
    gydion.level = 8
    _prepare(gydion, *(spell.id for spell in gydion.spells))
    run = run_card(state, "hero_copier")

    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL").finish()

    assert len(gydion.spellbook) == len(gydion.spells)
    assert any(event.event_type == GameEventType.SPELLBOOK_PREPARED for event in run.events)


@pytest.mark.effect_flow
def test_wish_counts_when_no_other_spell_is_prepared() -> None:
    state, gydion = _state()
    _prepare(gydion)
    push_steps(state, _wish_steps(state, gydion))

    result = process_stack(state)

    assert result.input_request is None
    assert gydion.wish_cast_count == 1
    assert state.phase == GamePhase.RESOLUTION


@pytest.mark.effect_flow
def test_wish_progress_is_per_caster_public_and_persistent() -> None:
    state, gydion = _state()
    copier = state.get_hero("hero_enemy")
    _prepare(gydion)
    push_steps(state, _wish_steps(state, copier))

    process_stack(state)

    assert gydion.wish_cast_count == 0
    assert copier.wish_cast_count == 1
    view = build_view(state, for_hero_id=gydion.id)
    heroes = {hero["id"]: hero for team in view["teams"].values() for hero in team["heroes"]}
    assert heroes[copier.id]["wish_cast_count"] == 1
    restored = GameState.model_validate_json(state.model_dump_json())
    assert restored.get_hero(copier.id).wish_cast_count == 1


@pytest.mark.effect_flow
def test_in_progress_wish_sequence_survives_json_round_trip() -> None:
    state, gydion = _state()
    _prepare(gydion, "shield", "magic_missile")
    push_steps(state, _wish_steps(state, gydion))

    request = process_stack(state)
    assert request.input_request is not None
    assert request.input_request.request_type == InputRequestType.SELECT_CARD
    assert gydion.wish_cast_count == 1

    restored = GameState.model_validate_json(state.model_dump_json())
    restored_sequence = next(
        step for step in restored.execution_stack if step.type.value == "wish_sequence"
    )
    assert restored_sequence.started is True
    restored.execution_stack[-1].pending_input = {"selection": "shield"}
    action = process_stack(restored)
    assert action.input_request is not None
    assert action.input_request.request_type == InputRequestType.CHOOSE_ACTION
    restored.execution_stack[-1].pending_input = {"selection": "HOLD"}

    result = process_stack(restored)

    assert result.input_request is None
    assert restored.get_hero(gydion.id).wish_cast_count == 1
    assert restored.phase == GamePhase.RESOLUTION


@pytest.mark.effect_flow
def test_third_wish_resolves_selected_spell_before_team_victory() -> None:
    state, gydion = _state()
    _prepare(gydion, "midas_touch")
    gydion.wish_cast_count = 2
    push_steps(state, _wish_steps(state, gydion))

    spell_choice = process_stack(state)
    assert spell_choice.input_request is not None
    assert spell_choice.input_request.request_type == InputRequestType.SELECT_CARD
    assert [option.id for option in spell_choice.input_request.options] == ["midas_touch"]
    state.execution_stack[-1].pending_input = {"selection": "midas_touch"}
    action = process_stack(state)
    assert action.input_request is not None
    assert action.input_request.request_type == InputRequestType.CHOOSE_ACTION
    state.execution_stack[-1].pending_input = {"selection": "SKILL"}
    result = process_stack(state)

    assert gydion.gold > 0
    assert gydion.wish_cast_count == 3
    assert state.phase == GamePhase.GAME_OVER
    assert state.winner == TeamColor.RED
    assert state.victory_condition == "WISH"
    event_types = [event.event_type for event in result.events]
    assert event_types.index(GameEventType.GOLD_GAINED) < event_types.index(GameEventType.GAME_OVER)


@pytest.mark.effect_flow
def test_third_wish_wins_after_selected_spell_fizzles() -> None:
    state, gydion = _state()
    _prepare(gydion, "power_word_kill")
    enemy = state.get_hero("hero_enemy")
    blocker = gydion_card("cantrip")
    blocker.state = CardState.HAND
    enemy.hand = [blocker]
    gydion.wish_cast_count = 2
    push_steps(state, _wish_steps(state, gydion))

    spell_choice = process_stack(state)
    assert spell_choice.input_request is not None
    assert spell_choice.input_request.request_type == InputRequestType.SELECT_CARD
    assert [option.id for option in spell_choice.input_request.options] == ["power_word_kill"]
    state.execution_stack[-1].pending_input = {"selection": "power_word_kill"}
    action = process_stack(state)
    assert action.input_request is not None
    assert action.input_request.request_type == InputRequestType.CHOOSE_ACTION
    state.execution_stack[-1].pending_input = {"selection": "SKILL"}
    result = process_stack(state)

    assert result.input_request is None
    assert state.phase == GamePhase.GAME_OVER
    assert state.winner == TeamColor.RED
    assert state.victory_condition == "WISH"
    assert any(event.event_type == GameEventType.GAME_OVER for event in result.events)

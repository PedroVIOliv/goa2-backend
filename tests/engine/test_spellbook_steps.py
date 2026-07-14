from __future__ import annotations

from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.board import Board
from goa2.domain.events import GameEventType
from goa2.domain.input import InputRequestType
from goa2.domain.models import CardState, Hero, Team, TeamColor
from goa2.domain.models.effect import EffectScope, EffectType, Shape
from goa2.domain.state import GameState
from goa2.engine.effect_manager import EffectManager
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import CastSpellStep, PerformCardActionStep, PrepareSpellbookStep


def _spell_state() -> tuple[GameState, Hero]:
    gydion = HeroRegistry.get("Gydion")
    assert gydion is not None
    gydion.initialize_state()
    gydion.team = TeamColor.RED
    opponent = Hero(
        id="hero_opponent",
        name="Opponent",
        team=TeamColor.BLUE,
        deck=[],
    )
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[gydion], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[opponent], minions=[]),
        },
        current_actor_id=gydion.id,
    )
    return state, gydion


def _prepare(gydion: Hero, *spell_ids: str) -> None:
    for spell in gydion.spells:
        if spell.id in spell_ids:
            spell.state = CardState.SPELLBOOK
            spell.is_facedown = True


def test_prepare_spellbook_returns_all_outside_spells_and_emits_one_public_event() -> None:
    state, gydion = _spell_state()
    push_steps(state, [PrepareSpellbookStep()])

    result = process_stack(state)

    assert len(gydion.spellbook) == 22
    assert all(spell.is_facedown for spell in gydion.spellbook)
    assert [event.event_type for event in result.events] == [GameEventType.SPELLBOOK_PREPARED]
    assert result.events[0].metadata == {
        "returned_spell_ids": sorted(spell.id for spell in gydion.spells),
        "spellbook_count": 22,
    }


def test_prepare_spellbook_is_partial_idempotent_and_expires_returned_spell_effects() -> None:
    state, gydion = _spell_state()
    _prepare(gydion, "shocking_grasp", "magic_missile")
    EffectManager.create_effect(
        state,
        source_id=str(gydion.id),
        source_card_id="shield",
        effect_type=EffectType.ATTACK_IMMUNITY,
        scope=EffectScope(shape=Shape.GLOBAL),
        is_active=True,
    )

    push_steps(state, [PrepareSpellbookStep()])
    first = process_stack(state)
    push_steps(state, [PrepareSpellbookStep()])
    second = process_stack(state)

    assert len(gydion.spellbook) == 22
    assert len({id(spell) for spell in gydion.spells}) == 22
    assert state.active_effects == []
    assert state.get_card_by_id("shield").is_active is False  # type: ignore[union-attr]
    assert first.events[0].metadata["returned_spell_ids"] == sorted(
        {spell.id for spell in gydion.spells} - {"shocking_grasp", "magic_missile"}
    )
    assert second.events[0].metadata == {
        "returned_spell_ids": [],
        "spellbook_count": 22,
    }


def test_cast_spell_prompts_for_multiple_and_rejects_stale_input_without_spending() -> None:
    state, gydion = _spell_state()
    allowed = ["shocking_grasp", "magic_missile", "expeditious_retreat"]
    _prepare(gydion, *allowed)
    push_steps(state, [CastSpellStep(allowed_spell_ids=allowed)])

    first = process_stack(state)
    assert first.input_request is not None
    assert first.input_request.request_type == InputRequestType.SELECT_CARD
    assert first.input_request.player_id == gydion.id
    assert {option.id for option in first.input_request.options} == set(allowed)

    state.execution_stack[-1].pending_input = {"selection": "shield"}
    stale = process_stack(state)

    assert stale.input_request is not None
    assert stale.input_request.request_type == InputRequestType.SELECT_CARD
    assert stale.events == []
    assert {spell.id for spell in gydion.spellbook} == set(allowed)
    assert gydion.cast_spells == [spell for spell in gydion.spells if spell.id not in allowed]


def test_cast_spell_spends_before_action_choice_and_records_owner_caster_source() -> None:
    state, gydion = _spell_state()
    allowed = ["shocking_grasp", "magic_missile", "expeditious_retreat"]
    _prepare(gydion, *allowed)
    push_steps(state, [CastSpellStep(allowed_spell_ids=allowed)])
    process_stack(state)
    state.execution_stack[-1].pending_input = {"selection": "magic_missile"}

    result = process_stack(state)

    spell = state.get_card_by_id("magic_missile")
    assert spell is not None
    assert spell.state == CardState.OUTSIDE_SPELLBOOK
    assert spell.is_facedown is False
    assert len(gydion.spellbook) == 2
    assert result.input_request is not None
    assert result.input_request.request_type == InputRequestType.CHOOSE_ACTION
    assert result.input_request.player_id == gydion.id
    assert [event.event_type for event in result.events] == [GameEventType.SPELL_CAST]
    assert result.events[0].metadata == {
        "spell_id": "magic_missile",
        "owner_id": gydion.id,
        "caster_id": gydion.id,
    }
    assert state.execution_context["spell_owner_id"] == gydion.id
    assert state.execution_context["spell_caster_id"] == gydion.id
    assert state.execution_context["cast_spell_id"] == "magic_missile"
    assert isinstance(state.execution_stack[-1], PerformCardActionStep)


def test_cast_spell_auto_selects_one_and_no_options_is_a_clean_noop() -> None:
    state, gydion = _spell_state()
    _prepare(gydion, "shield")
    push_steps(state, [CastSpellStep(allowed_spell_ids=["shield"])])

    selected = process_stack(state)

    assert selected.input_request is not None
    assert selected.input_request.request_type == InputRequestType.CHOOSE_ACTION
    assert [event.event_type for event in selected.events] == [GameEventType.SPELL_CAST]
    assert gydion.spellbook == []

    push_steps(state, [CastSpellStep(allowed_spell_ids=["burning_hands"])])
    empty = process_stack(state)
    assert empty.input_request is not None  # resumes the existing action chooser
    assert empty.events == []
    assert state.get_card_by_id("burning_hands").state == CardState.OUTSIDE_SPELLBOOK  # type: ignore[union-attr]


def test_cast_spell_uses_explicit_caster_context_while_spending_the_unique_owners_spell() -> None:
    state, gydion = _spell_state()
    opponent = state.get_hero("hero_opponent")
    assert opponent is not None
    _prepare(gydion, "shield")
    state.execution_context["copying_hero"] = opponent.id
    push_steps(
        state,
        [CastSpellStep(allowed_spell_ids=["shield"], caster_key="copying_hero")],
    )

    result = process_stack(state)

    assert result.input_request is not None
    assert result.input_request.request_type == InputRequestType.CHOOSE_ACTION
    assert result.input_request.player_id == opponent.id
    assert gydion.spellbook == []
    assert result.events[0].actor_id == opponent.id
    assert result.events[0].metadata == {
        "spell_id": "shield",
        "owner_id": gydion.id,
        "caster_id": opponent.id,
    }


def test_cast_step_stack_round_trips_at_spell_and_action_choices() -> None:
    state, gydion = _spell_state()
    _prepare(gydion, "shocking_grasp", "magic_missile")
    push_steps(
        state,
        [CastSpellStep(allowed_spell_ids=["shocking_grasp", "magic_missile"])],
    )
    spell_choice = process_stack(state)
    assert spell_choice.input_request is not None

    restored_at_spell = GameState.model_validate_json(state.model_dump_json())
    resumed_spell_choice = process_stack(restored_at_spell)
    assert resumed_spell_choice.input_request is not None
    assert resumed_spell_choice.input_request.request_type == InputRequestType.SELECT_CARD

    restored_at_spell.execution_stack[-1].pending_input = {"selection": "shocking_grasp"}
    action_choice = process_stack(restored_at_spell)
    assert action_choice.input_request is not None
    assert action_choice.input_request.request_type == InputRequestType.CHOOSE_ACTION

    restored_at_action = GameState.model_validate_json(restored_at_spell.model_dump_json())
    resumed_action_choice = process_stack(restored_at_action)
    assert resumed_action_choice.input_request is not None
    assert resumed_action_choice.input_request.request_type == InputRequestType.CHOOSE_ACTION
    assert restored_at_action.execution_context["spell_owner_id"] == gydion.id
    assert restored_at_action.execution_context["spell_caster_id"] == gydion.id
    assert restored_at_action.execution_context["cast_spell_id"] == "shocking_grasp"

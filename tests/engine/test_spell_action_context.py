from __future__ import annotations

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardState,
    CardTier,
    GamePhase,
    Hero,
    Minion,
    MinionType,
    PassiveTrigger,
    SpellCard,
    Team,
    TeamColor,
)
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps, submit_input
from goa2.engine.steps import (
    CheckPassiveAbilitiesStep,
    PerformCardActionStep,
    RestoreActionContextStep,
)


def _state(*, with_target: bool = True) -> tuple[GameState, Card, SpellCard]:
    outer = Card(
        id="outer_skill",
        name="Outer Skill",
        tier=CardTier.I,
        color=CardColor.BLUE,
        initiative=5,
        primary_action=ActionType.SKILL,
        effect_id="outer_skill",
        effect_text="",
        state=CardState.UNRESOLVED,
        is_facedown=False,
    )
    spell = SpellCard.define(
        id="nested_attack",
        name="Nested Attack",
        spell_rank=0,
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        range_value=1,
        effect_text="",
    )
    caster = Hero(
        id="hero_caster",
        name="Caster",
        team=TeamColor.RED,
        deck=[outer],
        spells=[spell],
        current_turn_card=outer,
    )
    enemy = Minion(
        id="enemy_minion",
        name="Enemy",
        team=TeamColor.BLUE,
        type=MinionType.MELEE,
    )
    hexes = {Hex(q=0, r=0, s=0), Hex(q=1, r=0, s=-1)}
    board = Board(zones={"z1": Zone(id="z1", hexes=hexes, neighbors=[])})
    board.populate_tiles_from_zones()
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[caster]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE,
                minions=[enemy] if with_target else [],
            ),
        },
        phase=GamePhase.RESOLUTION,
        current_actor_id=caster.id,
    )
    state.place_entity(caster.id, Hex(q=0, r=0, s=0))
    if with_target:
        state.place_entity(enemy.id, Hex(q=1, r=0, s=-1))
    state.execution_context.update(
        {
            "selected_card": spell.id,
            "spell_owner": caster.id,
            "current_action_type": ActionType.SKILL,
            "current_card_id": outer.id,
            "performing_card_id": outer.id,
            "performing_card_owner_id": caster.id,
        }
    )
    return state, outer, spell


def _performed_step(*, suppress_after_resolve_card: bool = True) -> PerformCardActionStep:
    return PerformCardActionStep(
        card_key="selected_card",
        card_owner_key="spell_owner",
        hero_id="hero_caster",
        suppress_after_resolve_card=suppress_after_resolve_card,
    )


def test_nested_primary_action_builds_full_hooks_and_restores_source() -> None:
    state, outer, spell = _state()
    step = _performed_step()
    step.pending_input = {"selection": "ATTACK"}

    result = step.resolve(state, state.execution_context)

    triggers = [
        nested.trigger
        for nested in result.new_steps
        if isinstance(nested, CheckPassiveAbilitiesStep)
    ]
    assert triggers == [
        PassiveTrigger.BEFORE_ACTION.value,
        PassiveTrigger.BEFORE_ATTACK.value,
        PassiveTrigger.AFTER_ATTACK.value,
        PassiveTrigger.AFTER_BASIC_ACTION.value,
        PassiveTrigger.AFTER_PRIMARY_ACTION.value,
    ]
    assert PassiveTrigger.AFTER_RESOLVE_CARD.value not in triggers
    assert isinstance(result.new_steps[-1], RestoreActionContextStep)
    assert state.execution_context["current_action_type"] == ActionType.ATTACK
    assert state.execution_context["current_card_id"] == spell.id
    assert state.get_performing_card("hero_caster") is spell

    result.new_steps[-1].resolve(state, state.execution_context)
    assert state.execution_context["current_action_type"] == ActionType.SKILL
    assert state.execution_context["current_card_id"] == outer.id
    assert state.get_performing_card("hero_caster") is outer
    assert "action_context_stack" not in state.execution_context


def test_non_spell_performed_action_keeps_after_resolve_card_hook() -> None:
    state, _, _ = _state()
    step = _performed_step(suppress_after_resolve_card=False)
    step.pending_input = {"selection": "ATTACK"}

    result = step.resolve(state, state.execution_context)

    triggers = [
        nested.trigger
        for nested in result.new_steps
        if isinstance(nested, CheckPassiveAbilitiesStep)
    ]
    assert triggers[-1] == PassiveTrigger.AFTER_RESOLVE_CARD.value


def test_nested_action_round_trips_at_chooser_and_target_then_restores() -> None:
    state, outer, spell = _state()
    push_steps(state, [_performed_step()])

    result = process_stack(state)
    assert result.input_request is not None
    assert result.input_request.request_type == InputRequestType.CHOOSE_ACTION

    state = GameState.model_validate_json(state.model_dump_json())
    submit_input(state, {"selection": "ATTACK"})
    result = process_stack(state)
    assert result.input_request is not None
    assert result.input_request.request_type == InputRequestType.SELECT_UNIT
    assert state.execution_context["current_card_id"] == spell.id
    assert state.get_performing_card("hero_caster").id == spell.id

    state = GameState.model_validate_json(state.model_dump_json())
    submit_input(state, {"selection": "enemy_minion"})
    result = process_stack(state)
    assert result.input_request is None
    assert state.execution_context["current_action_type"] == ActionType.SKILL
    assert state.execution_context["current_card_id"] == outer.id
    assert state.get_performing_card("hero_caster").id == outer.id
    assert "action_context_stack" not in state.execution_context


def test_failed_mandatory_nested_action_restores_outer_context() -> None:
    state, outer, _ = _state(with_target=False)
    push_steps(state, [_performed_step()])
    result = process_stack(state)
    assert result.input_request is not None

    submit_input(state, {"selection": "ATTACK"})
    result = process_stack(state)

    assert result.input_request is None
    assert state.execution_context["current_action_type"] == ActionType.SKILL
    assert state.execution_context["current_card_id"] == outer.id
    assert state.get_performing_card("hero_caster").id == outer.id
    assert "action_context_stack" not in state.execution_context

from __future__ import annotations

from goa2.domain.input import InputRequestType
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardState,
    CardTier,
)
from goa2.domain.models.effect import ActiveEffect, DurationType, EffectScope, EffectType, Shape
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import ForceDiscardStep, SetContextFlagStep
from tests.engine.effects.builders import EffectScenarioBuilder


def _card(card_id: str, *, basic: bool) -> Card:
    return Card(
        id=card_id,
        name=card_id,
        tier=CardTier.UNTIERED if basic else CardTier.III,
        color=CardColor.GOLD if basic else CardColor.BLUE,
        initiative=5,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        effect_id="",
        effect_text="",
        state=CardState.HAND,
        is_facedown=False,
    )


def _state():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1)])
        .red_hero("hero_actor", at=(0, 0, 0))
        .blue_hero("hero_victim", at=(1, 0, -1))
        .with_actor("hero_actor")
        .build()
    )
    state.execution_context["victim"] = "hero_victim"
    return state


def test_filtered_force_discard_offers_only_requested_basic_status() -> None:
    state = _state()
    victim = state.get_hero("hero_victim")
    victim.hand = [_card("basic", basic=True), _card("non_basic", basic=False)]
    push_steps(state, [ForceDiscardStep(victim_key="victim", card_is_basic=False)])

    request = process_stack(state)

    assert request.input_request is not None
    assert request.input_request.request_type == InputRequestType.SELECT_CARD
    assert request.input_request.player_id == "hero_victim"
    assert {option.id for option in request.input_request.options} == {"non_basic"}


def test_filtered_force_discard_no_match_is_noop_and_continues() -> None:
    state = _state()
    state.get_hero("hero_victim").hand = [_card("non_basic", basic=False)]
    push_steps(
        state,
        [
            ForceDiscardStep(victim_key="victim", card_is_basic=True),
            SetContextFlagStep(key="continued", value=True),
        ],
    )

    result = process_stack(state)

    assert result.input_request is None
    assert state.execution_context["continued"] is True
    assert [card.id for card in state.get_hero("hero_victim").hand] == ["non_basic"]


def test_filtered_force_discard_allows_mrak_shield_as_replacement() -> None:
    state = _state()
    victim = state.get_hero("hero_victim")
    victim.hand = [_card("required_non_basic", basic=False)]
    shield = _card("discard_shield", basic=True)
    shield.state = CardState.RESOLVED
    victim.played_cards = [shield]
    state.active_effects.append(
        ActiveEffect(
            id="shield_effect",
            source_id=victim.id,
            source_card_id=shield.id,
            effect_type=EffectType.DISCARD_SHIELD,
            scope=EffectScope(shape=Shape.POINT, origin_id=victim.id),
            duration=DurationType.THIS_ROUND,
            created_at_turn=state.turn,
            created_at_round=state.round,
            is_active=True,
        )
    )
    push_steps(state, [ForceDiscardStep(victim_key="victim", card_is_basic=False)])

    request = process_stack(state)

    assert request.input_request is not None
    assert {option.id for option in request.input_request.options} == {
        "required_non_basic",
        "discard_shield",
    }
    state.execution_stack[-1].pending_input = {"selection": "discard_shield"}
    process_stack(state)
    assert [card.id for card in victim.hand] == ["required_non_basic"]
    assert [card.id for card in victim.discard_pile] == ["discard_shield"]


def test_filtered_force_discard_does_not_enable_shield_without_matching_hand_card() -> None:
    state = _state()
    victim = state.get_hero("hero_victim")
    victim.hand = [_card("wrong_basic", basic=True)]
    shield = _card("discard_shield", basic=True)
    shield.state = CardState.RESOLVED
    victim.played_cards = [shield]
    state.active_effects.append(
        ActiveEffect(
            id="shield_effect",
            source_id=victim.id,
            source_card_id=shield.id,
            effect_type=EffectType.DISCARD_SHIELD,
            scope=EffectScope(shape=Shape.POINT, origin_id=victim.id),
            duration=DurationType.THIS_ROUND,
            created_at_turn=state.turn,
            created_at_round=state.round,
            is_active=True,
        )
    )
    push_steps(state, [ForceDiscardStep(victim_key="victim", card_is_basic=False)])

    result = process_stack(state)

    assert result.input_request is None
    assert [card.id for card in victim.played_cards if card is not None] == ["discard_shield"]

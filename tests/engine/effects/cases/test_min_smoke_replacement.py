"""Min Smoke Bomb re-placement contracts."""

from __future__ import annotations

import pytest

import goa2.scripts.min_effects  # noqa: F401
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardState,
    CardTier,
    Token,
    TokenType,
)
from goa2.domain.models.effect import DurationType, EffectScope, EffectType, Shape
from goa2.engine.effect_manager import EffectManager
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.stats import compute_card_stats
from goa2.engine.steps import PlaceTokenStep

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _hex_disk(radius: int) -> list[tuple[int, int, int]]:
    return [
        (q, r, -q - r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if abs(q + r) <= radius
    ]


def _state_with_smoke():
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero("hero_min", at=(-1, 0, 1))
        .red_hero("red_target", at=(2, 0, -2))
        .blue_hero("blue_enemy", at=(0, 0, 0))
        .with_actor("hero_min")
        .build()
    )
    smoke = Token(
        id="smoke",
        name="Smoke Bomb",
        token_type=TokenType.SMOKE_BOMB,
        owner_id="hero_min",
    )
    state.register_entity(smoke)
    state.token_pool[TokenType.SMOKE_BOMB] = [smoke]
    state.place_entity("smoke", Hex(q=0, r=1, s=-1))
    effect = EffectManager.create_effect(
        state=state,
        source_id="hero_min",
        effect_type=EffectType.LOS_BLOCKER,
        scope=EffectScope(shape=Shape.POINT, origin_id="smoke"),
        duration=DurationType.PASSIVE,
        is_active=True,
    )
    return state, effect


@pytest.mark.effect_contract
def test_replacing_existing_smoke_preserves_its_los_effect() -> None:
    state, effect = _state_with_smoke()
    assert state.validator.can_be_targeted(state, "blue_enemy", "red_target").allowed
    context = {
        "swap_token_id": "smoke",
        "smoke_place_hex": Hex(q=1, r=0, s=-1),
    }

    result = PlaceTokenStep(
        token_type=TokenType.SMOKE_BOMB,
        hex_key="smoke_place_hex",
        existing_token_key="swap_token_id",
    ).resolve(state, context)

    assert state.get_position("smoke") == Hex(q=1, r=0, s=-1)
    assert any(active.id == effect.id for active in state.active_effects)
    assert not state.validator.can_be_targeted(state, "blue_enemy", "red_target").allowed
    assert [event.event_type.value for event in result.events] == ["TOKEN_MOVED"]


@pytest.mark.effect_flow
def test_cobra_stance_replaces_smoke_without_losing_los_effect() -> None:
    state, effect = _state_with_smoke()
    state.get_hero("hero_min").current_turn_card = hero_card("Min", "cobra_stance")

    run = run_card(state, "hero_min")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_enemy")
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("smoke")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=1, r=0, s=-1))
    run.finish()

    assert state.get_position("smoke") == Hex(q=1, r=0, s=-1)
    assert any(active.id == effect.id for active in state.active_effects)


@pytest.mark.effect_flow
def test_ruse_replaces_smoke_without_losing_los_effect() -> None:
    attack = Card(
        id="enemy_attack",
        name="Enemy Attack",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=1,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        secondary_actions={},
        range_value=1,
        effect_id="",
        effect_text="",
        is_facedown=False,
    )
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero("hero_min", at=(1, 0, -1))
        .blue_hero("blue_enemy", at=(0, 0, 0), current_card=attack)
        .with_actor("blue_enemy")
        .build()
    )
    ruse = hero_card("Min", "ruse")
    ruse.state = CardState.HAND
    state.get_hero("hero_min").hand = [ruse]
    smoke = Token(
        id="smoke",
        name="Smoke Bomb",
        token_type=TokenType.SMOKE_BOMB,
        owner_id="hero_min",
    )
    state.register_entity(smoke)
    state.token_pool[TokenType.SMOKE_BOMB] = [smoke]
    state.place_entity("smoke", Hex(q=3, r=0, s=-3))
    effect = EffectManager.create_effect(
        state=state,
        source_id="hero_min",
        effect_type=EffectType.LOS_BLOCKER,
        scope=EffectScope(shape=Shape.POINT, origin_id="smoke"),
        duration=DurationType.PASSIVE,
        is_active=True,
    )

    run = run_card(state, "blue_enemy")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_min")
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("ruse")
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("smoke")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=2, r=0, s=-2))
    run.finish()

    assert state.get_position("smoke") == Hex(q=2, r=0, s=-2)
    assert any(active.id == effect.id for active in state.active_effects)


@pytest.mark.effect_contract
@pytest.mark.parametrize("card_id", ["cobra_stance", "ruse"])
def test_smoke_replacement_cards_relocate_the_selected_token(card_id: str) -> None:
    state, _ = _state_with_smoke()
    hero = state.get_hero("hero_min")
    card = hero_card("Min", card_id)
    effect = CardEffectRegistry.get(card_id)
    stats = compute_card_stats(state, hero.id, card)

    if card_id == "ruse":
        steps = effect.build_defense_steps(
            state,
            hero,
            card,
            stats,
            {"attacker_id": "blue_enemy", "defender_id": "hero_min"},
        )
    else:
        steps = effect.build_steps(state, hero, card, stats)

    placement = next(step for step in steps if isinstance(step, PlaceTokenStep))
    assert placement.existing_token_key == "swap_token_id"

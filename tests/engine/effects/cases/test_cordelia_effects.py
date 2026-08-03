"""Behavioral contracts for Cordelia's card effects."""

from __future__ import annotations

import pytest

import goa2.scripts.cordelia_effects  # noqa: F401 - register Cordelia effects
from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import CardState, StatType
from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.state import GameState
from goa2.domain.views import build_view
from goa2.engine.effect_manager import EffectManager
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.stats import get_computed_stat
from goa2.engine.steps import DiscardCardStep, FinalizeHeroTurnStep

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import EffectRun, run_card


def _hex_disk(radius: int) -> list[tuple[int, int, int]]:
    return [
        (q, r, -q - r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if max(abs(q), abs(r), abs(-q - r)) <= radius
    ]


def _option_set(run: EffectRun) -> set:
    assert run.latest_request is not None
    values = set()
    for option in run.latest_request.options:
        metadata = getattr(option, "metadata", None)
        values.add(metadata["raw"] if metadata and "raw" in metadata else option.id)
    return values


def _put_card(state, hero_id: str, card_id: str, zone: str):
    card = hero_card("Cordelia", card_id)
    card.is_facedown = False
    hero = state.get_hero(hero_id)
    if zone == "hand":
        card.state = CardState.HAND
        hero.hand.append(card)
    elif zone == "discard":
        card.state = CardState.DISCARD
        hero.discard_pile.append(card)
    elif zone == "played":
        card.state = CardState.RESOLVED
        hero.played_cards.append(card)
    else:  # pragma: no cover - test helper guard
        raise ValueError(zone)
    return card


def _position(state, unit_id: str) -> tuple[int, int, int] | None:
    position = state.get_position(unit_id)
    return (position.q, position.r, position.s) if position else None


@pytest.mark.effect_contract
def test_every_cordelia_card_has_a_registered_effect() -> None:
    effect_ids = {
        "witching_hour",
        "this_is_my_broomstick",
        "fatal_bonds",
        "toxic_tranquility",
        "potion_explosion",
        "enchanted_path",
        "recipe_for_disaster",
        "broomstick_beatdown",
        "collateral_misfortune",
        "fungal_favor",
        "vile_vial",
        "candy_trail",
        "trouble_brewing",
        "broom_for_improvement",
        "healing_spores",
        "charmed_step",
        "bewitch",
        "jinx",
    }
    assert {
        effect_id for effect_id in effect_ids if CardEffectRegistry.get(effect_id)
    } == effect_ids


@pytest.mark.effect_flow
@pytest.mark.parametrize(
    ("card_id", "bonus"),
    [
        ("broom_for_improvement", 1),
        ("broomstick_beatdown", 2),
        ("this_is_my_broomstick", 3),
    ],
)
def test_broom_bonus_applies_to_basic_actions_only_after_the_attack(
    card_id: str, bonus: int
) -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero(
            "hero_cordelia",
            at=(0, 0, 0),
            current_card=hero_card("Cordelia", card_id),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_cordelia")
        .build()
    )

    run = run_card(state, "hero_cordelia")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion").finish()

    basic = hero_card("Cordelia", "bewitch")
    non_basic = hero_card("Cordelia", "collateral_misfortune")
    assert (
        get_computed_stat(state, "hero_cordelia", StatType.ATTACK, 3, performing_card=basic)
        == 3 + bonus
    )
    assert (
        get_computed_stat(state, "hero_cordelia", StatType.ATTACK, 3, performing_card=non_basic)
        == 3
    )
    assert get_computed_stat(state, "hero_cordelia", StatType.RANGE, 3, performing_card=basic) == 3


@pytest.mark.effect_flow
def test_collateral_uses_numbered_mode_before_target_selection() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero(
            "hero_cordelia",
            at=(0, 0, 0),
            current_card=hero_card("Cordelia", "collateral_misfortune"),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .blue_hero("blue_hero", at=(2, 0, -2))
        .blue_minion("isolated", at=(0, 3, -3))
        .with_actor("hero_cordelia")
        .build()
    )

    run = run_card(state, "hero_cordelia")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER)
    assert _option_set(run) == {1, 2}
    run.choose(2)
    run.expect_input(InputRequestType.SELECT_UNIT)
    assert "blue_minion" in _option_set(run)
    assert "isolated" not in _option_set(run)
    run.choose("blue_minion").finish()


@pytest.mark.effect_flow
@pytest.mark.parametrize(
    ("first_mode", "first_target", "second_target"),
    [
        (1, "adjacent_target", "linked_target"),
        (2, "linked_target", "adjacent_target"),
    ],
)
def test_fatal_bonds_can_attack_once_with_each_bullet_in_either_order(
    first_mode: int,
    first_target: str,
    second_target: str,
) -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(5))
        .red_hero(
            "hero_cordelia",
            at=(0, 0, 0),
            current_card=hero_card("Cordelia", "fatal_bonds"),
        )
        .blue_minion("adjacent_target", at=(1, 0, -1))
        .blue_minion("linked_target", at=(3, 0, -3))
        .blue_hero("linking_hero", at=(4, 0, -4))
        .with_actor("hero_cordelia")
        .build()
    )

    run = run_card(state, "hero_cordelia")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(first_mode)
    run.expect_input(InputRequestType.SELECT_UNIT).choose(first_target)
    run.expect_input(InputRequestType.SELECT_UNIT)
    assert second_target in _option_set(run)
    assert first_target not in _option_set(run)
    run.choose(second_target).finish()

    assert "adjacent_target" not in state.entity_locations
    assert "linked_target" not in state.entity_locations


def _healing_state(card_id: str = "healing_spores"):
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(5))
        .red_hero(
            "hero_cordelia",
            at=(0, 0, 0),
            current_card=hero_card("Cordelia", card_id),
        )
        .red_hero("friendly", at=(0, 1, -1))
        .blue_hero("enemy_a", at=(2, 0, -2))
        .blue_hero("enemy_b", at=(-2, 0, 2))
        .with_actor("hero_cordelia")
        .build()
    )
    discarded = _put_card(state, "friendly", "bewitch", "discard")
    state.get_hero("enemy_a").gold = 3
    state.get_hero("enemy_b").gold = 3
    return state, discarded


@pytest.mark.effect_flow
@pytest.mark.parametrize("card_id", ["healing_spores", "fungal_favor"])
def test_healing_family_skip_retrieval_causes_no_coin_loss(card_id: str) -> None:
    state, discarded = _healing_state(card_id)

    run = run_card(state, "hero_cordelia")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("friendly")
    run.expect_input(InputRequestType.SELECT_CARD).skip().finish()

    assert discarded in state.get_hero("friendly").discard_pile
    assert state.get_hero("enemy_a").gold == 3
    assert state.get_hero("enemy_b").gold == 3


@pytest.mark.effect_flow
def test_healing_spores_retrieval_then_one_enemy_loses_one_coin() -> None:
    state, discarded = _healing_state()

    run = run_card(state, "hero_cordelia")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("friendly")
    run.expect_input(InputRequestType.SELECT_CARD).choose(discarded.id)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_a").finish()

    assert discarded in state.get_hero("friendly").hand
    assert state.get_hero("enemy_a").gold == 2
    assert state.get_hero("enemy_b").gold == 3


@pytest.mark.effect_flow
def test_healing_spores_does_nothing_without_an_eligible_friendly_hero() -> None:
    state, _discarded = _healing_state()
    state.get_hero("friendly").discard_pile.clear()

    run = run_card(state, "hero_cordelia")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL").finish()

    assert state.get_hero("enemy_a").gold == 3
    assert state.get_hero("enemy_b").gold == 3


@pytest.mark.effect_flow
def test_toxic_tranquility_charges_each_enemy_after_retrieval() -> None:
    state, discarded = _healing_state("toxic_tranquility")

    run = run_card(state, "hero_cordelia")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("friendly")
    run.expect_input(InputRequestType.SELECT_CARD).choose(discarded.id).finish()

    assert state.get_hero("enemy_a").gold == 2
    assert state.get_hero("enemy_b").gold == 2


@pytest.mark.effect_flow
def test_vile_vial_gold_card_is_tier_zero_revealed_faceup_and_discarded() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero(
            "hero_cordelia",
            at=(0, 0, 0),
            current_card=hero_card("Cordelia", "vile_vial"),
        )
        .blue_hero("enemy", at=(2, 0, -2))
        .with_actor("hero_cordelia")
        .build()
    )
    gold = _put_card(state, "enemy", "bewitch", "hand")
    hidden = _put_card(state, "enemy", "broom_for_improvement", "hand")

    run = run_card(state, "hero_cordelia")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy")
    run.expect_input(InputRequestType.SELECT_CARD)
    assert run.latest_request.player_id == "enemy"
    run.choose(gold.id).finish()

    assert state.get_hero("hero_cordelia").gold == 0
    assert gold in state.get_hero("enemy").discard_pile
    assert hidden in state.get_hero("enemy").hand
    public = build_view(state, for_hero_id="hero_cordelia")
    assert public["card_reveal"]["card"]["id"] == gold.id
    assert public["card_reveal"]["card"]["is_facedown"] is False
    assert public["card_reveal"]["tier_value"] == 0
    assert public["card_reveal"]["discarded"] is True
    enemy_view = public["teams"]["BLUE"]["heroes"][0]
    assert enemy_view["hand"] == []
    assert any(event.event_type == GameEventType.CARD_REVEALED for event in run.events)

    restored = GameState.model_validate_json(state.model_dump_json())
    restored_reveal = build_view(restored, for_hero_id="hero_cordelia")["card_reveal"]
    assert restored_reveal["card"]["id"] == gold.id
    assert restored_reveal["tier_value"] == 0


@pytest.mark.effect_contract
def test_direct_reveal_survives_revealers_turn_then_clears_after_another_turn() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(2))
        .red_hero("hero_cordelia", at=(0, 0, 0))
        .blue_hero("enemy", at=(1, 0, -1))
        .with_actor("hero_cordelia")
        .with_unresolved_heroes([])
        .build()
    )
    revealed = _put_card(state, "enemy", "bewitch", "hand")
    state.card_reveal = {
        "revealer_id": "hero_cordelia",
        "target_unit_id": "enemy",
        "owner_id": "enemy",
        "card_id": revealed.id,
        "tier_value": 0,
    }

    push_steps(state, [FinalizeHeroTurnStep(hero_id="hero_cordelia")])
    process_stack(state)
    assert build_view(state)["card_reveal"]["card"]["id"] == revealed.id

    push_steps(state, [FinalizeHeroTurnStep(hero_id="enemy")])
    process_stack(state)
    assert state.card_reveal is None
    assert build_view(state)["card_reveal"] is None


@pytest.mark.effect_flow
def test_vile_vial_tier_two_grants_two_coins_and_keeps_card_in_hand() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero(
            "hero_cordelia",
            at=(0, 0, 0),
            current_card=hero_card("Cordelia", "vile_vial"),
        )
        .blue_hero("enemy", at=(2, 0, -2))
        .with_actor("hero_cordelia")
        .build()
    )
    tier_two = _put_card(state, "enemy", "fungal_favor", "hand")

    run = run_card(state, "hero_cordelia")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy")
    run.expect_input(InputRequestType.SELECT_CARD).choose(tier_two.id).finish()

    assert state.get_hero("hero_cordelia").gold == 2
    assert tier_two in state.get_hero("enemy").hand
    assert build_view(state)["card_reveal"]["discarded"] is False


@pytest.mark.effect_flow
def test_potion_explosion_discards_a_tier_two_card_because_two_is_less_than_three() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero(
            "hero_cordelia",
            at=(0, 0, 0),
            current_card=hero_card("Cordelia", "potion_explosion"),
        )
        .blue_hero("enemy", at=(2, 0, -2))
        .with_actor("hero_cordelia")
        .build()
    )
    tier_two = _put_card(state, "enemy", "fungal_favor", "hand")

    run = run_card(state, "hero_cordelia")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy")
    run.expect_input(InputRequestType.SELECT_CARD).choose(tier_two.id).finish()

    assert state.get_hero("hero_cordelia").gold == 2
    assert tier_two in state.get_hero("enemy").discard_pile


@pytest.mark.effect_flow
@pytest.mark.parametrize("card_id", ["charmed_step", "candy_trail"])
def test_charmed_family_places_next_to_target_then_pushes_from_new_position(
    card_id: str,
) -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero(
            "hero_cordelia",
            at=(0, 0, 0),
            current_card=hero_card("Cordelia", card_id),
        )
        .blue_hero("enemy", at=(2, 0, -2))
        .with_actor("hero_cordelia")
        .build()
    )

    run = run_card(state, "hero_cordelia")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 1, "r": 0, "s": -1}).finish()

    assert _position(state, "hero_cordelia") == (1, 0, -1)
    assert _position(state, "enemy") == (3, 0, -3)


@pytest.mark.effect_flow
def test_enchanted_path_two_space_push_stops_at_board_edge() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3)])
        .red_hero(
            "hero_cordelia",
            at=(0, 0, 0),
            current_card=hero_card("Cordelia", "enchanted_path"),
        )
        .blue_hero("enemy", at=(2, 0, -2))
        .with_actor("hero_cordelia")
        .build()
    )

    run = run_card(state, "hero_cordelia")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 1, "r": 0, "s": -1})
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2).finish()

    assert _position(state, "enemy") == (3, 0, -3)


@pytest.mark.effect_flow
def test_recipe_places_enemy_minion_then_optionally_retrieves_basic_card() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(5))
        .red_hero(
            "hero_cordelia",
            at=(0, 0, 0),
            current_card=hero_card("Cordelia", "recipe_for_disaster"),
        )
        .blue_minion("enemy_minion", at=(3, 0, -3))
        .with_actor("hero_cordelia")
        .build()
    )
    basic = _put_card(state, "hero_cordelia", "jinx", "discard")
    _put_card(state, "hero_cordelia", "healing_spores", "discard")

    run = run_card(state, "hero_cordelia")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_minion")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 1, "r": 0, "s": -1})
    run.expect_input(InputRequestType.SELECT_CARD)
    assert _option_set(run) == {basic.id}
    run.choose(basic.id).finish()

    assert _position(state, "enemy_minion") == (1, 0, -1)
    assert basic in state.get_hero("hero_cordelia").hand


@pytest.mark.effect_flow
def test_bewitch_skips_its_penalty_when_it_would_reduce_range_below_one() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero(
            "hero_cordelia",
            at=(0, 0, 0),
            current_card=hero_card("Cordelia", "bewitch"),
        )
        .blue_minion("attack_target", at=(1, 0, -1))
        .blue_hero("enemy", at=(2, 0, -2))
        .with_actor("hero_cordelia")
        .build()
    )

    run = run_card(state, "hero_cordelia")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("attack_target").finish()

    assert get_computed_stat(state, "enemy", StatType.RANGE, 1) == 1
    assert get_computed_stat(state, "enemy", StatType.RANGE, 3) == 2

    EffectManager.create_effect(
        state=state,
        source_id="hero_cordelia",
        effect_type=EffectType.AREA_STAT_MODIFIER,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=4,
            origin_id="hero_cordelia",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        stat_type=StatType.RANGE,
        stat_value=-50,
        is_active=True,
    )
    assert get_computed_stat(state, "enemy", StatType.RANGE, 3) == -47


@pytest.mark.effect_flow
def test_jinx_reduces_attack_and_its_discard_move_is_exactly_one_space() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero("hero_cordelia", at=(0, 0, 0))
        .blue_hero("enemy", at=(2, 0, -2))
        .with_actor("enemy")
        .build()
    )
    jinx = _put_card(state, "hero_cordelia", "jinx", "played")
    discarded = _put_card(state, "hero_cordelia", "bewitch", "hand")
    EffectManager.create_effect(
        state=state,
        source_id="hero_cordelia",
        source_card_id=jinx.id,
        effect_type=EffectType.AREA_STAT_MODIFIER,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=4,
            origin_id="hero_cordelia",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        stat_type=StatType.ATTACK,
        stat_value=-10,
        is_active=True,
    )
    assert get_computed_stat(state, "enemy", StatType.ATTACK, 3) == -7

    push_steps(
        state,
        [DiscardCardStep(card_id=discarded.id, hero_id="hero_cordelia")],
    )
    run = EffectRun(state=state, hero_id="hero_cordelia")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).confirm()
    run.expect_input(InputRequestType.SELECT_HEX)
    assert Hex(q=2, r=0, s=-2) not in _option_set(run)
    run.choose({"q": 1, "r": 0, "s": -1}).finish()

    assert _position(state, "hero_cordelia") == (1, 0, -1)
    assert state.current_actor_id == "enemy"


@pytest.mark.effect_flow
def test_jinx_does_not_offer_move_when_cordelia_has_no_legal_space() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(2))
        .red_hero("hero_cordelia", at=(0, 0, 0))
        .blue_hero("enemy", at=(2, 0, -2))
        .red_minion("block_0", at=(1, 0, -1))
        .red_minion("block_1", at=(1, -1, 0))
        .red_minion("block_2", at=(0, -1, 1))
        .red_minion("block_3", at=(-1, 0, 1))
        .red_minion("block_4", at=(-1, 1, 0))
        .red_minion("block_5", at=(0, 1, -1))
        .with_actor("enemy")
        .build()
    )
    jinx = _put_card(state, "hero_cordelia", "jinx", "played")
    discarded = _put_card(state, "hero_cordelia", "bewitch", "hand")
    EffectManager.create_effect(
        state=state,
        source_id="hero_cordelia",
        source_card_id=jinx.id,
        effect_type=EffectType.AREA_STAT_MODIFIER,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=4,
            origin_id="hero_cordelia",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        stat_type=StatType.ATTACK,
        stat_value=-10,
        is_active=True,
    )

    push_steps(state, [DiscardCardStep(card_id=discarded.id, hero_id="hero_cordelia")])
    EffectRun(state=state, hero_id="hero_cordelia").finish()

    assert _position(state, "hero_cordelia") == (0, 0, 0)


def _witching_state(*, enemy_at=(2, 0, -2), attack_item: int = 0):
    attack_card = hero_card("Cordelia", "bewitch")
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(6))
        .red_hero("hero_cordelia", at=(0, 0, 0))
        .blue_hero("enemy", at=enemy_at, current_card=attack_card)
        .with_actor("enemy")
        .build()
    )
    cordelia = state.get_hero("hero_cordelia")
    cordelia.level = 8
    cordelia.ultimate_card = hero_card("Cordelia", "witching_hour")
    state.get_hero("enemy").items[StatType.ATTACK] = attack_item
    EffectManager.create_effect(
        state=state,
        source_id="hero_cordelia",
        effect_type=EffectType.AREA_STAT_MODIFIER,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=4,
            origin_id="hero_cordelia",
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        stat_type=StatType.ATTACK,
        stat_value=-10,
        is_active=True,
    )
    return state


@pytest.mark.effect_contract
def test_witching_hour_hides_attack_choice_when_current_computed_attack_is_negative() -> None:
    state = _witching_state()

    run = run_card(state, "enemy")
    run.expect_input(InputRequestType.CHOOSE_ACTION)

    assert "ATTACK" not in _option_set(run)
    assert "MOVEMENT" in _option_set(run)


@pytest.mark.effect_contract
def test_witching_hour_counts_already_active_items_and_only_applies_in_radius() -> None:
    rescued_by_item = _witching_state(attack_item=8)
    item_run = run_card(rescued_by_item, "enemy")
    item_run.expect_input(InputRequestType.CHOOSE_ACTION)
    assert "ATTACK" in _option_set(item_run)  # 3 base + 8 item - 10 = 1

    outside_radius = _witching_state(enemy_at=(5, 0, -5))
    range_run = run_card(outside_radius, "enemy")
    range_run.expect_input(InputRequestType.CHOOSE_ACTION)
    assert "ATTACK" in _option_set(range_run)

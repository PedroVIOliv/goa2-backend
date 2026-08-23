from __future__ import annotations

import pytest

import goa2.scripts.sabina_effects  # noqa: F401
from goa2.domain.input import InputRequestType

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _state(card_id: str, *, target_at: tuple[int, int, int] = (1, 0, -1)):
    return (
        EffectScenarioBuilder()
        .with_hexes(
            [
                (0, 0, 0),
                (1, 0, -1),
                (2, 0, -2),
                (-1, 0, 1),
                (0, 1, -1),
            ]
        )
        .red_hero(
            "hero_sabina",
            at=(0, 0, 0),
            name="Sabina",
            current_card=hero_card("Sabina", card_id),
        )
        .blue_minion("target_minion", at=target_at)
        .blue_minion("bonus_minion_1", at=(-1, 0, 1))
        .blue_minion("bonus_minion_2", at=(0, 1, -1))
        .with_actor("hero_sabina")
        .build()
    )


@pytest.mark.effect_flow
@pytest.mark.parametrize(
    ("card_id", "bonus_targets"),
    [
        ("shootout", ["bonus_minion_1"]),
        ("bullet_hell", ["bonus_minion_1", "bonus_minion_2"]),
    ],
)
def test_sabina_removal_rider_uses_adjacency_before_target_defeat(
    card_id: str, bonus_targets: list[str]
) -> None:
    state = _state(card_id)
    run = run_card(state, "hero_sabina")

    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("target_minion")

    # The attack defeats and removes the adjacent target. The rider must still
    # fire because the card asks whether the target was adjacent when targeted.
    run.expect_input(InputRequestType.SELECT_UNIT)
    gold_after_attack = state.get_hero("hero_sabina").gold

    for index, bonus_target in enumerate(bonus_targets):
        run.choose(bonus_target)
        if index + 1 < len(bonus_targets):
            run.expect_input(InputRequestType.SELECT_UNIT)
    run.finish()

    assert "target_minion" not in state.entity_locations
    assert all(target not in state.entity_locations for target in bonus_targets)
    assert state.get_hero("hero_sabina").gold == gold_after_attack


@pytest.mark.effect_flow
def test_sabina_removal_rider_skips_nonadjacent_attack_target() -> None:
    state = _state("shootout", target_at=(2, 0, -2))
    run = run_card(state, "hero_sabina")

    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("target_minion")
    run.finish()

    assert "target_minion" not in state.entity_locations
    assert "bonus_minion_1" in state.entity_locations
    assert "bonus_minion_2" in state.entity_locations

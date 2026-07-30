import pytest

import goa2.data.heroes.silverarrow
import goa2.scripts.silverarrow_effects  # noqa: F401 - register effects
from goa2.domain.input import InputRequestType

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _option_set(run) -> set:
    assert run.latest_request is not None
    options = set()
    for option in run.latest_request.options:
        if getattr(option, "metadata", None) and "raw" in option.metadata:
            options.add(option.metadata.get("raw"))
        else:
            options.add(option.id)
    return options


@pytest.mark.effect_flow
def test_natures_blessing_gift_targets_any_hero_but_self():
    """Nature's Blessing gift is offered to any hero in radius.

    Card text: "A hero in radius may retrieve a discarded card." "A hero" is
    unqualified, so enemy heroes are legal recipients; only Silverarrow
    herself is excluded, per the "a hero excludes the actor" convention.
    """
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(4)])
        .red_hero(
            "hero_silverarrow",
            at=(0, 0, 0),
            current_card=hero_card("Silverarrow", "natures_blessing"),
        )
        .red_hero("hero_ally", at=(1, 0, -1))
        .blue_hero("hero_enemy", at=(2, 0, -2))
        .with_actor("hero_silverarrow")
        .build()
    )

    run = run_card(state, "hero_silverarrow")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)

    options = _option_set(run)
    assert "hero_ally" in options
    assert "hero_enemy" in options
    assert "hero_silverarrow" not in options


@pytest.mark.effect_flow
@pytest.mark.parametrize("card_id", ["lead_astray", "divert_attention"])
def test_drag_family_enemy_move_is_mandatory(card_id: str) -> None:
    """Lead Astray and Divert Attention open with the same imperative clause as
    Disorient — "Move an enemy unit adjacent to you up to N spaces" — so the
    enemy pick and its destination are both non-skippable. Only the trailing
    "move up to that number of spaces" self-move stays optional.
    """
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(5)])
        .red_hero(
            "hero_silverarrow",
            at=(0, 0, 0),
            current_card=hero_card("Silverarrow", card_id),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_silverarrow")
        .build()
    )

    run = run_card(state, "hero_silverarrow")
    run.expect_input(InputRequestType.CHOOSE_ACTION)

    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    assert run.latest_request is not None
    assert run.latest_request.can_skip is False

    run.choose("blue_minion").expect_input(InputRequestType.SELECT_HEX)
    assert run.latest_request is not None
    assert run.latest_request.can_skip is False


@pytest.mark.effect_flow
def test_disorient_enemy_move_is_mandatory():
    """Disorient's first clause is imperative: "Move an enemy unit adjacent to
    you 1 space" — both the enemy selection and its destination must be
    mandatory (no skip). Only the trailing "you may move 1 space" is optional.
    """
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(4)])
        .red_hero(
            "hero_silverarrow",
            at=(0, 0, 0),
            current_card=hero_card("Silverarrow", "disorient"),
        )
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_silverarrow")
        .build()
    )

    run = run_card(state, "hero_silverarrow")
    run.expect_input(InputRequestType.CHOOSE_ACTION)

    # Select the enemy to move — imperative, so no skip allowed.
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    assert run.latest_request is not None
    assert run.latest_request.can_skip is False

    # Destination for that enemy — also part of the mandatory move.
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_HEX)
    assert run.latest_request is not None
    assert run.latest_request.can_skip is False

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
def test_natures_blessing_gift_targets_friendly_only():
    """Nature's Blessing gift must target a friendly hero, not an enemy.

    Card text: "A hero in radius may retrieve a discarded card." The gift is a
    benefit (retrieve + coins), so it should not be giftable to an enemy hero.
    Self is excluded too (friendly-only ruling).
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
    assert "hero_enemy" not in options
    assert "hero_silverarrow" not in options

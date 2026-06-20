import pytest

import goa2.data.heroes.tigerclaw
import goa2.scripts.tigerclaw_effects  # noqa: F401 - register effects

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
@pytest.mark.parametrize("card_id", ["poisoned_dagger", "poisoned_dart"])
def test_poison_can_target_any_hero_except_self(card_id):
    """Poison "a hero in range" — unlike defeat/attack effects, a friendly hero
    (ally) is a legal target (counter-intuitive but per the rules). Tigerclaw
    himself is excluded (default self-exclusion)."""
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(4)])
        .red_hero(
            "hero_tigerclaw",
            at=(0, 0, 0),
            current_card=hero_card("Tigerclaw", card_id),
        )
        .red_hero("hero_ally", at=(1, 0, -1))
        .blue_hero("hero_enemy", at=(2, 0, -2))
        .with_actor("hero_tigerclaw")
        .build()
    )

    run = run_card(state, "hero_tigerclaw")
    run.expect_input("CHOOSE_ACTION").choose("SKILL")
    run.expect_input("SELECT_UNIT")

    options = _option_set(run)
    assert "hero_ally" in options  # friendly hero IS a legal poison target
    assert "hero_enemy" in options  # enemy hero still a legal target
    assert "hero_tigerclaw" not in options  # self excluded by default

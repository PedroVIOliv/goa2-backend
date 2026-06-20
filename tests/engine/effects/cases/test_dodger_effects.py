import pytest

import goa2.scripts.dodger_effects  # noqa: F401
from goa2.domain.input import InputRequestType
from goa2.domain.models.enums import StatType

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _setup_dodger(hexes, *, with_ultimate: bool = True):
    """Level-8 Dodger about to play Darkest Ritual.

    Level 8 satisfies the card's "If you have your Ultimate" clause. When
    ``with_ultimate`` is set, the real Tide of Darkness ultimate is assigned so
    this is a faithful level-8 Dodger (and its passive override is in effect for
    spawn-point counting).
    """
    state = (
        EffectScenarioBuilder()
        .with_hexes(hexes)
        .red_hero(
            "hero_dodger",
            at=(0, 0, 0),
            current_card=hero_card("Dodger", "darkest_ritual"),
        )
        .with_actor("hero_dodger")
        .build()
    )
    dodger = state.get_hero("hero_dodger")
    dodger.level = 8
    if with_ultimate:
        dodger.ultimate_card = hero_card("Dodger", "tide_of_darkness")
    return state, dodger


@pytest.mark.effect_flow
def test_darkest_ritual_grants_ultimate_item_even_without_coins() -> None:
    """Darkest Ritual's two clauses are independent.

    Card text: "If there are 2 or more empty spawn points in radius ..., gain 2
    coins. If you have your Ultimate, gain an Attack item."

    With fewer than 2 empty spawn points in radius (here a 2-hex board → only 1
    free hex), the coin clause is skipped, but a level-8 Dodger must STILL gain
    the Attack item. This currently fails because the GainItemStep reads
    context["self"], which is only set inside the coin branch.
    """
    # 2-hex board: hero on one hex, exactly one free hex → < 2 empty spawn points
    state, dodger = _setup_dodger([(0, 0, 0), (1, 0, -1)])
    gold_before = dodger.gold

    run = run_card(state, "hero_dodger")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").finish()

    # Coin clause correctly skipped (< 2 empty spawn points)...
    assert dodger.gold == gold_before
    # ...but the independent Ultimate item clause must still fire.
    assert dodger.items.get(StatType.ATTACK, 0) == 1


@pytest.mark.effect_flow
def test_darkest_ritual_grants_item_when_coins_also_gained() -> None:
    """Control: with 2+ empty spawn points, both clauses fire.

    The item only comes through here because the coin branch sets
    context["self"] first — exactly the coupling the bug exposes.
    """
    # Roomy board: many free hexes in radius → 2+ empty spawn points (override)
    state, dodger = _setup_dodger([(q, 0, -q) for q in range(5)])
    gold_before = dodger.gold

    run = run_card(state, "hero_dodger")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").finish()

    assert dodger.gold == gold_before + 2
    assert dodger.items.get(StatType.ATTACK, 0) == 1

import pytest

import goa2.scripts.wasp_effects  # noqa: F401
from goa2.domain.input import InputRequestType
from goa2.engine.effect_manager import EffectManager

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _resolve_magnetic_dagger(state):
    """Drive Magnetic Dagger to completion and activate its prevention effect.

    The attack target is a minion so no reaction window is prompted. The
    PLACEMENT_PREVENTION effect is created dormant during resolution, so it is
    activated via the card lifecycle (as the real turn flow does).
    """
    run = run_card(state, "hero_wasp")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_adj").finish()

    wasp = state.get_hero("hero_wasp")
    card_id = wasp.current_turn_card.id
    wasp.resolve_current_card()
    EffectManager.activate_effects_by_card(state, card_id)
    return run


@pytest.mark.effect_flow
def test_magnetic_dagger_allows_allies_to_swap_enemy_units():
    """Magnetic Dagger blocks "themselves or enemy heroes" — not Wasp's allies.

    Confirms a friendly hero can still swap with an enemy hero AND an enemy
    minion in radius, while an enemy actor is blocked from the same swaps.
    """
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(5)])
        .red_hero(
            "hero_wasp",
            at=(0, 0, 0),
            current_card=hero_card("Wasp", "magnetic_dagger"),
        )
        .blue_minion("blue_adj", at=(1, 0, -1))  # adjacent attack target
        .blue_hero("hero_enemy", at=(2, 0, -2))  # enemy hero in radius
        .blue_minion("enemy_minion", at=(3, 0, -3))  # enemy minion in radius
        .red_hero("hero_ally", at=(4, 0, -4))  # Wasp's ally (friendly actor)
        .with_actor("hero_wasp")
        .build()
    )

    _resolve_magnetic_dagger(state)
    v = state.validator

    # A Wasp ally may still swap with protected enemy units in radius.
    assert v.can_be_swapped(state, "hero_enemy", "hero_ally").allowed
    assert v.can_be_swapped(state, "enemy_minion", "hero_ally").allowed

    # An enemy actor is blocked from swapping the same units.
    assert not v.can_be_swapped(state, "hero_enemy", "enemy_minion").allowed
    assert not v.can_be_swapped(state, "enemy_minion", "hero_enemy").allowed

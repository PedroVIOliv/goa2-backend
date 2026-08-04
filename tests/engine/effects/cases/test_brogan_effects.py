"""Behavioral contracts for Brogan's card effects."""

from __future__ import annotations

import pytest

import goa2.scripts.brogan_effects  # noqa: F401 - register Brogan effects
from goa2.domain.input import InputRequestType
from goa2.domain.models.effect import AffectsFilter, EffectType
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import PerformPrimaryActionStep

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _brogan_playing_bulwark():
    return (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_brogan",
            at=(0, 0, 0),
            current_card=hero_card("Brogan", "bulwark"),
        )
        .with_actor("hero_brogan")
        .build()
    )


@pytest.mark.effect_contract
def test_bulwark_protects_both_the_hero_and_friendly_units() -> None:
    """ "You and friendly units in radius" is two payloads of one active effect."""
    state = _brogan_playing_bulwark()

    run_card(state, "hero_brogan").expect_input(InputRequestType.CHOOSE_ACTION).choose(
        "SKILL"
    ).finish()

    bound = [e for e in state.active_effects if e.source_card_id == "bulwark"]
    assert all(e.effect_type == EffectType.PLACEMENT_PREVENTION for e in bound)
    assert {e.scope.affects for e in bound} == {
        AffectsFilter.SELF,
        AffectsFilter.FRIENDLY_UNITS,
    }


@pytest.mark.effect_contract
def test_repeating_bulwark_does_not_duplicate_its_effect() -> None:
    """Only one instance of an active effect per card can be active."""
    state = _brogan_playing_bulwark()

    run_card(state, "hero_brogan").expect_input(InputRequestType.CHOOSE_ACTION).choose(
        "SKILL"
    ).finish()
    before = [e.id for e in state.active_effects]

    state.execution_context["selected_card"] = "bulwark"
    push_steps(state, [PerformPrimaryActionStep(hero_id="hero_brogan")])
    process_stack(state)

    assert [e.id for e in state.active_effects] == before

"""Behavioral contracts for Brogan's card effects."""

from __future__ import annotations

import pytest

import goa2.scripts.brogan_effects  # noqa: F401 - register Brogan effects
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import Token, TokenType
from goa2.domain.models.effect import AffectsFilter, EffectType
from goa2.domain.types import BoardEntityID, HeroID
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import PerformPrimaryActionStep

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


@pytest.mark.effect_flow
def test_mad_dash_may_cross_passable_mine() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero("hero_brogan", at=(0, 0, 0), current_card=hero_card("Brogan", "mad_dash"))
        .blue_minion("target", at=(3, 0, -3))
        .blue_hero("mine_owner", at=(5, 0, -5))
        .with_actor("hero_brogan")
        .build()
    )
    mine = Token(
        id=BoardEntityID("mine_1"),
        name="Mine",
        token_type=TokenType.MINE_DUD,
        owner_id=HeroID("mine_owner"),
        is_passable=True,
    )
    state.token_pool[TokenType.MINE_DUD] = [mine]
    state.register_entity(mine, "token")
    state.place_entity(mine.id, Hex(q=1, r=0, s=-1))

    run = run_card(state, "hero_brogan")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_HEX)

    assert run.latest_request is not None
    destinations = {option.metadata["raw"] for option in run.latest_request.options}
    destination = Hex(q=2, r=0, s=-2)
    assert destination in destinations

    run.choose(destination).expect_input(InputRequestType.SELECT_UNIT)

    assert state.get_position("hero_brogan") == destination
    assert state.get_position("mine_1") is None


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

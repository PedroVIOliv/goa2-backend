"""Regressions for skipped attacks and mutually exclusive attack orders."""

import pytest

import goa2.scripts.bain_effects
import goa2.scripts.dodger_effects  # noqa: F401
from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.models import CardState, Minion, MinionType, TeamColor
from goa2.domain.models.marker import MarkerType

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _scenario(hero, card, *, adjacent=True):
    builder = (
        EffectScenarioBuilder()
        .with_hexes((q, r, -q - r) for q in range(-4, 5) for r in range(-4, 5) if abs(q + r) <= 4)
        .red_hero("actor", at=(0, 0, 0), current_card=hero_card(hero, card))
        .red_hero("ally", at=(3, -1, -2))
        .blue_hero("far", at=(3, 0, -3))
        .with_actor("actor")
    )
    if adjacent:
        builder.blue_hero("near", at=(1, 0, -1))
    state = builder.build()
    for uid in (["near", "far"] if adjacent else ["far"]):
        defender = state.get_hero(uid)
        defender.hand = [hero_card("Swift", cid) for cid in ("super_shotgun", "hunting_season")]
        for card in defender.hand:
            card.state = CardState.HAND
    return state


def _targets(run):
    return [e.target_id for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]


@pytest.mark.effect_flow
@pytest.mark.parametrize("card", ["trusted_sidekick", "pile_on"])
@pytest.mark.parametrize("skip", [False, True])
def test_hanu_optional_second_attack_does_not_reuse_defender(card, skip):
    state = _scenario("Hanu", card)
    # Pile On's second bullet targets a minion, whereas Sidekick targets a hero.
    if card == "pile_on":
        if skip:
            minion = Minion(id="minion", name="Minion", team=TeamColor.BLUE, type=MinionType.MELEE)
            state.teams[TeamColor.BLUE].minions.append(minion)
            state.place_entity("minion", Hex(q=2, r=-1, s=-1))
    elif not skip:
        # No friendly hero adjacent to the ranged target.
        state.move_unit("ally", Hex(q=-3, r=0, s=3))
    run = run_card(state, "actor")
    run.expect_input("CHOOSE_ACTION").choose("ATTACK").expect_input("SELECT_NUMBER")
    run.choose(1).expect_input("SELECT_UNIT").choose("near").expect_input("SELECT_CARD_OR_PASS")
    run.choose("super_shotgun")
    if skip:
        run.expect_input("SELECT_UNIT").skip()
    run.finish()
    assert _targets(run) == ["near"]
    assert [c.id for c in state.get_hero("near").hand] == ["hunting_season"]
    assert state.current_actor_id == "actor"


@pytest.mark.effect_flow
def test_sidekick_ranged_first_without_adjacent_target():
    state = _scenario("Hanu", "trusted_sidekick", adjacent=False)
    run = run_card(state, "actor")
    run.expect_input("CHOOSE_ACTION").choose("ATTACK").expect_input("SELECT_NUMBER")
    run.choose(2).expect_input("SELECT_UNIT").choose("far").expect_input("SELECT_CARD_OR_PASS")
    run.choose("super_shotgun").finish()
    assert _targets(run) == ["far"]
    assert [c.id for c in state.get_hero("far").hand] == ["hunting_season"]


@pytest.mark.effect_flow
@pytest.mark.parametrize(
    "hero,card", [("Bain", "hunter_seeker"), ("Dodger", "middlefinger_of_death")]
)
@pytest.mark.parametrize("order", [1, 2])
@pytest.mark.parametrize("skip_second", [False, True])
def test_two_attack_orders_never_execute_the_other_branch(hero, card, order, skip_second):
    state = _scenario(hero, card)
    if hero == "Bain":
        state.get_marker(MarkerType.BOUNTY).place(target_id="far", value=0, source_id="actor")
    else:
        discarded = hero_card("Swift", "snipe")
        discarded.state = CardState.DISCARD
        state.get_hero("far").discard_pile = [discarded]
    first, second = ("far", "near") if hero == "Bain" else ("near", "far")
    if order == 2:
        first, second = second, first
    run = run_card(state, "actor")
    run.expect_input("CHOOSE_ACTION").choose("ATTACK").expect_input("SELECT_NUMBER")
    run.choose(order).expect_input("SELECT_UNIT").choose(first).expect_input("SELECT_CARD_OR_PASS")
    run.choose("super_shotgun").expect_input("SELECT_UNIT")
    if skip_second:
        run.skip().finish()
    else:
        run.choose(second).expect_input("SELECT_CARD_OR_PASS").choose("super_shotgun").finish()
    assert _targets(run) == ([first] if skip_second else [first, second])
    assert [c.id for c in state.get_hero(first).hand] == ["hunting_season"]
    assert len(state.get_hero(second).hand) == (2 if skip_second else 1)

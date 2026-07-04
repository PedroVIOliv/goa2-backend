"""Effect flow tests for Ignatia — the coin-branch chaos hero.

Every branch card reads the Tie Breaker coin face: BLUE face -> the
:tiebreaker_blue: text, ORANGE face -> the :tiebreaker_orange: text. The coin
is the same bit as ``state.tie_breaker_team`` (BLUE team -> blue face, RED team
-> orange face); see GameState.coin_face.
"""

import pytest

from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.events import GameEventType
from goa2.domain.input import InputRequestType
from goa2.domain.models import TeamColor

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _enable_ultimate(state, hero_id: str = "hero_ignatia") -> None:
    """Unlock Chaos Incarnate: level 8 + the ultimate card in hand-of-record."""
    ig = state.get_hero(hero_id)
    ig.level = 8
    ig.ultimate_card = HeroRegistry.get("Ignatia").ultimate_card


def _enable_equilibrium(state, hero_id: str = "hero_ignatia") -> None:
    """Activate a THIS_ROUND Equilibrium effect on Ignatia (as her Silver would)."""
    from goa2.domain.models.effect import (
        ActiveEffect,
        DurationType,
        EffectScope,
        EffectType,
        Shape,
    )

    ig = state.get_hero(hero_id)
    state.add_effect(
        ActiveEffect(
            id="equilibrium_test",
            source_id=str(ig.id),
            effect_type=EffectType.EQUILIBRIUM,
            scope=EffectScope(shape=Shape.POINT, origin_id=str(ig.id)),
            duration=DurationType.THIS_ROUND,
            created_at_turn=state.turn,
            created_at_round=state.round,
        )
    )


def _hex_disk(radius: int) -> list[tuple[int, int, int]]:
    return [
        (q, r, -q - r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if abs(q + r) <= radius
    ]


def _option_set(run) -> set:
    """Set of selectable values from the current request (raw metadata or option id)."""
    assert run.latest_request is not None
    options = set()
    for option in run.latest_request.options:
        if hasattr(option, "metadata") and option.metadata and "raw" in option.metadata:
            options.add(option.metadata.get("raw"))
        elif hasattr(option, "id"):
            options.add(option.id)
        else:
            options.add(option)
    return options


def _set_coin(state, face: str) -> None:
    state.tie_breaker_team = TeamColor.BLUE if face == "BLUE" else TeamColor.RED


# Straight-line axis from origin: (2,0,-2) is on a straight line; (2,-1,-1) is not.
ON_AXIS = (2, 0, -2)
OFF_AXIS = (2, -1, -1)


# =============================================================================
# F1 — Fire attacks: playing_with_fire / erratic_fireblast / loosely_aimed_firebolts
#   blue  : target a unit in range NOT in a straight line
#   orange: target a unit in range in a straight line
# =============================================================================


def _fire_state(card_id: str):
    return (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero("hero_ignatia", at=(0, 0, 0), current_card=hero_card("Ignatia", card_id))
        .blue_minion("on_axis", at=ON_AXIS)
        .blue_minion("off_axis", at=OFF_AXIS)
        .with_actor("hero_ignatia")
        .build()
    )


@pytest.mark.effect_flow
def test_playing_with_fire_blue_targets_only_off_straight_line() -> None:
    state = _fire_state("playing_with_fire")
    _set_coin(state, "BLUE")

    run = run_card(state, "hero_ignatia")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)

    opts = _option_set(run)
    assert "off_axis" in opts
    assert "on_axis" not in opts


@pytest.mark.effect_flow
def test_playing_with_fire_orange_targets_only_straight_line() -> None:
    state = _fire_state("playing_with_fire")
    _set_coin(state, "ORANGE")

    run = run_card(state, "hero_ignatia")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)

    opts = _option_set(run)
    assert "on_axis" in opts
    assert "off_axis" not in opts


@pytest.mark.effect_flow
def test_playing_with_fire_blue_resolves_attack_on_off_axis_target() -> None:
    state = _fire_state("playing_with_fire")
    _set_coin(state, "BLUE")

    run = run_card(state, "hero_ignatia")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    # The minion has no defense card, so combat auto-resolves on selection.
    run.choose("off_axis").finish()

    assert any(e.event_type == GameEventType.COMBAT_RESOLVED for e in run.events)


def _fire_hero_state(card_id: str):
    """Fire scenario where targets are heroes (so the first target survives the
    attack and the ultimate re-perform's exclusion is observable)."""
    return (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero("hero_ignatia", at=(0, 0, 0), current_card=hero_card("Ignatia", card_id))
        .blue_hero("h_on", at=ON_AXIS)
        .blue_hero("h_off", at=OFF_AXIS)
        .with_actor("hero_ignatia")
        .build()
    )


@pytest.mark.effect_flow
def test_playing_with_fire_ultimate_flips_coin_and_reperforms_opposite_branch() -> None:
    state = _fire_hero_state("playing_with_fire")
    _set_coin(state, "BLUE")
    _enable_ultimate(state)

    run = run_card(state, "hero_ignatia")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    # Blue: first attack targets off the straight line.
    run.choose("h_off").expect_input("SELECT_CARD_OR_PASS")
    run.choose("PASS").expect_input(InputRequestType.SELECT_OPTION)
    # Chaos Incarnate: flip the coin and perform again.
    run.choose("YES").expect_input(InputRequestType.SELECT_UNIT)

    # The coin flipped BLUE -> orange, so the re-perform runs the orange branch.
    assert state.coin_face == "ORANGE"
    opts = _option_set(run)
    assert "h_on" in opts  # orange -> in a straight line
    assert "h_off" not in opts  # opposite branch (and first target) excluded


@pytest.mark.effect_flow
def test_playing_with_fire_ultimate_can_be_declined() -> None:
    state = _fire_hero_state("playing_with_fire")
    _set_coin(state, "BLUE")
    _enable_ultimate(state)

    run = run_card(state, "hero_ignatia")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("h_off").expect_input("SELECT_CARD_OR_PASS")
    run.choose("PASS").expect_input(InputRequestType.SELECT_OPTION)
    # Decline: no flip, no re-perform.
    run.choose("NO").finish()

    assert state.coin_face == "BLUE"  # coin unchanged


@pytest.mark.effect_flow
def test_equilibrium_lets_her_pick_blue_against_an_orange_coin() -> None:
    state = _fire_state("playing_with_fire")
    _set_coin(state, "ORANGE")  # coin shows orange (in-line)...
    _enable_equilibrium(state)

    run = run_card(state, "hero_ignatia")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    # ...but Equilibrium prompts her to choose the side instead of reading the coin.
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(1).expect_input(InputRequestType.SELECT_UNIT)  # 1 = Blue

    opts = _option_set(run)
    assert "off_axis" in opts  # blue -> not in a straight line
    assert "on_axis" not in opts


@pytest.mark.effect_flow
def test_ultimate_with_equilibrium_makes_the_reperform_a_free_choice() -> None:
    state = _fire_hero_state("playing_with_fire")
    _set_coin(state, "BLUE")
    _enable_ultimate(state)
    _enable_equilibrium(state)

    run = run_card(state, "hero_ignatia")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_NUMBER)  # first: choose side
    run.choose(1).expect_input(InputRequestType.SELECT_UNIT)  # blue
    run.choose("h_off").expect_input("SELECT_CARD_OR_PASS")
    run.choose("PASS").expect_input(InputRequestType.SELECT_OPTION)  # ultimate prompt
    # YES flips the coin, but the re-perform is another free choice (SELECT_NUMBER),
    # not a forced flipped-face attack.
    run.choose("YES").expect_input(InputRequestType.SELECT_NUMBER)

    assert state.coin_face == "ORANGE"  # the flip still happened (matters for future ties)


@pytest.mark.effect_flow
def test_erratic_fireblast_blue_excludes_straight_line_target() -> None:
    # Same branch logic as playing_with_fire, Tier II stats (range 3).
    state = _fire_state("erratic_fireblast")
    _set_coin(state, "BLUE")

    run = run_card(state, "hero_ignatia")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)

    opts = _option_set(run)
    assert "off_axis" in opts
    assert "on_axis" not in opts


# ---- loosely_aimed_firebolts (Tier III, range 3) --------------------------
#   orange adds: "May repeat once on a different hero." (repeat fires even if
#   the first target was not a hero; the repeat target must be a hero, in a
#   straight line, and different from the first.)


def _loosely_state():
    return (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero(
            "hero_ignatia",
            at=(0, 0, 0),
            current_card=hero_card("Ignatia", "loosely_aimed_firebolts"),
        )
        .blue_minion("m_on", at=(2, 0, -2))  # on-axis minion (first target)
        .blue_minion("m_on2", at=(0, -2, 2))  # on-axis minion (not a valid repeat)
        .blue_hero("h_on", at=(-2, 0, 2))  # on-axis hero (valid repeat)
        .blue_hero("h_off", at=(2, -1, -1))  # off-axis hero (not in line)
        .with_actor("hero_ignatia")
        .build()
    )


@pytest.mark.effect_flow
def test_loosely_orange_repeat_targets_only_a_different_hero_in_line() -> None:
    state = _loosely_state()
    _set_coin(state, "ORANGE")

    run = run_card(state, "hero_ignatia")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    # First target is a (non-hero) minion in a straight line — repeat still fires.
    run.choose("m_on").expect_input(InputRequestType.SELECT_OPTION)
    run.choose("YES").expect_input(InputRequestType.SELECT_UNIT)

    opts = _option_set(run)
    assert "h_on" in opts  # a different hero, in a straight line
    assert "h_off" not in opts  # off the straight line
    assert "m_on" not in opts  # the first target is excluded
    assert "m_on2" not in opts  # repeat must be a hero, not a minion


@pytest.mark.effect_flow
def test_loosely_blue_attacks_off_axis_without_repeat() -> None:
    state = _loosely_state()
    _set_coin(state, "BLUE")

    run = run_card(state, "hero_ignatia")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    opts = _option_set(run)
    assert "h_off" in opts  # off the straight line -> valid under blue
    assert "m_on" not in opts  # on the straight line -> excluded under blue
    # Blue has no repeat: after the defender passes, the action ends (no repeat prompt).
    run.choose("h_off").expect_input("SELECT_CARD_OR_PASS")
    run.choose("PASS").finish()

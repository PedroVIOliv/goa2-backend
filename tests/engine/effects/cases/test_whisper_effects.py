"""Whisper effect tests — Swift Justice (gold).

Swift Justice branch 1: "Target a hero in range with an empty discard.
After the attack: If able, that hero performs a movement action on the card
they defended with, moving full distance in a straight line."

The defender *performs a movement action*, so movement-prevention effects
(e.g. Xargatha's "Enemy heroes in radius cannot perform movement actions")
make them unable — the "if able" clause.
"""

import pytest

from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import ActionType
from goa2.domain.models.effect import AffectsFilter, DurationType, EffectScope, EffectType, Shape

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _apply_movement_prevention(state, origin_id: str = "hero_whisper") -> None:
    """Live effect: enemy heroes in radius cannot perform movement actions."""
    from goa2.engine.steps.effects import CreateEffectStep

    CreateEffectStep(
        effect_type=EffectType.TARGET_PREVENTION,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=6,
            origin_id=origin_id,
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=DurationType.THIS_TURN,
        restrictions=[ActionType.MOVEMENT],
    ).resolve(state, {})


def _swift_justice_state():
    """Whisper with Swift Justice; enemy hero at range 2 with an empty discard
    and a defense card (Terrify: DEFENSE 7 / MOVEMENT 3) in hand."""
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(6)])
        .red_hero(
            "hero_whisper",
            at=(0, 0, 0),
            current_card=hero_card("Whisper", "swift_justice"),
        )
        .blue_hero("hero_defender", at=(2, 0, -2))
        .with_actor("hero_whisper")
        .build()
    )
    defender = state.get_hero("hero_defender")
    assert defender is not None
    defender.hand.append(hero_card("Garrus", "terrify"))
    return state


def _attack_and_defend(run) -> None:
    """Drive Swift Justice branch 1 through the attack + defense."""
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(1).expect_input(InputRequestType.SELECT_UNIT)
    run.choose("hero_defender").expect_input(InputRequestType.SELECT_CARD_OR_PASS)
    run.choose("terrify")


@pytest.mark.effect_flow
def test_swift_justice_forces_defender_movement_after_defense() -> None:
    state = _swift_justice_state()

    run = run_card(state, "hero_whisper")
    _attack_and_defend(run)

    # The defender is forced to move full distance (3) in a straight line.
    run.expect_input(InputRequestType.SELECT_HEX)
    assert state.execution_context["current_action_type"] == ActionType.MOVEMENT
    assert state.execution_context["current_card_id"] == "terrify"
    assert state.get_performing_card("hero_defender").id == "terrify"
    run.choose(Hex(q=5, r=0, s=-5)).finish()

    assert state.entity_locations["hero_defender"] == Hex(q=5, r=0, s=-5)
    assert state.execution_context["current_action_type"] == ActionType.ATTACK
    assert state.execution_context["current_card_id"] == "swift_justice"
    assert state.get_performing_card("hero_whisper").id == "swift_justice"
    assert "action_context_stack" not in state.execution_context


@pytest.mark.effect_flow
def test_swift_justice_movement_not_forced_when_defender_cannot_move() -> None:
    """A movement-prevention effect on the defender means they are not able to
    perform the movement action — no forced move happens."""
    state = _swift_justice_state()
    _apply_movement_prevention(state)

    run = run_card(state, "hero_whisper")
    _attack_and_defend(run)
    run.finish()

    assert state.entity_locations["hero_defender"] == Hex(q=2, r=0, s=-2)


@pytest.mark.effect_flow
def test_swift_justice_forced_movement_cannot_be_skipped() -> None:
    """The defender performs the movement — they cannot decline it."""
    state = _swift_justice_state()

    run = run_card(state, "hero_whisper")
    _attack_and_defend(run)

    run.expect_input(InputRequestType.SELECT_HEX)
    assert run.latest_request is not None
    assert run.latest_request.can_skip is False

    # A client that submits SKIP anyway is re-prompted, not obeyed.
    run.skip().expect_input(InputRequestType.SELECT_HEX)
    run.choose(Hex(q=5, r=0, s=-5)).finish()

    assert state.entity_locations["hero_defender"] == Hex(q=5, r=0, s=-5)


@pytest.mark.effect_flow
def test_swift_justice_forced_movement_fizzles_without_a_legal_line() -> None:
    """No legal full-distance straight line means "not able" — the forced move
    is a no-op and must not abort Whisper's action."""
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(5)])
        .red_hero(
            "hero_whisper",
            at=(0, 0, 0),
            current_card=hero_card("Whisper", "swift_justice"),
        )
        .blue_hero("hero_defender", at=(2, 0, -2))
        .with_actor("hero_whisper")
        .build()
    )
    defender = state.get_hero("hero_defender")
    assert defender is not None
    defender.hand.append(hero_card("Garrus", "terrify"))

    run = run_card(state, "hero_whisper")
    _attack_and_defend(run)
    run.finish()

    assert state.entity_locations["hero_defender"] == Hex(q=2, r=0, s=-2)
    assert state.current_actor_id == "hero_whisper"
    assert state.execution_context["current_action_type"] == ActionType.ATTACK
    assert state.execution_context["current_card_id"] == "swift_justice"
    assert "action_context_stack" not in state.execution_context


@pytest.mark.effect_flow
def test_swift_justice_ultimate_survives_an_impossible_forced_move() -> None:
    """The forced move is the defender's own nested movement action: failing it
    cancels that action only, so Grim Reaper's second attack still happens."""
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(5)] + [(0, 1, -1)])
        .red_hero(
            "hero_whisper",
            at=(0, 0, 0),
            current_card=hero_card("Whisper", "swift_justice"),
        )
        .blue_hero("hero_defender", at=(2, 0, -2))
        .blue_minion("minion_1", at=(0, 1, -1))
        .with_actor("hero_whisper")
        .build()
    )
    defender = state.get_hero("hero_defender")
    assert defender is not None
    defender.hand.append(hero_card("Garrus", "terrify"))
    whisper = state.get_hero("hero_whisper")
    assert whisper is not None
    whisper.level = 8
    whisper.ultimate_card = hero_card("Whisper", "grim_reaper")

    run = run_card(state, "hero_whisper")
    _attack_and_defend(run)

    # No legal full-distance straight line for the defender — the forced move
    # fails, but the unchosen adjacent-attack branch is still offered.
    run.expect_input(InputRequestType.SELECT_UNIT)
    assert run.latest_request is not None
    assert [option.id for option in run.latest_request.options] == ["minion_1"]

    assert state.entity_locations["hero_defender"] == Hex(q=2, r=0, s=-2)
    assert state.current_actor_id == "hero_whisper"
    assert state.execution_context["current_card_id"] == "swift_justice"
    assert "action_context_stack" not in state.execution_context

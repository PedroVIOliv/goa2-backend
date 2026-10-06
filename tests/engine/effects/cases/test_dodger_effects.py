import pytest

import goa2.scripts.dodger_effects  # noqa: F401
from goa2.domain.input import InputRequestType
from goa2.domain.models import TeamColor
from goa2.domain.models.effect import AffectsFilter, DurationType, EffectScope, EffectType, Shape
from goa2.domain.models.enums import StatType
from goa2.domain.rules_version import EMPTY_MEANS_NOT_OBSTACLE
from goa2.domain.types import BoardEntityID
from goa2.engine.effect_manager import EffectManager
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import AttackSequenceStep, PerformPrimaryActionStep

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


# =============================================================================
# Tide of Darkness while defending
# =============================================================================


def _defending_dodger(*, with_ultimate: bool):
    """Level-8 Dodger about to block a 5-damage attack with Shield of Decay.

    The board carries no spawn points and no battle zone, so the card's "+2 if
    there are 2 or more empty spawn points in radius" clause can only hold via
    Tide of Darkness, which counts every free space as a spawn point.
    """
    state = (
        EffectScenarioBuilder()
        .with_hexes(
            [(q, r, -q - r) for q in range(-1, 3) for r in range(-1, 3) if -1 <= -q - r <= 2]
        )
        .red_hero("hero_attacker", at=(0, 0, 0))
        .blue_hero("hero_dodger", at=(1, 0, -1))
        .with_actor("hero_attacker")
        .build()
    )
    dodger = state.get_hero("hero_dodger")
    dodger.level = 8
    if with_ultimate:
        dodger.ultimate_card = hero_card("Dodger", "tide_of_darkness")
    shield = hero_card("Dodger", "shield_of_decay")
    shield.is_facedown = False
    dodger.hand = [shield]
    return state


def _block_five_damage(state):
    """Drive a plain 5-damage melee attack onto Dodger, blocked by Shield of Decay."""
    push_steps(state, [AttackSequenceStep(damage=5, range_val=1)])
    result = process_stack(state)
    assert result.input_request.request_type.value == "SELECT_UNIT"
    state.execution_stack[-1].pending_input = {"selection": "hero_dodger"}
    result = process_stack(state)
    assert result.input_request.request_type.value == "SELECT_CARD_OR_PASS"
    state.execution_stack[-1].pending_input = {"selection": "shield_of_decay"}
    process_stack(state)
    return BoardEntityID("hero_dodger") in state.entity_locations


@pytest.mark.effect_flow
def test_tide_of_darkness_counts_while_dodger_defends() -> None:
    """Blocking with a primary DEFENSE card is performing an action.

    Shield of Decay has Defense 3; the +2 clause is what survives a 5-damage
    attack. Tide of Darkness must satisfy that clause on Dodger's behalf even
    though the current actor during a defense is the attacker.
    """
    assert _block_five_damage(_defending_dodger(with_ultimate=True))


@pytest.mark.effect_flow
def test_defense_bonus_needs_the_clause_without_tide_of_darkness() -> None:
    """Control: no Tide, no spawn points, so the +2 never fires and Defense 3 falls.

    Without this, the test above could pass because the bonus applies
    unconditionally rather than because Tide satisfied the clause.
    """
    assert not _block_five_damage(_defending_dodger(with_ultimate=False))


@pytest.mark.effect_contract
def test_enfeeblement_creates_one_instance_per_payload() -> None:
    """The card's two clauses are two payloads of a single active effect."""
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_dodger",
            at=(0, 0, 0),
            current_card=hero_card("Dodger", "enfeeblement"),
        )
        .with_actor("hero_dodger")
        .build()
    )

    run_card(state, "hero_dodger").expect_input(InputRequestType.CHOOSE_ACTION).choose(
        "SKILL"
    ).finish()

    bound = [e for e in state.active_effects if e.source_card_id == "enfeeblement"]
    assert {e.effect_type for e in bound} == {
        EffectType.AREA_STAT_MODIFIER,
        EffectType.REPEAT_PREVENTION,
    }


@pytest.mark.effect_contract
def test_repeating_enfeeblement_does_not_duplicate_its_effect() -> None:
    """Only one instance of an active effect per card can be active."""
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_dodger",
            at=(0, 0, 0),
            current_card=hero_card("Dodger", "enfeeblement"),
        )
        .with_actor("hero_dodger")
        .build()
    )

    run_card(state, "hero_dodger").expect_input(InputRequestType.CHOOSE_ACTION).choose(
        "SKILL"
    ).finish()
    before = [e.id for e in state.active_effects]

    state.execution_context["selected_card"] = "enfeeblement"
    push_steps(state, [PerformPrimaryActionStep(hero_id="hero_dodger")])
    process_stack(state)

    assert [e.id for e in state.active_effects] == before


# =============================================================================
# Shields — emptiness is judged with Dodger as the hero performing the action
# =============================================================================


def _shield_state(*, wasp_team: TeamColor, rules_version: int = EMPTY_MEANS_NOT_OBSTACLE):
    """Dodger blocks 5 damage with Shield of Decay (Defense 3, +2 with 2+ empty
    spawn points). Two spawn points sit in his radius; a Static Barrier around
    (4, 0, -4) covers only (2, 0, -2), and Dodger stands outside it."""
    hexes = [(q, r, -q - r) for q in range(-4, 5) for r in range(-4, 5) if abs(-q - r) <= 4]
    state = (
        EffectScenarioBuilder()
        .with_hexes(hexes)
        .spawn_point((2, 0, -2))
        .spawn_point((1, 1, -2))
        .red_hero("hero_attacker", at=(0, 0, 0))
        .blue_hero("hero_dodger", at=(1, 0, -1))
        .hero("hero_wasp", team=wasp_team, at=(4, 0, -4))
        .with_actor("hero_attacker")
        .build()
    )
    state.active_zone_id = "z1"
    state.rules_version = rules_version
    EffectManager.create_effect(
        state=state,
        source_id="hero_wasp",
        effect_type=EffectType.STATIC_BARRIER,
        scope=EffectScope(shape=Shape.GLOBAL, affects=AffectsFilter.ENEMY_HEROES),
        duration=DurationType.THIS_TURN,
        is_active=True,
        barrier_radius=2,
        barrier_origin_id="hero_wasp",
    )
    shield = hero_card("Dodger", "shield_of_decay")
    shield.is_facedown = False
    state.get_hero("hero_dodger").hand = [shield]
    return state


@pytest.mark.effect_flow
def test_shield_loses_its_bonus_to_an_enemy_barrier() -> None:
    assert not _block_five_damage(_shield_state(wasp_team=TeamColor.RED))


@pytest.mark.effect_flow
def test_shield_keeps_its_bonus_under_a_teammates_barrier() -> None:
    # The attacker is Wasp's enemy, but emptiness is judged for Dodger, Wasp's ally.
    assert _block_five_damage(_shield_state(wasp_team=TeamColor.BLUE))


@pytest.mark.effect_flow
def test_shield_before_the_ruling_ignores_an_enemy_barrier() -> None:
    state = _shield_state(wasp_team=TeamColor.RED, rules_version=EMPTY_MEANS_NOT_OBSTACLE - 1)
    assert _block_five_damage(state)


def _dread_razor_state(*, barrier: bool):
    """Dodger next to one spawn point, (1, 0, -1), with an enemy adjacent too."""
    hexes = [(q, r, -q - r) for q in range(-4, 5) for r in range(-4, 5) if abs(-q - r) <= 4]
    state = (
        EffectScenarioBuilder()
        .with_hexes(hexes)
        .spawn_point((1, 0, -1))
        .blue_hero("hero_dodger", at=(0, 0, 0), current_card=hero_card("Dodger", "dread_razor"))
        .red_hero("hero_enemy", at=(-1, 0, 1))
        .red_hero("hero_wasp", at=(3, 0, -3))
        .with_actor("hero_dodger")
        .build()
    )
    state.active_zone_id = "z1"
    state.rules_version = EMPTY_MEANS_NOT_OBSTACLE
    if barrier:
        EffectManager.create_effect(
            state=state,
            source_id="hero_wasp",
            effect_type=EffectType.STATIC_BARRIER,
            scope=EffectScope(shape=Shape.GLOBAL, affects=AffectsFilter.ENEMY_HEROES),
            duration=DurationType.THIS_TURN,
            is_active=True,
            barrier_radius=2,
            barrier_origin_id="hero_wasp",
        )
    return state


def _dread_razor_first_prompt(state) -> InputRequestType:
    run = run_card(state, "hero_dodger")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    return process_stack(state).input_request.request_type


@pytest.mark.effect_flow
def test_dread_razor_offers_range_next_to_an_open_spawn_point() -> None:
    assert _dread_razor_first_prompt(_dread_razor_state(barrier=False)) == (
        InputRequestType.SELECT_NUMBER
    )


@pytest.mark.effect_flow
def test_dread_razor_is_melee_only_when_the_spawn_point_is_behind_an_enemy_barrier() -> None:
    assert _dread_razor_first_prompt(_dread_razor_state(barrier=True)) == (
        InputRequestType.SELECT_UNIT
    )

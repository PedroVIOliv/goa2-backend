"""Snorri: Inscribe the Runes + active_runes() helper.

TDD paths: docs/superpowers/plans/2026-07-10-snorri-tdd-paths.md §1
(H1-H6, U1). Later Snorri tasks extend this file with the remaining
rune-conditional cards; ``snorri_card``/``snorri_state`` are kept general
(free-form runes dict, turn number, board layout) for that reuse.
"""

from __future__ import annotations

import pytest

import goa2.scripts.snorri_effects  # noqa: F401 — registers @register_effect classes
from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardState,
    CardTier,
    EffectType,
    RuneType,
)
from goa2.domain.state import GameState
from goa2.domain.views import build_view
from goa2.engine.effect_manager import EffectManager
from goa2.engine.handler import process_stack, push_steps, submit_input
from goa2.engine.steps import AttackSequenceStep, SetContextFlagStep
from goa2.scripts.snorri_effects import active_runes

from ..builders import EffectScenarioBuilder
from ..runner import EffectRun, run_card


def snorri_card(card_id: str) -> Card:
    """Fetch a real Snorri card (fresh, playable copy) from the registry."""
    hero = HeroRegistry.get("Snorri")
    if hero is None:
        raise LookupError("Snorri hero not registered")
    candidates = [*hero.deck]
    if hero.ultimate_card is not None:
        candidates.append(hero.ultimate_card)
    for card in candidates:
        if card.id == card_id:
            playable = card.model_copy(deep=True)
            playable.state = CardState.UNRESOLVED
            playable.is_facedown = False
            return playable
    raise LookupError(card_id)


def snorri_state(
    card_id: str,
    *,
    turn: int = 1,
    runes: dict[int, RuneType] | None = None,
    enemy_hero_id: str = "hero_knight",
) -> GameState:
    """Small-arena scenario: Snorri (red) about to resolve ``card_id``."""
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero("hero_snorri", at=(0, 0, 0), current_card=snorri_card(card_id))
        .blue_hero(enemy_hero_id, at=(1, 0, -1))
        .with_actor("hero_snorri")
        .build()
    )
    state.turn = turn
    if runes:
        state.get_hero("hero_snorri").rune_slots = dict(runes)
    return state


def _hero_view(state: GameState, *, viewer_id: str, hero_id: str) -> dict:
    view = build_view(state, for_hero_id=viewer_id)
    for team in view["teams"].values():
        for hero_view in team["heroes"]:
            if hero_view["id"] == hero_id:
                return hero_view
    raise AssertionError(f"{hero_id} not found in view for {viewer_id}")


# ---------------------------------------------------------------------------
# section 1: Inscribe the Runes
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_inscribe_places_four_runes_with_choice():  # H1
    state = snorri_state("inscribe_the_runes")
    run = run_card(state, "hero_snorri")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input("SELECT_OPTION").choose("axe")
    run.expect_input("SELECT_OPTION").choose("bird")
    run.expect_input("SELECT_OPTION").choose("anvil")  # horn auto-placed
    run.finish()

    assert state.get_hero("hero_snorri").rune_slots == {
        1: RuneType.AXE,
        2: RuneType.BIRD,
        3: RuneType.ANVIL,
        4: RuneType.HORN,
    }
    assert "RUNES_PLACED" in [e.event_type.value for e in run.events]


@pytest.mark.effect_contract
def test_inscribe_rune_slots_public_to_opponent():  # H2
    state = snorri_state("inscribe_the_runes")
    run = run_card(state, "hero_snorri")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input("SELECT_OPTION").choose("horn")
    run.expect_input("SELECT_OPTION").choose("axe")
    run.expect_input("SELECT_OPTION").choose("bird")  # anvil auto-placed
    run.finish()

    snorri_view = _hero_view(state, viewer_id="hero_knight", hero_id="hero_snorri")
    assert snorri_view["rune_slots"] == {"1": "horn", "2": "axe", "3": "bird", "4": "anvil"}


@pytest.mark.effect_flow
def test_inscribe_replay_overwrites_arrangement():  # H3
    state = snorri_state(
        "inscribe_the_runes",
        runes={1: RuneType.AXE, 2: RuneType.BIRD, 3: RuneType.ANVIL, 4: RuneType.HORN},
    )
    run = run_card(state, "hero_snorri")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input("SELECT_OPTION").choose("horn")
    run.expect_input("SELECT_OPTION").choose("anvil")
    run.expect_input("SELECT_OPTION").choose("bird")  # axe auto-placed
    run.finish()

    assert state.get_hero("hero_snorri").rune_slots == {
        1: RuneType.HORN,
        2: RuneType.ANVIL,
        3: RuneType.BIRD,
        4: RuneType.AXE,
    }


@pytest.mark.effect_flow
def test_inscribe_survives_end_of_round_and_card_returns_to_hand():  # H4
    state = snorri_state("inscribe_the_runes")
    run = run_card(state, "hero_snorri", finalize_turn=True)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input("SELECT_OPTION").choose("axe")
    run.expect_input("SELECT_OPTION").choose("bird")
    run.expect_input("SELECT_OPTION").choose("anvil")
    run.finish()

    snorri = state.get_hero("hero_snorri")
    expected = dict(snorri.rune_slots)
    snorri.retrieve_cards()  # end-of-round card cleanup

    assert snorri.rune_slots == expected
    assert any(c.id == "inscribe_the_runes" for c in snorri.hand)


@pytest.mark.effect_contract
def test_inscribe_survives_defeat_and_respawn():  # H5
    state = snorri_state("inscribe_the_runes")
    run = run_card(state, "hero_snorri")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input("SELECT_OPTION").choose("axe")
    run.expect_input("SELECT_OPTION").choose("bird")
    run.expect_input("SELECT_OPTION").choose("anvil")
    run.finish()

    snorri = state.get_hero("hero_snorri")
    expected = dict(snorri.rune_slots)

    # Simulate defeat (removed from board) and respawn (re-placed elsewhere).
    state.remove_entity("hero_snorri")
    assert snorri.rune_slots == expected

    state.place_entity("hero_snorri", Hex(q=0, r=0, s=0))
    assert snorri.rune_slots == expected


@pytest.mark.effect_contract
def test_place_runes_step_survives_serialization_mid_prompt():
    """PlaceRunesStep pauses mid-arrangement across 3 prompts; a save/load
    between prompts must not lose the runes already placed — progress lives
    in the step's ``placed`` field, not local variables."""
    state = snorri_state("inscribe_the_runes")
    run = run_card(state, "hero_snorri")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input("SELECT_OPTION").choose("axe")
    run.expect_input("SELECT_OPTION")  # consumes "axe"; now prompting for slot 2

    step = state.execution_stack[-1]
    assert step.placed == {1: RuneType.AXE}

    restored = GameState.model_validate(state.model_dump(mode="json"))
    restored_step = restored.execution_stack[-1]
    assert restored_step.placed == {1: RuneType.AXE}

    submit_input(restored, {"selection": "bird"})
    result = process_stack(restored)
    assert result.input_request is not None
    assert result.input_request.request_type.value == "SELECT_OPTION"  # slot 3

    submit_input(restored, {"selection": "anvil"})  # horn auto-placed
    result = process_stack(restored)
    assert result.input_request is None

    assert restored.get_hero("hero_snorri").rune_slots == {
        1: RuneType.AXE,
        2: RuneType.BIRD,
        3: RuneType.ANVIL,
        4: RuneType.HORN,
    }


@pytest.mark.effect_contract
def test_active_runes_reflects_turn_slot_only():  # H6
    state = snorri_state(
        "runic_dagger",
        runes={1: RuneType.AXE, 2: RuneType.BIRD, 3: RuneType.ANVIL, 4: RuneType.HORN},
    )
    card = state.get_hero("hero_snorri").current_turn_card

    state.turn = 2
    assert active_runes(state, card, {}) == {RuneType.BIRD}

    for turn in (1, 3, 4):
        state.turn = turn
        assert RuneType.BIRD not in active_runes(state, card, {})


@pytest.mark.effect_contract
def test_active_runes_empty_before_inscribe():  # U1
    state = snorri_state("runic_dagger")  # rune_slots defaults empty
    card = state.get_hero("hero_snorri").current_turn_card
    assert active_runes(state, card, {}) == set()


@pytest.mark.effect_contract
def test_active_runes_uses_card_owner_not_current_actor():
    """A copied Snorri card (e.g. Mind Grip) must still see Snorri's runes —
    the owner is resolved by scanning card containers, not by
    ``state.current_actor_id`` (TDD §19)."""
    state = snorri_state(
        "runic_dagger",
        runes={1: RuneType.AXE, 2: RuneType.BIRD, 3: RuneType.ANVIL, 4: RuneType.HORN},
    )
    card = state.get_hero("hero_snorri").current_turn_card
    state.turn = 1
    state.current_actor_id = "hero_knight"
    assert active_runes(state, card, {}) == {RuneType.AXE}


@pytest.mark.effect_contract
def test_active_runes_unions_ultimate_context_keys():
    state = snorri_state(
        "runic_dagger",
        runes={1: RuneType.AXE, 2: RuneType.BIRD, 3: RuneType.ANVIL, 4: RuneType.HORN},
    )
    card = state.get_hero("hero_snorri").current_turn_card
    state.turn = 1
    context = {"snorri_ult_rune_action": RuneType.HORN.value}
    assert active_runes(state, card, context) == {RuneType.AXE, RuneType.HORN}


# ---------------------------------------------------------------------------
# sections 9-11: Oath defense family
# ---------------------------------------------------------------------------


def _attack_card(card_id: str, color: CardColor, *, is_ranged: bool = False) -> Card:
    return Card(
        id=card_id,
        name=card_id.replace("_", " ").title(),
        tier=CardTier.UNTIERED if color in (CardColor.GOLD, CardColor.SILVER) else CardTier.I,
        color=color,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=10,
        secondary_actions={},
        is_ranged=is_ranged,
        effect_id="",
        effect_text="",
        is_facedown=False,
    )


def _oath_state(
    oath_id: str,
    *,
    runes: dict[int, RuneType],
    attack_color: CardColor,
    is_ranged: bool = False,
) -> GameState:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(
            "hero_attacker",
            at=(0, 0, 0),
            current_card=_attack_card("incoming_attack", attack_color, is_ranged=is_ranged),
        )
        .blue_hero("hero_snorri", at=(1, 0, -1))
        .with_actor("hero_attacker")
        .build()
    )
    snorri = state.get_hero("hero_snorri")
    oath = snorri_card(oath_id)
    oath.state = CardState.HAND
    snorri.hand = [oath]
    snorri.rune_slots = dict(runes)
    state.turn = 1
    return state


def _run_oath_attack(state: GameState, *, rider: bool = False) -> EffectRun:
    steps = [
        AttackSequenceStep(
            damage=10,
            range_val=1,
            is_ranged=state.get_hero("hero_attacker").current_turn_card.is_ranged,
        )
    ]
    if rider:
        # A post-attack rider must still resolve after Oath's immunity takes
        # effect; it belongs to the attack already in progress.
        steps.append(SetContextFlagStep(key="blocked_attack_rider", value=True))
    push_steps(state, steps)
    run = EffectRun(state=state, hero_id="hero_attacker")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_snorri")
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose(
        state.get_hero("hero_snorri").hand[0].id
    )
    return run


def _combat_outcomes(run: EffectRun) -> list[str]:
    return [
        event.metadata["outcome"]
        for event in run.events
        if event.event_type == GameEventType.COMBAT_RESOLVED
    ]


def _has_oath_immunity(state: GameState) -> bool:
    return any(
        effect.effect_type == EffectType.IMMUNITY_ENEMY_ACTIONS
        and effect.source_id == "hero_snorri"
        and effect.is_active
        for effect in state.active_effects
    )


@pytest.mark.effect_flow
def test_oath_endurance_horn_blocks_basic_attack_and_grants_immunity():  # §9 H1
    state = _oath_state(
        "oath_of_endurance", runes={1: RuneType.HORN}, attack_color=CardColor.SILVER
    )

    run = _run_oath_attack(state).finish()

    assert _combat_outcomes(run) == ["BLOCKED"]
    assert _has_oath_immunity(state)


@pytest.mark.effect_flow
def test_oath_endurance_axe_blocks_non_ranged_attack():  # §9 H2
    state = _oath_state("oath_of_endurance", runes={1: RuneType.AXE}, attack_color=CardColor.RED)

    run = _run_oath_attack(state).finish()

    assert _combat_outcomes(run) == ["BLOCKED"]
    assert _has_oath_immunity(state)


@pytest.mark.effect_flow
def test_oath_endurance_mismatched_rune_does_not_block_or_grant_immunity():  # §9 U1
    state = _oath_state("oath_of_endurance", runes={1: RuneType.HORN}, attack_color=CardColor.RED)

    run = _run_oath_attack(state).finish()

    assert _combat_outcomes(run) == ["DEFEATED"]
    assert not _has_oath_immunity(state)


@pytest.mark.effect_flow
def test_oath_endurance_without_active_rune_does_not_block():  # §9 U2
    state = _oath_state("oath_of_endurance", runes={}, attack_color=CardColor.SILVER)

    run = _run_oath_attack(state).finish()

    assert _combat_outcomes(run) == ["DEFEATED"]
    assert not _has_oath_immunity(state)


@pytest.mark.effect_flow
def test_oath_endurance_immunity_does_not_stop_the_blocked_attack_rider():  # §9 U3
    state = _oath_state(
        "oath_of_endurance", runes={1: RuneType.HORN}, attack_color=CardColor.SILVER
    )

    run = _run_oath_attack(state, rider=True).finish()

    assert _combat_outcomes(run) == ["BLOCKED"]
    assert state.execution_context["blocked_attack_rider"] is True


@pytest.mark.effect_flow
def test_oath_endurance_immunity_expires_before_next_turn():  # §9 U4
    state = _oath_state(
        "oath_of_endurance", runes={1: RuneType.HORN}, attack_color=CardColor.SILVER
    )
    _run_oath_attack(state).finish()
    assert _has_oath_immunity(state)

    EffectManager.expire_active_turn_effects(state)
    state.turn = 2
    push_steps(state, [AttackSequenceStep(damage=10, range_val=1)])
    result = process_stack(state)

    assert result.input_request is not None
    assert {option.id for option in result.input_request.options} == {"hero_snorri"}
    assert not _has_oath_immunity(state)


@pytest.mark.effect_flow
def test_oath_fortitude_bird_blocks_ranged_attack():  # §10 H1
    state = _oath_state(
        "oath_of_fortitude",
        runes={1: RuneType.BIRD},
        attack_color=CardColor.RED,
        is_ranged=True,
    )

    run = _run_oath_attack(state).finish()

    assert _combat_outcomes(run) == ["BLOCKED"]


@pytest.mark.effect_flow
def test_oath_fortitude_treats_adjacent_ranged_attack_as_ranged():  # §10 H2
    bird_state = _oath_state(
        "oath_of_fortitude",
        runes={1: RuneType.BIRD},
        attack_color=CardColor.RED,
        is_ranged=True,
    )
    axe_state = _oath_state(
        "oath_of_fortitude",
        runes={1: RuneType.AXE},
        attack_color=CardColor.RED,
        is_ranged=True,
    )

    assert _combat_outcomes(_run_oath_attack(bird_state).finish()) == ["BLOCKED"]
    assert _combat_outcomes(_run_oath_attack(axe_state).finish()) == ["DEFEATED"]


@pytest.mark.effect_flow
def test_oath_perseverance_single_active_rune_is_auto_chosen():  # §11 H1
    state = _oath_state(
        "oath_of_perseverance", runes={1: RuneType.HORN}, attack_color=CardColor.GOLD
    )

    run = _run_oath_attack(state).finish()

    assert _combat_outcomes(run) == ["BLOCKED"]


@pytest.mark.effect_flow
def test_oath_perseverance_anvil_blocks_non_basic_attack():  # §11 H2
    state = _oath_state(
        "oath_of_perseverance", runes={1: RuneType.ANVIL}, attack_color=CardColor.GREEN
    )

    run = _run_oath_attack(state).finish()

    assert _combat_outcomes(run) == ["BLOCKED"]


@pytest.mark.effect_flow
def test_oath_perseverance_chosen_mismatched_rune_does_not_block():  # §11 U1
    state = _oath_state(
        "oath_of_perseverance", runes={1: RuneType.HORN}, attack_color=CardColor.SILVER
    )
    # This supplies a second active rune only to exercise Perseverance's
    # choose-one branch. Rune Mastery will populate this key in Task 11.
    state.execution_context["snorri_ult_rune_action"] = RuneType.BIRD.value

    run = _run_oath_attack(state)
    run.expect_input(InputRequestType.SELECT_OPTION).choose(RuneType.BIRD.value).finish()

    assert _combat_outcomes(run) == ["DEFEATED"]
    assert not _has_oath_immunity(state)

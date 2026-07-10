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
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import Card, CardState, RuneType
from goa2.domain.state import GameState
from goa2.domain.views import build_view
from goa2.engine.handler import process_stack, submit_input
from goa2.scripts.snorri_effects import active_runes

from ..builders import EffectScenarioBuilder
from ..runner import run_card


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

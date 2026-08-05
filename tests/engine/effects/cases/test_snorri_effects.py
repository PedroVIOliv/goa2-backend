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
    Minion,
    MinionType,
    RuneType,
    StatType,
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


# ---------------------------------------------------------------------------
# sections 2-4: Runic Dagger / Hammer / Battleaxe
# ---------------------------------------------------------------------------


def _runic_melee_state(
    card_id: str,
    *,
    runes: dict[int, RuneType] | None = None,
    hexes: list[tuple[int, int, int]] | None = None,
    target_at: tuple[int, int, int] = (1, 0, -1),
) -> GameState:
    builder = EffectScenarioBuilder().with_hexes(
        hexes
        or [
            (0, 0, 0),
            (1, 0, -1),
            (2, 0, -2),
            (3, 0, -3),
            (0, 1, -1),
            (1, 1, -2),
        ]
    )
    state = (
        builder.red_hero("hero_snorri", at=(0, 0, 0), current_card=snorri_card(card_id))
        .blue_hero("hero_knight", at=target_at)
        .with_actor("hero_snorri")
        .build()
    )
    state.turn = 1
    if runes:
        state.get_hero("hero_snorri").rune_slots = dict(runes)
    return state


def _start_melee_attack(state: GameState) -> EffectRun:
    run = run_card(state, "hero_snorri")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    return run


def _pass_hero_defense(run: EffectRun, target_id: str = "hero_knight") -> EffectRun:
    return (
        run.expect_input(InputRequestType.SELECT_UNIT)
        .choose(target_id)
        .expect_input(InputRequestType.SELECT_CARD_OR_PASS)
        .choose("PASS")
    )


def _combat_count(run: EffectRun) -> int:
    return sum(event.event_type == GameEventType.COMBAT_RESOLVED for event in run.events)


@pytest.mark.effect_flow
def test_runic_dagger_h1_anvil_retrieves_discarded_card():
    state = _runic_melee_state("runic_dagger", runes={1: RuneType.ANVIL})
    discarded = snorri_card("rune_sigils")
    state.get_hero("hero_snorri").discard_pile = [discarded]

    run = _start_melee_attack(state)
    _pass_hero_defense(run).expect_input(InputRequestType.SELECT_CARD).choose(discarded.id).finish()

    assert any(card.id == discarded.id for card in state.get_hero("hero_snorri").hand)


@pytest.mark.effect_flow
def test_runic_dagger_h2_can_decline_retrieve():
    state = _runic_melee_state("runic_dagger", runes={1: RuneType.ANVIL})
    discarded = snorri_card("rune_sigils")
    state.get_hero("hero_snorri").discard_pile = [discarded]

    run = _start_melee_attack(state)
    _pass_hero_defense(run).expect_input(InputRequestType.SELECT_CARD).skip().finish()

    assert state.get_hero("hero_snorri").discard_pile == [discarded]


@pytest.mark.effect_flow
def test_runic_dagger_h3_retrieves_after_target_is_defeated():
    state = _runic_melee_state("runic_dagger", runes={1: RuneType.ANVIL})
    discarded = snorri_card("rune_sigils")
    state.get_hero("hero_snorri").discard_pile = [discarded]

    run = _start_melee_attack(state)
    _pass_hero_defense(run).expect_input(InputRequestType.SELECT_CARD).choose(discarded.id).finish()

    assert state.get_position("hero_knight") is None
    assert any(card.id == discarded.id for card in state.get_hero("hero_snorri").hand)


@pytest.mark.effect_flow
def test_runic_dagger_u1_without_anvil_has_no_retrieve_prompt():
    state = _runic_melee_state("runic_dagger", runes={1: RuneType.HORN})
    state.get_hero("hero_snorri").discard_pile = [snorri_card("rune_sigils")]

    run = _start_melee_attack(state)
    _pass_hero_defense(run).finish()

    assert _combat_count(run) == 1


@pytest.mark.effect_flow
def test_runic_dagger_u2_empty_discard_has_no_retrieve_prompt():
    state = _runic_melee_state("runic_dagger", runes={1: RuneType.ANVIL})

    run = _start_melee_attack(state)
    _pass_hero_defense(run).finish()

    assert _combat_count(run) == 1


@pytest.mark.effect_flow
def test_runic_dagger_u3_no_adjacent_target_aborts_action():
    state = _runic_melee_state(
        "runic_dagger",
        hexes=[(0, 0, 0), (1, 0, -1), (2, 0, -2)],
        target_at=(2, 0, -2),
    )

    _start_melee_attack(state).finish()

    assert state.get_position("hero_knight") == Hex(q=2, r=0, s=-2)


@pytest.mark.effect_flow
def test_runic_hammer_h1_horn_premove_then_attacks_from_new_position():
    state = _runic_melee_state("runic_hammer", runes={1: RuneType.HORN}, target_at=(2, 0, -2))

    run = _start_melee_attack(state)
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 1, "r": 0, "s": -1})
    _pass_hero_defense(run).finish()

    assert state.get_position("hero_snorri") == Hex(q=1, r=0, s=-1)
    assert _combat_count(run) == 1


@pytest.mark.effect_flow
def test_runic_hammer_h2_can_decline_horn_premove():
    state = _runic_melee_state("runic_hammer", runes={1: RuneType.HORN})

    run = _start_melee_attack(state)
    run.expect_input(InputRequestType.SELECT_HEX).skip()
    _pass_hero_defense(run).finish()

    assert state.get_position("hero_snorri") == Hex(q=0, r=0, s=0)


@pytest.mark.effect_flow
def test_runic_hammer_h3_anvil_retrieves_without_premove():
    state = _runic_melee_state("runic_hammer", runes={1: RuneType.ANVIL})
    discarded = snorri_card("rune_sigils")
    state.get_hero("hero_snorri").discard_pile = [discarded]

    run = _start_melee_attack(state)
    _pass_hero_defense(run).expect_input(InputRequestType.SELECT_CARD).choose(discarded.id).finish()

    assert state.get_position("hero_snorri") == Hex(q=0, r=0, s=0)
    assert any(card.id == discarded.id for card in state.get_hero("hero_snorri").hand)


@pytest.mark.effect_flow
def test_runic_hammer_u1_without_rune_is_plain_adjacent_attack():
    state = _runic_melee_state("runic_hammer")

    run = _start_melee_attack(state)
    _pass_hero_defense(run).finish()

    assert _combat_count(run) == 1


@pytest.mark.effect_flow
def test_runic_hammer_u2_horn_without_legal_move_still_attacks():
    state = _runic_melee_state(
        "runic_hammer",
        runes={1: RuneType.HORN},
        hexes=[(0, 0, 0), (1, 0, -1)],
    )

    run = _start_melee_attack(state)
    _pass_hero_defense(run).finish()

    assert _combat_count(run) == 1


@pytest.mark.effect_flow
def test_runic_hammer_u3_premove_can_leave_no_adjacent_target_and_abort():
    state = _runic_melee_state(
        "runic_hammer",
        runes={1: RuneType.HORN},
        hexes=[(0, 0, 0), (1, 0, -1), (2, 0, -2), (-1, 1, 0)],
        target_at=(1, 0, -1),
    )

    run = _start_melee_attack(state)
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": -1, "r": 1, "s": 0}).finish()

    assert state.get_position("hero_snorri") == Hex(q=-1, r=1, s=0)
    assert state.get_position("hero_knight") == Hex(q=1, r=0, s=-1)


def _battleaxe_state_with_minions(*, minion_count: int) -> GameState:
    state = _runic_melee_state(
        "runic_battleaxe",
        runes={1: RuneType.AXE},
        hexes=[
            (0, 0, 0),
            (1, 0, -1),
            (2, 0, -2),
            (0, 1, -1),
            (1, 1, -2),
            (-1, 1, 0),
        ],
    )
    builder_minions = [(0, 1, -1), (1, 1, -2)]
    for index, location in enumerate(builder_minions[:minion_count], start=1):
        minion_id = f"blue_minion_{index}"
        state.teams[state.get_hero("hero_knight").team].minions.append(
            Minion(
                id=minion_id,
                name=minion_id,
                team=state.get_hero("hero_knight").team,
                type=MinionType.MELEE,
            )
        )
        state.place_entity(minion_id, Hex(q=location[0], r=location[1], s=location[2]))
    return state


@pytest.mark.effect_flow
def test_runic_battleaxe_h3_axe_repeats_full_attack_on_enemy_minion():
    state = _battleaxe_state_with_minions(minion_count=1)

    run = _start_melee_attack(state)
    _pass_hero_defense(run).expect_input(InputRequestType.SELECT_OPTION).choose("YES")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion_1").finish()

    assert _combat_count(run) == 2


@pytest.mark.effect_flow
def test_runic_battleaxe_h4_can_decline_repeat():
    state = _battleaxe_state_with_minions(minion_count=1)

    run = _start_melee_attack(state)
    _pass_hero_defense(run).expect_input(InputRequestType.SELECT_OPTION).choose("NO").finish()

    assert _combat_count(run) == 1


@pytest.mark.effect_flow
def test_runic_battleaxe_h5_horn_repeat_can_move_to_a_minion_two_spaces_away():
    """Horn's second pre-move is part of Battleaxe's full repeated sequence.

    The minion is not adjacent after the first attack, but it is two spaces
    away: Snorri can accept the repeat, move one space, then attack it.
    """
    state = _battleaxe_state_with_minions(minion_count=1)
    state.execution_context["snorri_ult_rune_action"] = RuneType.HORN.value
    state.remove_entity("blue_minion_1")
    state.place_entity("blue_minion_1", Hex(q=2, r=0, s=-2))

    run = _start_melee_attack(state)
    run.expect_input(InputRequestType.SELECT_HEX).skip()
    _pass_hero_defense(run).expect_input(InputRequestType.SELECT_OPTION).choose("YES")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 1, "r": 0, "s": -1})
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion_1").finish()

    assert _combat_count(run) == 2


@pytest.mark.effect_flow
def test_runic_battleaxe_horn_repeat_move_resolves_before_impossible_attack_aborts():
    state = _battleaxe_state_with_minions(minion_count=1)
    state.execution_context["snorri_ult_rune_action"] = RuneType.HORN.value
    state.remove_entity("blue_minion_1")
    state.place_entity("blue_minion_1", Hex(q=3, r=0, s=-3))

    run = _start_melee_attack(state)
    run.expect_input(InputRequestType.SELECT_HEX).skip()
    _pass_hero_defense(run).expect_input(InputRequestType.SELECT_OPTION).choose("YES")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 0, "r": 1, "s": -1}).finish()

    assert state.get_position("hero_snorri") == Hex(q=0, r=1, s=-1)
    assert _combat_count(run) == 1


# ---------------------------------------------------------------------------
# sections 5-6: Runecaster / Runeblaster
# ---------------------------------------------------------------------------


def _runic_ranged_state(
    card_id: str,
    *,
    runes: dict[int, RuneType] | None = None,
    target_at: tuple[int, int, int] = (3, 0, -3),
    bystanders: list[tuple[str, tuple[int, int, int]]] | None = None,
    near_target_at: tuple[int, int, int] | None = None,
) -> GameState:
    hexes = [
        (0, 0, 0),
        (1, 0, -1),
        (2, 0, -2),
        (3, 0, -3),
        (4, 0, -4),
        (0, 1, -1),
        (1, 1, -2),
        (2, 1, -3),
        (3, 1, -4),
    ]
    builder = (
        EffectScenarioBuilder()
        .with_hexes(hexes)
        .red_hero("hero_snorri", at=(0, 0, 0), current_card=snorri_card(card_id))
        .blue_minion("blue_target", at=target_at)
        .with_actor("hero_snorri")
    )
    if near_target_at is not None:
        builder.blue_minion("blue_near", at=near_target_at)
    for hero_id, location in bystanders or []:
        builder.blue_hero(hero_id, at=location)

    state = builder.build()
    state.turn = 1
    if runes:
        state.get_hero("hero_snorri").rune_slots = dict(runes)
    return state


def _start_ranged_attack(state: GameState) -> EffectRun:
    run = run_card(state, "hero_snorri")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    return run


@pytest.mark.effect_flow
def test_runecaster_h1_only_targets_at_effective_maximum_range():
    state = _runic_ranged_state("runecaster", target_at=(4, 0, -4), near_target_at=(3, 0, -3))
    state.get_hero("hero_snorri").items[StatType.RANGE] = 1

    run = _start_ranged_attack(state).expect_input(InputRequestType.SELECT_UNIT)

    assert {option.id for option in run.latest_request.options} == {"blue_target"}
    run.choose("blue_target").finish()


@pytest.mark.effect_flow
def test_runecaster_h2_horn_moves_up_to_two_after_attack():
    state = _runic_ranged_state("runecaster", runes={1: RuneType.HORN})

    run = _start_ranged_attack(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_target")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 2, "r": 0, "s": -2}).finish()

    assert state.get_position("hero_snorri") == Hex(q=2, r=0, s=-2)


@pytest.mark.effect_flow
def test_runecaster_h3_axe_makes_snapshot_hero_discard():
    state = _runic_ranged_state(
        "runecaster",
        runes={1: RuneType.AXE},
        bystanders=[("hero_bystander", (3, 1, -4))],
    )
    discard = snorri_card("rune_sigils")
    state.get_hero("hero_bystander").hand = [discard]

    run = _start_ranged_attack(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_target")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_bystander")
    run.expect_input(InputRequestType.SELECT_CARD).choose(discard.id).finish()

    assert state.get_hero("hero_bystander").hand == []
    assert state.get_hero("hero_bystander").discard_pile == [discard]


@pytest.mark.effect_flow
def test_runecaster_h4_axe_defeats_snapshot_hero_without_cards():
    state = _runic_ranged_state(
        "runecaster",
        runes={1: RuneType.AXE},
        bystanders=[("hero_bystander", (3, 1, -4))],
    )

    run = _start_ranged_attack(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_target")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_bystander").finish()

    assert state.get_position("hero_bystander") is None


@pytest.mark.effect_flow
def test_runecaster_h5_axe_chooses_between_multiple_snapshot_heroes():
    state = _runic_ranged_state(
        "runecaster",
        runes={1: RuneType.AXE},
        bystanders=[("hero_a", (3, 1, -4)), ("hero_b", (2, 1, -3))],
    )
    card_a = snorri_card("rune_sigils")
    card_b = snorri_card("safe_passage")
    state.get_hero("hero_a").hand = [card_a]
    state.get_hero("hero_b").hand = [card_b]

    run = _start_ranged_attack(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_target")
    run.expect_input(InputRequestType.SELECT_UNIT)
    assert {option.id for option in run.latest_request.options} == {"hero_a", "hero_b"}
    run.choose("hero_b").expect_input(InputRequestType.SELECT_CARD).choose(card_b.id).finish()

    assert state.get_hero("hero_a").hand == [card_a]
    assert state.get_hero("hero_b").hand == []


@pytest.mark.effect_flow
def test_runecaster_h6_axe_uses_targeting_time_adjacency_after_target_defeat():
    state = _runic_ranged_state(
        "runecaster",
        runes={1: RuneType.AXE},
        bystanders=[("hero_bystander", (3, 1, -4))],
    )

    run = _start_ranged_attack(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_target")
    run.expect_input(InputRequestType.SELECT_UNIT)

    assert state.get_position("blue_target") is None
    assert {option.id for option in run.latest_request.options} == {"hero_bystander"}


@pytest.mark.effect_flow
def test_runecaster_u1_without_maximum_range_target_aborts():
    state = _runic_ranged_state("runecaster", target_at=(2, 0, -2))

    _start_ranged_attack(state).finish()

    assert state.get_position("blue_target") == Hex(q=2, r=0, s=-2)


@pytest.mark.effect_flow
def test_runecaster_u2_axe_without_snapshot_hero_has_no_rider_prompt():
    state = _runic_ranged_state("runecaster", runes={1: RuneType.AXE})

    run = _start_ranged_attack(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_target").finish()

    assert _combat_count(run) == 1


@pytest.mark.effect_flow
def test_runecaster_u3_exact_range_uses_topology_not_obstacle_pathing():
    state = _runic_ranged_state("runecaster")
    state.board.tiles[Hex(q=1, r=0, s=-1)].is_terrain = True

    run = _start_ranged_attack(state).expect_input(InputRequestType.SELECT_UNIT)

    assert {option.id for option in run.latest_request.options} == {"blue_target"}


@pytest.mark.effect_flow
def test_runecaster_u4_axe_excludes_immune_snapshot_hero():
    state = _runic_ranged_state(
        "runecaster",
        runes={1: RuneType.AXE},
        bystanders=[("hero_immune", (3, 1, -4))],
    )
    from goa2.domain.models import AffectsFilter, DurationType, EffectScope, EffectType, Shape
    from goa2.engine.effect_manager import EffectManager

    EffectManager.create_effect(
        state=state,
        source_id="hero_immune",
        effect_type=EffectType.IMMUNITY_ENEMY_ACTIONS,
        scope=EffectScope(shape=Shape.POINT, origin_id="hero_immune", affects=AffectsFilter.SELF),
        duration=DurationType.THIS_TURN,
        is_active=True,
    )

    run = _start_ranged_attack(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_target").finish()

    assert state.execution_context["rc_adjacent"] == []


@pytest.mark.effect_flow
def test_runeblaster_h1_bird_targets_any_unit_in_range():
    state = _runic_ranged_state("runeblaster", runes={1: RuneType.BIRD}, near_target_at=(1, 0, -1))

    run = _start_ranged_attack(state).expect_input(InputRequestType.SELECT_UNIT)

    assert {option.id for option in run.latest_request.options} == {"blue_target", "blue_near"}
    run.choose("blue_near").finish()


@pytest.mark.effect_flow
def test_runeblaster_u1_without_bird_requires_maximum_range():
    state = _runic_ranged_state("runeblaster", near_target_at=(1, 0, -1))

    run = _start_ranged_attack(state).expect_input(InputRequestType.SELECT_UNIT)

    assert {option.id for option in run.latest_request.options} == {"blue_target"}


# ---------------------------------------------------------------------------
# sections 7-8: Runetrap / Runebomb
# ---------------------------------------------------------------------------


def _rune_discard_state(
    card_id: str,
    *,
    runes: dict[int, RuneType] | None = None,
    include_victim: bool = True,
) -> GameState:
    builder = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero("hero_snorri", at=(0, 0, 0), current_card=snorri_card(card_id))
        .with_actor("hero_snorri")
    )
    if include_victim:
        builder.blue_hero("hero_victim", at=(1, 0, -1))
    state = builder.build()
    state.turn = 1
    if runes:
        state.get_hero("hero_snorri").rune_slots = dict(runes)
    return state


def _start_rune_discard(state: GameState) -> EffectRun:
    run = run_card(state, "hero_snorri")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    return run


@pytest.mark.effect_flow
@pytest.mark.parametrize(
    ("rune", "color"),
    [
        (RuneType.HORN, CardColor.GREEN),
        (RuneType.AXE, CardColor.SILVER),
        (RuneType.ANVIL, CardColor.BLUE),
    ],
)
def test_runetrap_h1_h2_h3_discards_the_rune_color(rune: RuneType, color: CardColor):
    state = _rune_discard_state("runetrap", runes={1: rune})
    matching = _attack_card(f"matching_{color.value}", color)
    other = _attack_card("other_red", CardColor.RED)
    state.get_hero("hero_victim").hand = [matching, other]

    run = _start_rune_discard(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_victim")
    run.expect_input(InputRequestType.SELECT_CARD).choose(matching.id).finish()

    victim = state.get_hero("hero_victim")
    assert victim.hand == [other]
    assert victim.discard_pile == [matching]


@pytest.mark.effect_flow
def test_runetrap_u1_bird_has_no_bullet():
    state = _rune_discard_state("runetrap", runes={1: RuneType.BIRD})
    state.get_hero("hero_victim").hand = [_attack_card("green", CardColor.GREEN)]

    _start_rune_discard(state).finish()

    assert len(state.get_hero("hero_victim").hand) == 1


@pytest.mark.effect_flow
def test_runetrap_u2_no_matching_color_fizzles():
    state = _rune_discard_state("runetrap", runes={1: RuneType.HORN})
    state.get_hero("hero_victim").hand = [_attack_card("red", CardColor.RED)]

    run = _start_rune_discard(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_victim").finish()

    assert [card.id for card in state.get_hero("hero_victim").hand] == ["red"]


@pytest.mark.effect_flow
def test_runetrap_u3_without_enemy_hero_fizzles():
    state = _rune_discard_state("runetrap", runes={1: RuneType.HORN}, include_victim=False)

    _start_rune_discard(state).finish()

    assert state.execution_context.get("rt_victim") is None


@pytest.mark.effect_flow
def test_runetrap_u4_without_rune_fizzles():
    state = _rune_discard_state("runetrap")
    state.get_hero("hero_victim").hand = [_attack_card("green", CardColor.GREEN)]

    _start_rune_discard(state).finish()

    assert [card.id for card in state.get_hero("hero_victim").hand] == ["green"]


@pytest.mark.effect_flow
def test_runetrap_u5_excludes_immune_enemy_hero():
    state = _rune_discard_state("runetrap", runes={1: RuneType.HORN})
    from goa2.domain.models import AffectsFilter, DurationType, EffectScope, EffectType, Shape
    from goa2.engine.effect_manager import EffectManager

    EffectManager.create_effect(
        state=state,
        source_id="hero_victim",
        effect_type=EffectType.IMMUNITY_ENEMY_ACTIONS,
        scope=EffectScope(shape=Shape.POINT, origin_id="hero_victim", affects=AffectsFilter.SELF),
        duration=DurationType.THIS_TURN,
        is_active=True,
    )

    _start_rune_discard(state).finish()

    assert state.execution_context.get("rt_victim") is None


@pytest.mark.effect_flow
def test_runetrap_u6_only_discards_from_hand():
    state = _rune_discard_state("runetrap", runes={1: RuneType.HORN})
    committed = _attack_card("committed_green", CardColor.GREEN)
    committed.state = CardState.UNRESOLVED
    resolved = _attack_card("resolved_green", CardColor.GREEN)
    resolved.state = CardState.RESOLVED
    victim = state.get_hero("hero_victim")
    victim.current_turn_card = committed
    victim.played_cards = [resolved]

    run = _start_rune_discard(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_victim").finish()

    assert victim.current_turn_card is committed
    assert victim.played_cards == [resolved]


@pytest.mark.effect_flow
def test_runebomb_h1_single_rune_is_auto_chosen():
    state = _rune_discard_state("runebomb", runes={1: RuneType.HORN})
    green = _attack_card("green", CardColor.GREEN)
    state.get_hero("hero_victim").hand = [green]

    run = _start_rune_discard(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_victim")
    run.expect_input(InputRequestType.SELECT_CARD).choose(green.id).finish()

    assert state.get_hero("hero_victim").discard_pile == [green]


@pytest.mark.effect_flow
def test_runebomb_h2_bird_discards_gold():
    state = _rune_discard_state("runebomb", runes={1: RuneType.BIRD})
    gold = _attack_card("gold", CardColor.GOLD)
    state.get_hero("hero_victim").hand = [gold]

    run = _start_rune_discard(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_victim")
    run.expect_input(InputRequestType.SELECT_CARD).choose(gold.id).finish()

    assert state.get_hero("hero_victim").discard_pile == [gold]


@pytest.mark.effect_flow
def test_runebomb_u1_without_rune_fizzles():
    state = _rune_discard_state("runebomb")
    state.get_hero("hero_victim").hand = [_attack_card("gold", CardColor.GOLD)]

    _start_rune_discard(state).finish()

    assert len(state.get_hero("hero_victim").hand) == 1


# ---------------------------------------------------------------------------
# sections 12-14: Passage family
# ---------------------------------------------------------------------------


def _passage_state(
    card_id: str,
    *,
    runes: dict[int, RuneType] | None = None,
    length: int = 6,
) -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(length)])
        .red_hero("hero_snorri", at=(0, 0, 0), current_card=snorri_card(card_id))
        .with_actor("hero_snorri")
        .build()
    )
    state.turn = 1
    if runes:
        state.get_hero("hero_snorri").rune_slots = dict(runes)
    return state


def _start_passage(state: GameState) -> EffectRun:
    run = run_card(state, "hero_snorri")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("MOVEMENT")
    return run


def _has_passage_immunity(state: GameState) -> bool:
    return any(
        effect.effect_type == EffectType.IMMUNITY_ENEMY_ACTIONS
        and effect.source_id == "hero_snorri"
        and effect.is_active
        for effect in state.active_effects
    )


@pytest.mark.effect_flow
def test_safe_passage_h1_bird_moves_through_obstacle():
    state = _passage_state("safe_passage", runes={1: RuneType.BIRD}, length=4)
    state.board.tiles[Hex(q=1, r=0, s=-1)].is_terrain = True

    _start_passage(state).expect_input(InputRequestType.SELECT_HEX).choose(
        {"q": 3, "r": 0, "s": -3}
    ).finish()

    assert state.get_position("hero_snorri") == Hex(q=3, r=0, s=-3)


@pytest.mark.effect_flow
def test_safe_passage_h2_bird_still_allows_normal_pathing():
    state = _passage_state("safe_passage", runes={1: RuneType.BIRD}, length=3)

    _start_passage(state).expect_input(InputRequestType.SELECT_HEX).choose(
        {"q": 2, "r": 0, "s": -2}
    ).finish()

    assert state.get_position("hero_snorri") == Hex(q=2, r=0, s=-2)


@pytest.mark.effect_flow
def test_safe_passage_u1_without_bird_cannot_path_through_obstacle():
    state = _passage_state("safe_passage", length=4)
    state.board.tiles[Hex(q=1, r=0, s=-1)].is_terrain = True

    run = _start_passage(state).expect_input(InputRequestType.SELECT_HEX)

    assert '{"q":3,"r":0,"s":-3}' not in {str(option.id) for option in run.latest_request.options}


@pytest.mark.effect_flow
def test_hidden_passage_h1_anvil_grants_immunity_after_move():
    state = _passage_state("hidden_passage", runes={1: RuneType.ANVIL})

    _start_passage(state).expect_input(InputRequestType.SELECT_HEX).choose(
        {"q": 1, "r": 0, "s": -1}
    ).finish()

    assert _has_passage_immunity(state)


@pytest.mark.effect_flow
def test_hidden_passage_h2_bird_ignores_obstacles():
    state = _passage_state("hidden_passage", runes={1: RuneType.BIRD}, length=4)
    state.board.tiles[Hex(q=1, r=0, s=-1)].is_terrain = True

    _start_passage(state).expect_input(InputRequestType.SELECT_HEX).choose(
        {"q": 3, "r": 0, "s": -3}
    ).finish()

    assert state.get_position("hero_snorri") == Hex(q=3, r=0, s=-3)


@pytest.mark.effect_flow
def test_hidden_passage_u1_immunity_expires_at_turn_end():
    state = _passage_state("hidden_passage", runes={1: RuneType.ANVIL})
    _start_passage(state).expect_input(InputRequestType.SELECT_HEX).choose(
        {"q": 1, "r": 0, "s": -1}
    ).finish()

    EffectManager.expire_active_turn_effects(state)

    assert not _has_passage_immunity(state)


@pytest.mark.effect_flow
def test_hidden_passage_u2_without_rune_is_plain_movement():
    state = _passage_state("hidden_passage")

    _start_passage(state).expect_input(InputRequestType.SELECT_HEX).choose(
        {"q": 3, "r": 0, "s": -3}
    ).finish()

    assert state.get_position("hero_snorri") == Hex(q=3, r=0, s=-3)
    assert not _has_passage_immunity(state)


@pytest.mark.effect_flow
def test_deep_passage_h1_horn_moves_up_to_five():
    state = _passage_state("deep_passage", runes={1: RuneType.HORN}, length=6)

    _start_passage(state).expect_input(InputRequestType.SELECT_HEX).choose(
        {"q": 5, "r": 0, "s": -5}
    ).finish()

    assert state.get_position("hero_snorri") == Hex(q=5, r=0, s=-5)


@pytest.mark.effect_flow
def test_deep_passage_u1_without_rune_is_plain_movement_three():
    state = _passage_state("deep_passage", length=6)

    run = _start_passage(state).expect_input(InputRequestType.SELECT_HEX)
    options = {option.metadata["raw"] for option in run.latest_request.options}
    assert Hex(q=3, r=0, s=-3) in options
    assert Hex(q=4, r=0, s=-4) not in options
    assert Hex(q=5, r=0, s=-5) not in options


@pytest.mark.effect_flow
def test_runic_battleaxe_u3_without_adjacent_enemy_minion_does_not_offer_repeat():
    state = _battleaxe_state_with_minions(minion_count=0)

    run = _start_melee_attack(state)
    _pass_hero_defense(run).finish()

    assert _combat_count(run) == 1


@pytest.mark.effect_flow
def test_runic_battleaxe_u4_repeat_does_not_offer_another_repeat():
    state = _battleaxe_state_with_minions(minion_count=2)

    run = _start_melee_attack(state)
    _pass_hero_defense(run).expect_input(InputRequestType.SELECT_OPTION).choose("YES")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion_1").finish()

    assert _combat_count(run) == 2


# ---------------------------------------------------------------------------
# sections 15-16: Ancestral Boon / Ancestral Grace
# ---------------------------------------------------------------------------


def _ancestral_state(card_id: str, *, runes: dict[int, RuneType]) -> GameState:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero("hero_snorri", at=(0, 0, 0), current_card=snorri_card(card_id))
        .red_hero("hero_ally", at=(1, 0, -1))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor("hero_snorri")
        .build()
    )
    state.get_hero("hero_snorri").rune_slots = dict(runes)
    return state


def _start_ancestral(state: GameState) -> EffectRun:
    return (
        run_card(state, "hero_snorri").expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    )


def _ally_cards(state: GameState, *, item: str = "runic_hammer", target: str = "runecaster"):
    ally = state.get_hero("hero_ally")
    item_card = snorri_card(item)
    target_card = snorri_card(target)
    ally.deck = [item_card, target_card]
    return ally, item_card, target_card


@pytest.mark.effect_flow
def test_ancestral_boon_h1_axe_swaps_resolved_and_hand_cards_in_place():
    state = _ancestral_state("ancestral_boon", runes={1: RuneType.AXE})
    ally, resolved, hand = _ally_cards(state)
    resolved.state = CardState.RESOLVED
    hand.state = CardState.HAND
    ally.played_cards = [resolved]
    ally.hand = [hand]

    run = _start_ancestral(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_ally")
    run.expect_input(InputRequestType.SELECT_CARD).choose(resolved.id)
    run.expect_input(InputRequestType.SELECT_CARD).choose(hand.id).finish()

    assert ally.played_cards == [hand]
    assert ally.hand == [resolved]
    assert hand.state == CardState.RESOLVED
    assert resolved.state == CardState.HAND


@pytest.mark.effect_flow
def test_ancestral_boon_h2_anvil_retrieves_every_discarded_card():
    state = _ancestral_state("ancestral_boon", runes={1: RuneType.ANVIL})
    ally, first, second = _ally_cards(state)
    first.state = second.state = CardState.DISCARD
    ally.discard_pile = [first, second]

    _start_ancestral(state).expect_input(InputRequestType.SELECT_UNIT).choose("hero_ally").finish()

    assert ally.discard_pile == []
    assert ally.hand == [first, second]
    assert {card.state for card in ally.hand} == {CardState.HAND}


@pytest.mark.effect_flow
def test_ancestral_boon_h3_recipient_can_decline():
    state = _ancestral_state("ancestral_boon", runes={1: RuneType.AXE})
    ally, resolved, hand = _ally_cards(state)
    resolved.state = CardState.RESOLVED
    hand.state = CardState.HAND
    ally.played_cards = [resolved]
    ally.hand = [hand]

    _start_ancestral(state).expect_input(InputRequestType.SELECT_UNIT).skip().finish()

    assert ally.played_cards == [resolved]
    assert ally.hand == [hand]


@pytest.mark.effect_flow
def test_ancestral_boon_u1_without_friendly_hero_fizzles():
    state = snorri_state("ancestral_boon", runes={1: RuneType.AXE})

    _start_ancestral(state).finish()


@pytest.mark.effect_contract
def test_ancestral_boon_u2_never_offers_snorri_as_recipient():
    state = _ancestral_state("ancestral_boon", runes={1: RuneType.AXE})

    run = _start_ancestral(state).expect_input(InputRequestType.SELECT_UNIT)

    assert "hero_snorri" not in {option.id for option in run.latest_request.options}


@pytest.mark.effect_contract
def test_ancestral_boon_u6_immune_friendly_hero_is_not_selectable():
    from goa2.domain.models import AffectsFilter, DurationType, EffectScope, Hero, Shape, TeamColor

    state = _ancestral_state("ancestral_boon", runes={1: RuneType.AXE})
    EffectManager.create_effect(
        state=state,
        source_id="hero_ally",
        effect_type=EffectType.IMMUNITY_ENEMY_ACTIONS,
        scope=EffectScope(shape=Shape.POINT, origin_id="hero_ally", affects=AffectsFilter.SELF),
        duration=DurationType.THIS_TURN,
        is_active=True,
        blocks_friendly_actors=True,
    )
    other = Hero(id="hero_other", name="hero_other", team=TeamColor.RED, deck=[])
    state.teams[TeamColor.RED].heroes.append(other)
    state.place_entity("hero_other", Hex(q=0, r=1, s=-1))

    run = _start_ancestral(state).expect_input(InputRequestType.SELECT_UNIT)

    assert "hero_ally" not in {option.id for option in run.latest_request.options}
    assert "hero_other" in {option.id for option in run.latest_request.options}


@pytest.mark.effect_flow
def test_ancestral_boon_u3_axe_skips_when_recipient_has_no_resolved_or_hand_card():
    state = _ancestral_state("ancestral_boon", runes={1: RuneType.AXE})

    _start_ancestral(state).expect_input(InputRequestType.SELECT_UNIT).choose("hero_ally").finish()


@pytest.mark.effect_flow
def test_ancestral_boon_u4_anvil_empty_discard_does_nothing():
    state = _ancestral_state("ancestral_boon", runes={1: RuneType.ANVIL})
    ally = state.get_hero("hero_ally")

    _start_ancestral(state).expect_input(InputRequestType.SELECT_UNIT).choose("hero_ally").finish()

    assert ally.hand == []


@pytest.mark.effect_flow
def test_ancestral_boon_u5_without_rune_fizzles():
    state = _ancestral_state("ancestral_boon", runes={})

    _start_ancestral(state).finish()


@pytest.mark.effect_flow
def test_ancestral_grace_h1_bird_swaps_item_with_same_tier_color_hand_card():
    state = _ancestral_state("ancestral_grace", runes={1: RuneType.BIRD})
    ally, item_card, target = _ally_cards(state)
    item_card.state = CardState.ITEM
    target.state = CardState.HAND
    ally.items = {item_card.item: 1}
    ally.hand = [target]

    run = _start_ancestral(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_ally")
    run.expect_input(InputRequestType.SELECT_CARD).choose(item_card.id)
    run.expect_input(InputRequestType.SELECT_CARD).choose(target.id).finish()

    assert target.state == CardState.ITEM
    assert item_card.state == CardState.HAND
    assert ally.hand == [item_card]
    assert ally.items[item_card.item] == 0
    assert ally.items[target.item] == 1


@pytest.mark.effect_flow
def test_ancestral_grace_h2_item_card_keeps_resolved_slot_location():
    state = _ancestral_state("ancestral_grace", runes={1: RuneType.BIRD})
    ally, item_card, target = _ally_cards(state)
    item_card.state = CardState.ITEM
    target.state = CardState.RESOLVED
    ally.items = {item_card.item: 1}
    ally.played_cards = [target]

    run = _start_ancestral(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_ally")
    run.expect_input(InputRequestType.SELECT_CARD).choose(item_card.id)
    run.expect_input(InputRequestType.SELECT_CARD).choose(target.id).finish()

    assert ally.played_cards == [item_card]
    assert item_card.state == CardState.RESOLVED
    assert target.state == CardState.ITEM


@pytest.mark.effect_flow
def test_ancestral_grace_h3_item_card_keeps_discard_location():
    state = _ancestral_state("ancestral_grace", runes={1: RuneType.BIRD})
    ally, item_card, target = _ally_cards(state)
    item_card.state = CardState.ITEM
    target.state = CardState.DISCARD
    ally.items = {item_card.item: 1}
    ally.discard_pile = [target]

    run = _start_ancestral(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_ally")
    run.expect_input(InputRequestType.SELECT_CARD).choose(item_card.id)
    run.expect_input(InputRequestType.SELECT_CARD).choose(target.id).finish()

    assert ally.discard_pile == [item_card]
    assert item_card.state == CardState.DISCARD
    assert target.state == CardState.ITEM


@pytest.mark.effect_flow
def test_ancestral_grace_u1_bird_has_no_effect_without_item_card():
    state = _ancestral_state("ancestral_grace", runes={1: RuneType.BIRD})

    _start_ancestral(state).expect_input(InputRequestType.SELECT_UNIT).choose("hero_ally").finish()


@pytest.mark.effect_flow
def test_ancestral_grace_u2_bird_requires_a_same_tier_color_non_item_card():
    state = _ancestral_state("ancestral_grace", runes={1: RuneType.BIRD})
    ally, item_card, target = _ally_cards(state, target="runic_dagger")
    item_card.state = CardState.ITEM
    target.state = CardState.HAND
    ally.items = {item_card.item: 1}
    ally.hand = [target]

    run = _start_ancestral(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_ally")
    run.expect_input(InputRequestType.SELECT_CARD).choose(item_card.id).finish()

    assert item_card.state == CardState.ITEM
    assert target.state == CardState.HAND


# ---------------------------------------------------------------------------
# section 17: Rune Sigils
# ---------------------------------------------------------------------------


def _rune_sigils_state(
    *,
    runes: dict[int, RuneType] | None = None,
    enemies: list[tuple[str, tuple[int, int, int]]] | None = None,
    minions: list[tuple[str, tuple[int, int, int]]] | None = None,
) -> GameState:
    hexes = [
        (0, 0, 0),
        (1, 0, -1),
        (2, 0, -2),
        (3, 0, -3),
        (0, 1, -1),
        (1, 1, -2),
        (2, 1, -3),
    ]
    builder = (
        EffectScenarioBuilder()
        .with_hexes(hexes)
        .red_hero("hero_snorri", at=(0, 0, 0), current_card=snorri_card("rune_sigils"))
        .with_actor("hero_snorri")
    )
    for hero_id, location in enemies or []:
        builder.blue_hero(hero_id, at=location)
    for minion_id, location in minions or []:
        builder.blue_minion(minion_id, at=location)
    state = builder.build()
    state.turn = 1
    if runes:
        state.get_hero("hero_snorri").rune_slots = dict(runes)
    return state


def _start_rune_sigils(state: GameState) -> EffectRun:
    return (
        run_card(state, "hero_snorri").expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    )


def _attack_values(run: EffectRun) -> list[int]:
    return [
        event.metadata["attack_value"]
        for event in run.events
        if event.event_type == GameEventType.COMBAT_RESOLVED
    ]


def _pass_sigils_defense(run: EffectRun) -> EffectRun:
    return run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")


@pytest.mark.effect_flow
def test_rune_sigils_h1_adjacent_attack_is_ranged_without_an_active_rune():
    state = _rune_sigils_state(enemies=[("hero_target", (1, 0, -1))])

    run = _start_rune_sigils(state)
    _pass_sigils_defense(
        run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_target")
    ).finish()

    assert _attack_values(run) == [2]
    assert state.execution_context["attack_is_ranged"] is True


@pytest.mark.effect_flow
def test_rune_sigils_h2_bird_can_target_enemy_minion_in_range():
    state = _rune_sigils_state(runes={1: RuneType.BIRD}, minions=[("blue_minion", (2, 0, -2))])

    run = _start_rune_sigils(state)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("blue_minion").finish()

    assert _attack_values(run) == [2]


@pytest.mark.effect_flow
def test_rune_sigils_h3_axe_adds_three_attack():
    state = _rune_sigils_state(runes={1: RuneType.AXE}, enemies=[("hero_target", (1, 0, -1))])

    run = _start_rune_sigils(state)
    _pass_sigils_defense(
        run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_target")
    ).finish()

    assert _attack_values(run) == [5]


@pytest.mark.effect_flow
def test_rune_sigils_h4_anvil_gains_coins_only_for_hero_target():
    state = _rune_sigils_state(runes={1: RuneType.ANVIL}, enemies=[("hero_target", (1, 0, -1))])

    run = _start_rune_sigils(state)
    _pass_sigils_defense(
        run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_target")
    ).finish()

    assert state.get_hero("hero_snorri").gold == 4  # 1 defeat coin + 3 Anvil coins
    assert any(
        event.event_type == GameEventType.GOLD_GAINED and event.metadata["amount"] == 3
        for event in run.events
    )

    minion_state = _rune_sigils_state(
        runes={1: RuneType.ANVIL}, minions=[("blue_minion", (1, 0, -1))]
    )
    _start_rune_sigils(minion_state).expect_input(InputRequestType.SELECT_UNIT).choose(
        "blue_minion"
    ).finish()

    assert minion_state.get_hero("hero_snorri").gold == 2  # defeated-minion reward only


@pytest.mark.effect_flow
def test_rune_sigils_h5_horn_repeats_on_different_enemy_hero():
    state = _rune_sigils_state(
        runes={1: RuneType.HORN},
        enemies=[("hero_first", (1, 0, -1)), ("hero_second", (2, 0, -2))],
    )

    run = _start_rune_sigils(state)
    _pass_sigils_defense(run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_first"))
    run.expect_input(InputRequestType.SELECT_OPTION).choose("YES")
    _pass_sigils_defense(
        run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_second")
    ).finish()

    assert _attack_values(run) == [2, 2]


@pytest.mark.effect_flow
def test_rune_sigils_h8_range_item_extends_bird_and_horn_reach():
    bird_state = _rune_sigils_state(runes={1: RuneType.BIRD}, minions=[("blue_minion", (3, 0, -3))])
    bird_state.get_hero("hero_snorri").items[StatType.RANGE] = 1
    bird_run = _start_rune_sigils(bird_state)
    assert {
        option.id
        for option in bird_run.expect_input(InputRequestType.SELECT_UNIT).latest_request.options
    } == {"blue_minion"}

    horn_state = _rune_sigils_state(
        runes={1: RuneType.HORN},
        enemies=[("hero_first", (1, 0, -1)), ("hero_second", (3, 0, -3))],
    )
    horn_state.get_hero("hero_snorri").items[StatType.RANGE] = 1
    horn_run = _start_rune_sigils(horn_state)
    _pass_sigils_defense(horn_run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_first"))
    horn_run.expect_input(InputRequestType.SELECT_OPTION).choose("NO").finish()


@pytest.mark.effect_flow
def test_rune_sigils_u1_horn_does_not_offer_repeat_without_other_enemy_hero():
    state = _rune_sigils_state(runes={1: RuneType.HORN}, enemies=[("hero_target", (1, 0, -1))])

    run = _start_rune_sigils(state)
    _pass_sigils_defense(
        run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_target")
    ).finish()


@pytest.mark.effect_flow
def test_rune_sigils_u2_bird_can_decline_minion_targeting_and_attack_adjacent_unit():
    state = _rune_sigils_state(
        runes={1: RuneType.BIRD},
        enemies=[("hero_target", (1, 0, -1))],
        minions=[("blue_minion", (2, 0, -2))],
    )

    run = _start_rune_sigils(state)
    run.expect_input(InputRequestType.SELECT_UNIT).skip()
    _pass_sigils_defense(
        run.expect_input(InputRequestType.SELECT_UNIT).choose("hero_target")
    ).finish()

    assert _attack_values(run) == [2]


@pytest.mark.effect_flow
def test_rune_sigils_u3_without_bird_requires_an_adjacent_unit():
    state = _rune_sigils_state(enemies=[("hero_target", (2, 0, -2))])

    _start_rune_sigils(state).finish()


# ---------------------------------------------------------------------------
# sections 18-19: Rune Mastery ultimate
# ---------------------------------------------------------------------------


def _enable_rune_mastery(state: GameState) -> None:
    snorri = state.get_hero("hero_snorri")
    mastery = snorri_card("rune_mastery")
    mastery.state = CardState.PASSIVE
    snorri.ultimate_card = mastery
    snorri.level = 8


@pytest.mark.effect_flow
def test_rune_mastery_h1_adds_second_rune_for_the_action_only():
    state = _passage_state(
        "deep_passage",
        runes={1: RuneType.BIRD, 2: RuneType.AXE, 3: RuneType.ANVIL, 4: RuneType.HORN},
        length=6,
    )
    _enable_rune_mastery(state)

    run = _start_passage(state)
    run.expect_input(InputRequestType.SELECT_OPTION).choose(RuneType.HORN.value)
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 5, "r": 0, "s": -5}).finish()

    assert state.get_position("hero_snorri") == Hex(q=5, r=0, s=-5)


@pytest.mark.effect_flow
def test_rune_mastery_h2_applies_to_defense_reactions():
    state = _oath_state(
        "oath_of_perseverance",
        runes={1: RuneType.HORN, 2: RuneType.BIRD, 3: RuneType.AXE, 4: RuneType.ANVIL},
        attack_color=CardColor.RED,
        is_ranged=True,
    )
    _enable_rune_mastery(state)

    run = _run_oath_attack(state)
    run.expect_input(InputRequestType.SELECT_OPTION).choose(RuneType.BIRD.value)
    run.expect_input(InputRequestType.SELECT_OPTION).choose(RuneType.BIRD.value).finish()

    assert _combat_outcomes(run) == ["BLOCKED"]


@pytest.mark.effect_flow
def test_rune_mastery_u1_without_placed_runes_does_not_prompt():
    state = _passage_state("deep_passage", length=4)
    _enable_rune_mastery(state)

    _start_passage(state).expect_input(InputRequestType.SELECT_HEX).choose(
        {"q": 3, "r": 0, "s": -3}
    ).finish()


@pytest.mark.effect_flow
def test_rune_mastery_u2_is_inert_below_level_eight():
    state = _passage_state("deep_passage", runes={1: RuneType.HORN}, length=4)
    snorri = state.get_hero("hero_snorri")
    mastery = snorri_card("rune_mastery")
    mastery.state = CardState.PASSIVE
    snorri.ultimate_card = mastery

    _start_passage(state).expect_input(InputRequestType.SELECT_HEX).choose(
        {"q": 3, "r": 0, "s": -3}
    ).finish()


@pytest.mark.effect_contract
def test_oath_immunity_belongs_to_the_oath_card():  # one instance per card
    """The Oath's immunity is that card's active effect, like Arien's Duelist."""
    state = _oath_state(
        "oath_of_endurance", runes={1: RuneType.HORN}, attack_color=CardColor.SILVER
    )

    _run_oath_attack(state).finish()

    immunity = next(
        effect
        for effect in state.active_effects
        if effect.effect_type == EffectType.IMMUNITY_ENEMY_ACTIONS
    )
    assert immunity.source_card_id == "oath_of_endurance"

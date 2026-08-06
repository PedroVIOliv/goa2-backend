"""Takahide's gold cycle (TDD §16-§19) and the Ready for War ultimate (§20).

Float / Sting / Strike each swap themselves with a gold card in the deck after
their primary action; Bushido swaps the one gold that is outside the deck. The
incoming gold inherits the outgoing card's exact place — becoming the resolved
turn card for the three golds, and landing FACEDOWN when Bushido pulls it into a
resolved slot or the discard pile (rulebook: a facedown card outside the hand
has no identity).

Pre-ultimate exactly one gold is ever outside the deck. Ready for War ends the
cycle: the silver goes back to the deck, both deck golds come to hand, and the
swap texts fizzle forever after (interp 1).
"""

from __future__ import annotations

import pytest

from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import ActionType, Card, CardColor, CardState, CardTier
from goa2.domain.views import build_view

from ..builders import EffectScenarioBuilder
from ..runner import EffectRun, run_card
from ..takahide_common import deck_card, equip_takahide

TAKAHIDE = "hero_takahide"
ENEMY = "hero_enemy_1"


def shield() -> Card:
    card = Card(
        id="enemy_shield",
        name="Enemy Shield",
        tier=CardTier.I,
        color=CardColor.BLUE,
        initiative=2,
        primary_action=ActionType.SKILL,
        secondary_actions={ActionType.DEFENSE: 12},
        effect_id="",
        effect_text="",
        is_facedown=False,
    )
    card.state = CardState.HAND
    return card


def board(radius: int = 4) -> list[tuple[int, int, int]]:
    return [
        (q, r, -q - r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if max(abs(q), abs(r), abs(-q - r)) <= radius
    ]


def gold_state(card_id: str, *, enemies=((3, 0, -3),)):
    """Takahide resolving `card_id` with his real deck; enemies hold big shields."""
    builder = EffectScenarioBuilder().with_hexes(board()).red_hero(TAKAHIDE, at=(0, 0, 0))
    for i, at in enumerate(enemies, 1):
        builder = builder.blue_hero(f"hero_enemy_{i}", at=at)
    state = builder.with_actor(TAKAHIDE).build()
    equip_takahide(state, card_id)
    for i in range(1, len(enemies) + 1):
        enemy = state.get_hero(f"hero_enemy_{i}")
        card = shield()
        enemy.deck.append(card)
        enemy.hand.append(card)
    return state


def option_ids(run: EffectRun) -> list[str]:
    assert run.latest_request is not None
    return [opt.id for opt in run.latest_request.options]


def strip_deck_golds(state) -> None:
    """Post-ultimate shape: both other golds sit in hand, none in the deck."""
    taka = state.get_hero(TAKAHIDE)
    for card in taka.deck:
        if card.color == CardColor.GOLD and card.state == CardState.DECK:
            card.state = CardState.HAND
            card.is_facedown = False
            taka.hand.append(card)


# ---------------------------------------------------------------------------
# §16 Bushido (silver: swap the out-of-deck gold with a deck gold)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_bushido_h1_h6_gold_in_hand_swaps_faceup_with_no_outgoing_prompt():
    state = gold_state("bushido")
    taka = state.get_hero(TAKAHIDE)

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_CARD)  # H6: straight to the deck-gold pick

    assert set(option_ids(run)) == {"sting_like_a_bee", "strike_like_a_tiger"}
    assert run.latest_request.can_skip is False  # U2: the swap is mandatory
    run.choose("sting_like_a_bee").finish()

    float_card = deck_card(taka, "float_like_a_butterfly")
    sting = deck_card(taka, "sting_like_a_bee")
    assert sting in taka.hand and sting.state == CardState.HAND
    assert sting.is_facedown is False
    assert float_card.state == CardState.DECK and float_card not in taka.hand


@pytest.mark.effect_flow
def test_bushido_h2_gold_in_a_resolved_slot_is_replaced_facedown():
    state = gold_state("bushido")
    taka = state.get_hero(TAKAHIDE)
    float_card = deck_card(taka, "float_like_a_butterfly")
    taka.hand.remove(float_card)
    float_card.state = CardState.RESOLVED
    float_card.is_facedown = False
    float_card.played_this_round = True
    taka.played_cards = [float_card]

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_CARD).choose("strike_like_a_tiger")
    run.finish()

    strike = deck_card(taka, "strike_like_a_tiger")
    assert taka.played_cards[0] is strike
    assert strike.state == CardState.RESOLVED
    assert strike.is_facedown is True
    assert float_card.state == CardState.DECK and float_card.is_facedown is False


@pytest.mark.effect_flow
def test_bushido_h3_gold_in_the_discard_is_replaced_facedown():
    state = gold_state("bushido")
    taka = state.get_hero(TAKAHIDE)
    float_card = deck_card(taka, "float_like_a_butterfly")
    taka.hand.remove(float_card)
    float_card.state = CardState.DISCARD
    float_card.is_facedown = False
    taka.discard_pile = [float_card]

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_CARD).choose("sting_like_a_bee")
    run.finish()

    sting = deck_card(taka, "sting_like_a_bee")
    assert taka.discard_pile == [sting]
    assert sting.state == CardState.DISCARD and sting.is_facedown is True
    assert float_card.state == CardState.DECK


@pytest.mark.effect_flow
def test_bushido_h4_the_facedown_card_is_masked_in_every_view():
    state = gold_state("bushido")
    taka = state.get_hero(TAKAHIDE)
    float_card = deck_card(taka, "float_like_a_butterfly")
    taka.hand.remove(float_card)
    float_card.state = CardState.DISCARD
    float_card.is_facedown = False
    taka.discard_pile = [float_card]

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_CARD).choose("sting_like_a_bee")
    run.finish()

    for viewer in (TAKAHIDE, ENEMY, None):
        view = build_view(state, for_hero_id=viewer)
        hero_view = next(h for h in view["teams"]["RED"]["heroes"] if h["id"] == TAKAHIDE)
        card_view = hero_view["discard_pile"][0]
        assert card_view["is_facedown"] is True
        assert "id" not in card_view


@pytest.mark.effect_flow
def test_bushido_h5_end_of_round_returns_the_facedown_card_faceup_to_hand():
    state = gold_state("bushido")
    taka = state.get_hero(TAKAHIDE)
    float_card = deck_card(taka, "float_like_a_butterfly")
    taka.hand.remove(float_card)
    float_card.state = CardState.DISCARD
    float_card.is_facedown = False
    taka.discard_pile = [float_card]

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_CARD).choose("sting_like_a_bee")
    run.finish()

    taka.retrieve_cards()

    sting = deck_card(taka, "sting_like_a_bee")
    assert sting in taka.hand
    assert sting.state == CardState.HAND and sting.is_facedown is False
    assert deck_card(taka, "float_like_a_butterfly").state == CardState.DECK


# ---------------------------------------------------------------------------
# §17 Float Like a Butterfly (MOVE 5, then swap)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_float_h2_move_then_swap_into_the_resolved_slot():
    state = gold_state("float_like_a_butterfly")
    taka = state.get_hero(TAKAHIDE)

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("MOVEMENT")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 2, "r": 0, "s": -2})
    run.expect_input(InputRequestType.SELECT_CARD).choose("sting_like_a_bee")
    run.finish()

    float_card = deck_card(taka, "float_like_a_butterfly")
    sting = deck_card(taka, "sting_like_a_bee")
    assert state.get_position(TAKAHIDE) == Hex(q=2, r=0, s=-2)
    assert float_card.state == CardState.DECK and float_card.is_facedown is False
    assert sting.state == CardState.RESOLVED and sting.is_facedown is False
    assert taka.played_cards[0] is sting


@pytest.mark.effect_flow
def test_float_h3_a_zero_space_move_still_swaps():
    state = gold_state("float_like_a_butterfly")
    taka = state.get_hero(TAKAHIDE)

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("MOVEMENT")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 0, "r": 0, "s": 0})
    run.expect_input(InputRequestType.SELECT_CARD).choose("strike_like_a_tiger")
    run.finish()

    assert state.get_position(TAKAHIDE) == Hex(q=0, r=0, s=0)
    assert deck_card(taka, "float_like_a_butterfly").state == CardState.DECK
    assert taka.played_cards[0] is deck_card(taka, "strike_like_a_tiger")


@pytest.mark.effect_flow
def test_float_h4_the_swapped_in_gold_returns_to_hand_at_end_of_round():
    state = gold_state("float_like_a_butterfly")
    taka = state.get_hero(TAKAHIDE)

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("MOVEMENT")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 1, "r": 0, "s": -1})
    run.expect_input(InputRequestType.SELECT_CARD).choose("sting_like_a_bee")
    run.finish()

    taka.retrieve_cards()

    assert deck_card(taka, "sting_like_a_bee") in taka.hand
    assert deck_card(taka, "float_like_a_butterfly").state == CardState.DECK


@pytest.mark.effect_flow
def test_float_u2_only_deck_golds_are_offered():
    state = gold_state("float_like_a_butterfly")

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("MOVEMENT")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 1, "r": 0, "s": -1})
    run.expect_input(InputRequestType.SELECT_CARD)

    assert set(option_ids(run)) == {"sting_like_a_bee", "strike_like_a_tiger"}


@pytest.mark.effect_flow
def test_float_u1_without_deck_golds_the_swap_fizzles():
    state = gold_state("float_like_a_butterfly")
    strip_deck_golds(state)
    taka = state.get_hero(TAKAHIDE)

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("MOVEMENT")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 1, "r": 0, "s": -1})
    run.finish()  # no swap prompt

    float_card = deck_card(taka, "float_like_a_butterfly")
    assert float_card.state == CardState.RESOLVED
    assert taka.played_cards[0] is float_card


# ---------------------------------------------------------------------------
# §18 Sting Like a Bee (ranged 3, ATK 5, target at MAXIMUM range)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_sting_h2_only_units_at_exactly_maximum_range_are_targetable():
    state = gold_state("sting_like_a_bee", enemies=[(3, 0, -3), (2, 0, -2)])

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT)

    assert option_ids(run) == ["hero_enemy_1"]  # the one at range 3, not the one at 2


@pytest.mark.effect_flow
def test_sting_h3_h4_swap_fires_after_a_defended_attack():
    state = gold_state("sting_like_a_bee")
    taka = state.get_hero(TAKAHIDE)

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("enemy_shield")
    run.expect_input(InputRequestType.SELECT_CARD).choose("strike_like_a_tiger")
    run.finish()

    sting = deck_card(taka, "sting_like_a_bee")
    strike = deck_card(taka, "strike_like_a_tiger")
    assert sting.state == CardState.DECK  # H3: back to the deck
    assert taka.played_cards[0] is strike
    assert strike.state == CardState.RESOLVED and strike.is_facedown is False


@pytest.mark.effect_flow
def test_sting_u1_no_target_at_max_range_hides_attack_without_a_swap():
    state = gold_state("sting_like_a_bee", enemies=[(1, 0, -1)])
    taka = state.get_hero(TAKAHIDE)

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).expect_option_absent("ATTACK")

    sting = deck_card(taka, "sting_like_a_bee")
    assert sting.state == CardState.UNRESOLVED
    assert taka.current_turn_card is sting
    assert deck_card(taka, "strike_like_a_tiger").state == CardState.DECK


@pytest.mark.effect_flow
def test_sting_u2_post_ultimate_the_swap_fizzles():
    state = gold_state("sting_like_a_bee")
    strip_deck_golds(state)
    taka = state.get_hero(TAKAHIDE)

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("enemy_shield")
    run.finish()  # no swap prompt

    sting = deck_card(taka, "sting_like_a_bee")
    assert sting.state == CardState.RESOLVED
    assert taka.played_cards[0] is sting


# ---------------------------------------------------------------------------
# §19 Strike Like a Tiger (adjacent, ATK 7)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_strike_h2_adjacent_attack_then_swap():
    state = gold_state("strike_like_a_tiger", enemies=[(1, 0, -1)])
    taka = state.get_hero(TAKAHIDE)

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("enemy_shield")
    run.expect_input(InputRequestType.SELECT_CARD).choose("sting_like_a_bee")
    run.finish()

    strike = deck_card(taka, "strike_like_a_tiger")
    sting = deck_card(taka, "sting_like_a_bee")
    assert strike.state == CardState.DECK
    assert taka.played_cards[0] is sting
    assert sting.state == CardState.RESOLVED


@pytest.mark.effect_flow
def test_strike_u1_no_adjacent_target_hides_attack_without_a_swap():
    state = gold_state("strike_like_a_tiger", enemies=[(3, 0, -3)])
    taka = state.get_hero(TAKAHIDE)

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).expect_option_absent("ATTACK")

    strike = deck_card(taka, "strike_like_a_tiger")
    assert strike.state == CardState.UNRESOLVED
    assert deck_card(taka, "sting_like_a_bee").state == CardState.DECK


# ---------------------------------------------------------------------------
# §20 Ready for War (one-shot at level 8)
# ---------------------------------------------------------------------------


def ultimate_effect():
    from goa2.engine.effects import CardEffectRegistry

    effect = CardEffectRegistry.get("ready_for_war")
    assert effect is not None
    return effect


def unlocked_state(silver_in: str = "hand"):
    """Takahide one round into the game, about to unlock his ultimate."""
    state = gold_state("come_to_aid")
    taka = state.get_hero(TAKAHIDE)
    taka.current_turn_card = None
    come_to_aid = deck_card(taka, "come_to_aid")
    come_to_aid.state = CardState.HAND
    come_to_aid.is_facedown = False
    taka.hand.append(come_to_aid)

    bushido = deck_card(taka, "bushido")
    if silver_in != "hand":
        taka.hand.remove(bushido)
        if silver_in == "discard":
            bushido.state = CardState.DISCARD
            taka.discard_pile.append(bushido)
        elif silver_in == "played":
            bushido.state = CardState.RESOLVED
            bushido.played_this_round = True
            taka.played_cards = [bushido]
    return state, taka


@pytest.mark.effect_contract
def test_ready_for_war_h1_silver_to_deck_and_both_golds_to_hand():
    state, taka = unlocked_state()

    ultimate_effect().on_ultimate_unlocked(state, taka)

    bushido = deck_card(taka, "bushido")
    assert bushido.state == CardState.DECK and bushido not in taka.hand
    hand_ids = {c.id for c in taka.hand}
    assert {"sting_like_a_bee", "strike_like_a_tiger", "float_like_a_butterfly"} <= hand_ids
    assert len(taka.hand) == 6  # 3 golds + 3 tier-I cards
    assert not [c for c in taka.deck if c.color == CardColor.GOLD and c.state == CardState.DECK]


@pytest.mark.effect_contract
def test_ready_for_war_h2_silver_returns_from_the_discard():
    state, taka = unlocked_state(silver_in="discard")

    ultimate_effect().on_ultimate_unlocked(state, taka)

    bushido = deck_card(taka, "bushido")
    assert bushido.state == CardState.DECK
    assert bushido not in taka.discard_pile
    assert len(taka.hand) == 6


@pytest.mark.effect_contract
def test_ready_for_war_h3_silver_returns_from_a_resolved_slot():
    state, taka = unlocked_state(silver_in="played")

    ultimate_effect().on_ultimate_unlocked(state, taka)

    bushido = deck_card(taka, "bushido")
    assert bushido.state == CardState.DECK
    assert taka.played_cards[0] is None  # the slot is emptied
    assert len(taka.hand) == 6


@pytest.mark.effect_contract
def test_ready_for_war_h4_the_golds_that_move_are_the_ones_in_the_deck():
    """Which golds sit in the deck varies with prior swaps, so the hook reads
    state rather than card identities: with Float in the discard and Sting in
    hand, only Strike (the one DECK gold) comes to hand."""
    state, taka = unlocked_state()
    float_card = deck_card(taka, "float_like_a_butterfly")
    sting = deck_card(taka, "sting_like_a_bee")
    taka.hand.remove(float_card)
    float_card.state = CardState.DISCARD
    taka.discard_pile.append(float_card)
    sting.state = CardState.HAND
    sting.is_facedown = False
    taka.hand.append(sting)

    ultimate_effect().on_ultimate_unlocked(state, taka)

    strike = deck_card(taka, "strike_like_a_tiger")
    assert strike in taka.hand  # the only DECK gold moved
    assert float_card.state == CardState.DISCARD  # untouched: it was not in the deck
    assert deck_card(taka, "bushido").state == CardState.DECK


@pytest.mark.effect_contract
def test_ready_for_war_h5_emits_public_events():
    from goa2.domain.events import GameEventType

    state, taka = unlocked_state()

    events = ultimate_effect().on_ultimate_unlocked(state, taka)

    types = [e.event_type for e in events]
    assert GameEventType.DECK_CARD_SWAPPED in types
    assert types.count(GameEventType.CARD_RETRIEVED) == 2
    assert all(e.actor_id == TAKAHIDE for e in events)


@pytest.mark.effect_contract
def test_ready_for_war_h6_end_of_round_retrieve_keeps_the_silver_in_the_deck():
    state, taka = unlocked_state()

    ultimate_effect().on_ultimate_unlocked(state, taka)
    taka.retrieve_cards()

    assert deck_card(taka, "bushido").state == CardState.DECK
    assert len(taka.hand) == 6


@pytest.mark.effect_contract
def test_ready_for_war_u1_is_idempotent():
    state, taka = unlocked_state()

    ultimate_effect().on_ultimate_unlocked(state, taka)
    hand_before = [c.id for c in taka.hand]
    events = ultimate_effect().on_ultimate_unlocked(state, taka)

    assert events == []
    assert [c.id for c in taka.hand] == hand_before


@pytest.mark.effect_flow
def test_ready_for_war_h7_post_ultimate_float_resolves_without_a_swap():
    state = gold_state("float_like_a_butterfly")
    taka = state.get_hero(TAKAHIDE)
    # Simulate the unlock with Float already committed as the turn card.
    ultimate_effect().on_ultimate_unlocked(state, taka)

    run = run_card(state, TAKAHIDE, finalize_turn=True)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("MOVEMENT")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 1, "r": 0, "s": -1})
    run.finish()  # no card-swap prompt

    float_card = deck_card(taka, "float_like_a_butterfly")
    assert float_card.state == CardState.RESOLVED
    assert taka.played_cards[0] is float_card


@pytest.mark.effect_flow
def test_ready_for_war_fires_through_the_level_up_path():
    from goa2.engine.handler import process_stack, push_steps
    from goa2.engine.steps import EndPhaseStep

    state, taka = unlocked_state()
    taka.gold = 28  # cumulative cost of levels 2-8

    push_steps(state, [EndPhaseStep()])
    process_stack(state)

    assert taka.level == 8
    assert deck_card(taka, "bushido").state == CardState.DECK
    assert deck_card(taka, "sting_like_a_bee") in taka.hand
    assert deck_card(taka, "strike_like_a_tiger") in taka.hand

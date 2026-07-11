"""P2: SwapWithDeckCardStep — exchange a card in play with a card in the deck."""

import pytest

from goa2.domain.models import ActionType, Card, CardColor, CardState, CardTier, Hero
from goa2.domain.models.effect import (
    ActiveEffect,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.state import GameState
from goa2.engine.steps import SwapWithDeckCardStep
from tests.engine.effects.builders import EffectScenarioBuilder

HERO_ID = "hero_swapper"


def gold(card_id: str, initiative: int = 5) -> Card:
    return Card(
        id=card_id,
        name=card_id.replace("_", " ").title(),
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=initiative,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        secondary_actions={},
        effect_id=card_id,
        effect_text="",
        is_facedown=False,
    )


def make_state() -> tuple[GameState, Hero]:
    """A hero whose master deck is gold_a/gold_b/gold_c, all currently in DECK."""
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero(HERO_ID, at=(0, 0, 0))
        .with_actor(HERO_ID)
        .build()
    )
    hero = state.get_hero(HERO_ID)
    assert hero is not None
    hero.deck = [gold("gold_a", 5), gold("gold_b", 6), gold("gold_c", 7)]
    for card in hero.deck:
        card.state = CardState.DECK
    return state, hero


def find(hero: Hero, card_id: str) -> Card:
    return next(c for c in hero.deck if c.id == card_id)


def put_in_hand(hero: Hero, card_id: str) -> Card:
    card = find(hero, card_id)
    card.state = CardState.HAND
    card.is_facedown = False
    hero.hand.append(card)
    return card


def put_in_discard(hero: Hero, card_id: str) -> Card:
    card = find(hero, card_id)
    card.state = CardState.DISCARD
    card.is_facedown = False
    hero.discard_pile.append(card)
    return card


def put_in_slot(hero: Hero, card_id: str, index: int = 0) -> Card:
    card = find(hero, card_id)
    card.state = CardState.RESOLVED
    card.is_facedown = False
    card.played_this_round = True
    while len(hero.played_cards) <= index:
        hero.played_cards.append(None)
    hero.played_cards[index] = card
    return card


def put_as_turn_card(hero: Hero, card_id: str) -> Card:
    card = find(hero, card_id)
    card.state = CardState.UNRESOLVED
    card.is_facedown = False
    card.played_this_round = True
    hero.current_turn_card = card
    return card


def run_swap(state: GameState, hero: Hero, outgoing: str, incoming: str, **kwargs):
    state.execution_context["deck_swap_card"] = incoming
    step = SwapWithDeckCardStep(hero_id=str(hero.id), outgoing_card_id=outgoing, **kwargs)
    return step.resolve(state, state.execution_context)


def test_swap_from_hand_keeps_incoming_faceup_in_hand():
    state, hero = make_state()
    put_in_hand(hero, "gold_a")

    result = run_swap(state, hero, "gold_a", "gold_b")

    assert result.is_finished
    gold_a, gold_b = find(hero, "gold_a"), find(hero, "gold_b")
    assert gold_b in hero.hand and gold_b.state == CardState.HAND
    assert gold_b.is_facedown is False
    assert gold_a not in hero.hand and gold_a.state == CardState.DECK
    assert gold_a.is_facedown is False


def test_swap_from_discard_places_incoming_facedown():
    state, hero = make_state()
    put_in_discard(hero, "gold_a")

    result = run_swap(state, hero, "gold_a", "gold_b", facedown_if_from_discard_or_resolved=True)

    assert result.is_finished
    gold_a, gold_b = find(hero, "gold_a"), find(hero, "gold_b")
    assert gold_b in hero.discard_pile and gold_b.state == CardState.DISCARD
    assert gold_b.is_facedown is True
    assert gold_a not in hero.discard_pile and gold_a.state == CardState.DECK
    assert gold_a.is_facedown is False


def test_swap_from_resolved_slot_keeps_slot_index_and_goes_facedown():
    state, hero = make_state()
    put_in_slot(hero, "gold_c", index=1)

    run_swap(state, hero, "gold_c", "gold_b", facedown_if_from_discard_or_resolved=True)

    gold_b, gold_c = find(hero, "gold_b"), find(hero, "gold_c")
    assert hero.played_cards[1] is gold_b
    assert gold_b.state == CardState.RESOLVED and gold_b.is_facedown is True
    assert gold_b.played_this_round is True
    assert gold_c not in hero.played_cards
    assert gold_c.state == CardState.DECK and gold_c.played_this_round is False


def test_swap_of_turn_card_installs_incoming_faceup():
    state, hero = make_state()
    put_as_turn_card(hero, "gold_a")

    run_swap(state, hero, "gold_a", "gold_c", facedown_if_from_discard_or_resolved=True)

    gold_a, gold_c = find(hero, "gold_a"), find(hero, "gold_c")
    assert hero.current_turn_card is gold_c
    assert gold_c.state == CardState.UNRESOLVED
    assert gold_c.is_facedown is False  # rider only fires for discard/resolved
    assert gold_a.state == CardState.DECK


def test_hand_swap_ignores_the_facedown_rider():
    state, hero = make_state()
    put_in_hand(hero, "gold_a")

    run_swap(state, hero, "gold_a", "gold_b", facedown_if_from_discard_or_resolved=True)

    assert find(hero, "gold_b").is_facedown is False


def test_swap_emits_event_with_both_card_ids():
    state, hero = make_state()
    put_in_hand(hero, "gold_a")

    result = run_swap(state, hero, "gold_a", "gold_b")

    assert len(result.events) == 1
    event = result.events[0]
    assert event.metadata["outgoing_card_id"] == "gold_a"
    assert event.metadata["incoming_card_id"] == "gold_b"
    assert event.actor_id == HERO_ID


def test_swap_expires_active_effects_of_both_cards():
    state, hero = make_state()
    put_in_hand(hero, "gold_a")
    for card_id in ("gold_a", "gold_b"):
        state.active_effects.append(
            ActiveEffect(
                id=f"fx_{card_id}",
                source_id=HERO_ID,
                source_card_id=card_id,
                effect_type=EffectType.LOS_BLOCKER,
                scope=EffectScope(shape=Shape.GLOBAL),
                duration=DurationType.THIS_ROUND,
                created_at_turn=state.turn,
                created_at_round=state.round,
                is_active=True,
            )
        )

    run_swap(state, hero, "gold_a", "gold_b")

    assert all(not e.is_active for e in state.active_effects)


def test_missing_incoming_card_is_a_clean_noop():
    state, hero = make_state()
    put_in_hand(hero, "gold_a")

    step = SwapWithDeckCardStep(hero_id=HERO_ID, outgoing_card_id="gold_a")
    result = step.resolve(state, state.execution_context)

    assert result.is_finished and not result.events
    assert find(hero, "gold_a").state == CardState.HAND


def test_incoming_card_not_in_deck_state_is_a_clean_noop():
    state, hero = make_state()
    put_in_hand(hero, "gold_a")
    put_in_hand(hero, "gold_b")  # gold_b is in HAND, not DECK

    result = run_swap(state, hero, "gold_a", "gold_b")

    assert result.is_finished and not result.events
    assert find(hero, "gold_a").state == CardState.HAND
    assert find(hero, "gold_b").state == CardState.HAND


def test_unknown_outgoing_card_is_a_clean_noop():
    state, hero = make_state()

    result = run_swap(state, hero, "gold_a", "gold_b")  # gold_a is in the deck, not in play

    assert result.is_finished and not result.events
    assert find(hero, "gold_b").state == CardState.DECK


def test_outgoing_card_resolved_from_context_key():
    state, hero = make_state()
    put_in_hand(hero, "gold_a")
    state.execution_context["out_card"] = "gold_a"
    state.execution_context["deck_swap_card"] = "gold_c"

    step = SwapWithDeckCardStep(hero_key="who", outgoing_card_key="out_card")
    state.execution_context["who"] = HERO_ID
    step.resolve(state, state.execution_context)

    assert find(hero, "gold_c") in hero.hand
    assert find(hero, "gold_a").state == CardState.DECK


@pytest.mark.parametrize("gate", ["active_if_key", "skip_if_key"])
def test_step_honors_conditional_gates(gate):
    state, hero = make_state()
    put_in_hand(hero, "gold_a")
    state.execution_context["deck_swap_card"] = "gold_b"
    kwargs = {gate: "flag"}
    if gate == "skip_if_key":
        state.execution_context["flag"] = True

    step = SwapWithDeckCardStep(hero_id=HERO_ID, outgoing_card_id="gold_a", **kwargs)
    result = step.resolve(state, state.execution_context)

    assert result.is_finished and not result.events
    assert find(hero, "gold_a").state == CardState.HAND

"""Takahide's unresolved-card swap family (TDD §11-§13).

"Target a unit adjacent to you. After the attack: A friendly hero in radius may
swap their unresolved card with a card in their hand[, or in their discard]."

All committed cards are faceup during Resolution (revealed at Revelation), so
the swap is public: the incoming card becomes the ally's faceup UNRESOLVED turn
card and the outgoing card lands in their hand (or discard, Hold My Saké).
Initiative is dynamic — the engine re-sorts before every action (interp 10).
"""

from __future__ import annotations

import pytest

from goa2.domain.input import InputRequestType
from goa2.domain.models import ActionType, Card, CardColor, CardState, CardTier
from goa2.engine.phases import resolve_next_action

from ..runner import EffectRun, run_card
from ..takahide_common import TAKAHIDE, takahide_state

ALLY = "hero_ally_1"
ALLY_2 = "hero_ally_2"
ENEMY = "hero_enemy_1"


def a_card(card_id: str, *, initiative: int = 5) -> Card:
    return Card(
        id=card_id,
        name=card_id.replace("_", " ").title(),
        tier=CardTier.I,
        color=CardColor.GREEN,
        initiative=initiative,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        effect_id="",
        effect_text="",
        is_facedown=False,
    )


def board(radius: int = 4) -> list[tuple[int, int, int]]:
    return [
        (q, r, -q - r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if max(abs(q), abs(r), abs(-q - r)) <= radius
    ]


def swap_state(card_id: str, *, allies=((2, 0, -2),), enemy_at=(1, 0, -1)):
    """Takahide with an ADJACENT enemy (so the attack has a legal target)."""
    return takahide_state(card_id, allies=list(allies), enemies=[enemy_at], hexes=board())


def commit(state, hero_id: str, card: Card) -> Card:
    """Give the hero a faceup UNRESOLVED turn card and mark them unresolved."""
    hero = state.get_hero(hero_id)
    assert hero is not None
    card.state = CardState.UNRESOLVED
    card.is_facedown = False
    card.played_this_round = True
    hero.deck.append(card)
    hero.current_turn_card = card
    if hero_id not in state.unresolved_hero_ids:
        state.unresolved_hero_ids.append(hero_id)
    return card


def give_hand(state, hero_id: str, *cards: Card) -> None:
    hero = state.get_hero(hero_id)
    assert hero is not None
    for card in cards:
        card.state = CardState.HAND
        card.is_facedown = False
        hero.deck.append(card)
        hero.hand.append(card)


def give_discard(state, hero_id: str, *cards: Card) -> None:
    hero = state.get_hero(hero_id)
    assert hero is not None
    for card in cards:
        card.state = CardState.DISCARD
        card.is_facedown = False
        hero.deck.append(card)
        hero.discard_pile.append(card)


def option_ids(run: EffectRun) -> list[str]:
    assert run.latest_request is not None
    return [opt.id for opt in run.latest_request.options]


# ---------------------------------------------------------------------------
# §11 Set an Example (ATK 2, radius 3)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_set_an_example_h1_ally_swaps_turn_card_with_a_hand_card():
    state = swap_state("set_an_example")
    turn_card = commit(state, ALLY, a_card("ally_turn", initiative=4))
    give_hand(state, ALLY, a_card("ally_spare", initiative=9))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)  # attack target
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")  # no defense
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)  # swap partner
    run.expect_input(InputRequestType.SELECT_CARD)
    assert run.latest_request.player_id == ALLY  # the ALLY chooses the card
    run.choose("ally_spare").finish()

    ally = state.get_hero(ALLY)
    assert ally.current_turn_card.id == "ally_spare"
    assert ally.current_turn_card.state == CardState.UNRESOLVED
    assert ally.current_turn_card.is_facedown is False
    assert turn_card in ally.hand
    assert turn_card.state == CardState.HAND


@pytest.mark.effect_flow
def test_set_an_example_h2_swapped_in_initiative_decides_who_acts_next():
    state = swap_state("set_an_example", allies=[(2, 0, -2), (0, 2, -2)])
    commit(state, ALLY, a_card("ally_turn", initiative=4))
    commit(state, ALLY_2, a_card("ally2_turn", initiative=8))
    give_hand(state, ALLY, a_card("ally_fast", initiative=12))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_fast")
    run.finish()

    resolve_next_action(state)
    assert state.current_actor_id == ALLY  # initiative 12 > 8


@pytest.mark.effect_flow
def test_set_an_example_h2b_swapping_in_a_slower_card_yields_the_turn():
    state = swap_state("set_an_example", allies=[(2, 0, -2), (0, 2, -2)])
    commit(state, ALLY, a_card("ally_turn", initiative=10))
    commit(state, ALLY_2, a_card("ally2_turn", initiative=8))
    give_hand(state, ALLY, a_card("ally_slow", initiative=3))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_slow")
    run.finish()

    resolve_next_action(state)
    assert state.current_actor_id == ALLY_2  # 8 > 3


@pytest.mark.effect_flow
def test_set_an_example_h3_rider_fires_even_when_the_attack_is_defended():
    state = swap_state("set_an_example")
    commit(state, ALLY, a_card("ally_turn"))
    give_hand(state, ALLY, a_card("ally_spare"))
    enemy = state.get_hero(ENEMY)
    shield = a_card("enemy_shield")
    shield.secondary_actions = {ActionType.DEFENSE: 9}
    enemy.deck.append(shield)
    shield.state = CardState.HAND
    enemy.hand.append(shield)

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    # The defender is offered a defense reaction; blocking must not skip the rider.
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("enemy_shield")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_spare")
    run.finish()

    assert state.get_hero(ALLY).current_turn_card.id == "ally_spare"


@pytest.mark.effect_flow
def test_set_an_example_h4_takahide_may_decline_the_rider():
    state = swap_state("set_an_example")
    commit(state, ALLY, a_card("ally_turn"))
    give_hand(state, ALLY, a_card("ally_spare"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.expect_input(InputRequestType.SELECT_UNIT).skip()
    run.finish()

    assert state.get_hero(ALLY).current_turn_card.id == "ally_turn"


@pytest.mark.effect_flow
def test_set_an_example_h4b_ally_may_decline_the_card_choice():
    state = swap_state("set_an_example")
    commit(state, ALLY, a_card("ally_turn"))
    give_hand(state, ALLY, a_card("ally_spare"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).skip()
    run.finish()

    assert state.get_hero(ALLY).current_turn_card.id == "ally_turn"


@pytest.mark.effect_flow
def test_set_an_example_u1_no_adjacent_target_aborts_before_the_rider():
    state = swap_state("set_an_example", enemy_at=(4, 0, -4))
    commit(state, ALLY, a_card("ally_turn"))
    give_hand(state, ALLY, a_card("ally_spare"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.finish()  # mandatory targeting fails → action aborts

    assert state.get_hero(ALLY).current_turn_card.id == "ally_turn"


@pytest.mark.effect_flow
def test_set_an_example_u2_no_ally_with_an_unresolved_card_fizzles():
    state = swap_state("set_an_example")
    give_hand(state, ALLY, a_card("ally_spare"))  # ally already acted: no turn card
    state.unresolved_hero_ids = []

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.finish()  # no swap prompt

    assert state.get_hero(ALLY).current_turn_card is None


@pytest.mark.effect_flow
def test_set_an_example_u3_ally_with_an_empty_hand_offers_no_swap():
    state = swap_state("set_an_example")
    commit(state, ALLY, a_card("ally_turn"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.finish()  # optional card select has no candidates → skipped

    assert state.get_hero(ALLY).current_turn_card.id == "ally_turn"


@pytest.mark.effect_flow
def test_set_an_example_u4_u5_only_unresolved_allies_are_eligible():
    """Heroes who already resolved are out (U4); Takahide is never eligible (U5)."""
    state = swap_state("set_an_example", allies=[(2, 0, -2), (0, 2, -2)])
    commit(state, ALLY, a_card("ally_turn"))
    give_hand(state, ALLY, a_card("ally_spare"))
    give_hand(state, ALLY_2, a_card("ally2_spare"))  # ALLY_2 has no unresolved card
    state.unresolved_hero_ids = [ALLY]

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.expect_input(InputRequestType.SELECT_UNIT)

    assert option_ids(run) == [ALLY]


# ---------------------------------------------------------------------------
# §12 Lead from the Front (ATK 3, radius 4)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_lead_from_the_front_h1_full_flow_at_radius_four():
    state = swap_state("lead_from_the_front", allies=[(0, 4, -4)])
    commit(state, ALLY, a_card("ally_turn"))
    give_hand(state, ALLY, a_card("ally_spare"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_spare")
    run.finish()

    assert state.get_hero(ALLY).current_turn_card.id == "ally_spare"


# ---------------------------------------------------------------------------
# §13 Hold My Saké (ATK 3, radius 4, hand OR discard)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_hold_my_sake_h1_swap_with_a_discarded_card():
    state = swap_state("hold_my_sake")
    turn_card = commit(state, ALLY, a_card("ally_turn"))
    give_discard(state, ALLY, a_card("ally_dumped", initiative=11))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_dumped")
    run.finish()

    ally = state.get_hero(ALLY)
    assert ally.current_turn_card.id == "ally_dumped"
    assert ally.current_turn_card.state == CardState.UNRESOLVED
    assert ally.current_turn_card.is_facedown is False
    assert turn_card in ally.discard_pile
    assert turn_card.state == CardState.DISCARD
    assert turn_card.is_facedown is False


@pytest.mark.effect_flow
def test_hold_my_sake_h2_offers_hand_and_discard_together():
    state = swap_state("hold_my_sake")
    commit(state, ALLY, a_card("ally_turn"))
    give_hand(state, ALLY, a_card("ally_spare"))
    give_discard(state, ALLY, a_card("ally_dumped"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD)

    assert set(option_ids(run)) == {"ally_spare", "ally_dumped"}


@pytest.mark.effect_flow
def test_hold_my_sake_u1_empty_hand_and_discard_means_no_swap():
    state = swap_state("hold_my_sake")
    commit(state, ALLY, a_card("ally_turn"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.finish()

    assert state.get_hero(ALLY).current_turn_card.id == "ally_turn"


@pytest.mark.effect_flow
def test_hold_my_sake_u2_facedown_discard_cards_are_not_offered():
    state = swap_state("hold_my_sake")
    commit(state, ALLY, a_card("ally_turn"))
    hidden = a_card("ally_hidden")
    give_discard(state, ALLY, hidden, a_card("ally_dumped"))
    hidden.is_facedown = True

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD)

    assert option_ids(run) == ["ally_dumped"]

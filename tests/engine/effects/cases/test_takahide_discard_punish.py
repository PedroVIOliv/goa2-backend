"""Takahide's color-discard punish family (TDD §8-§10).

"Choose a card in the discard of a friendly hero in radius. An enemy hero in
radius discards a card of the same color, if able."

Takahide picks both the color source (S4: his own discard is never eligible,
interp 8) and the victim(s), blind to their hand (interp 9). "If able" resolves
engine-side: no matching color in hand → no-op, the pick is spent.

The victim select is OPTIONAL (Snorri Runetrap precedent): a mandatory select
with no candidates would abort the whole action, which would contradict §8 U3
("color chosen but nothing happens").
"""

from __future__ import annotations

import pytest

from goa2.domain.input import InputRequestType
from goa2.domain.models import ActionType, Card, CardColor, CardState, CardTier
from goa2.domain.models.effect import (
    ActiveEffect,
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)

from ..runner import EffectRun, run_card
from ..takahide_common import TAKAHIDE, takahide_state

ALLY = "hero_ally_1"
ENEMY = "hero_enemy_1"
ENEMY_2 = "hero_enemy_2"


def colored(card_id: str, color: CardColor) -> Card:
    tier = CardTier.UNTIERED if color in (CardColor.GOLD, CardColor.SILVER) else CardTier.I
    return Card(
        id=card_id,
        name=card_id.replace("_", " ").title(),
        tier=tier,
        color=color,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=2,
        secondary_actions={},
        effect_id="",
        effect_text="",
        is_facedown=False,
    )


def give_hand(state, hero_id: str, *cards: Card) -> None:
    hero = state.get_hero(hero_id)
    assert hero is not None
    for card in cards:
        card.state = CardState.HAND
        hero.deck.append(card)
        hero.hand.append(card)


def give_discard(state, hero_id: str, *cards: Card) -> None:
    hero = state.get_hero(hero_id)
    assert hero is not None
    for card in cards:
        card.state = CardState.DISCARD
        hero.deck.append(card)
        hero.discard_pile.append(card)


def give_played(state, hero_id: str, *cards: Card) -> None:
    hero = state.get_hero(hero_id)
    assert hero is not None
    for card in cards:
        card.state = CardState.RESOLVED
        card.is_facedown = False
        hero.deck.append(card)
        hero.played_cards.append(card)


def board(radius: int = 4) -> list[tuple[int, int, int]]:
    return [
        (q, r, -q - r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if max(abs(q), abs(r), abs(-q - r)) <= radius
    ]


def punish_state(card_id: str, *, ally_at=(2, 0, -2), enemies=((0, 2, -2),)):
    return takahide_state(card_id, allies=[ally_at], enemies=list(enemies), hexes=board())


def option_ids(run: EffectRun) -> list[str]:
    assert run.latest_request is not None
    return [opt.id for opt in run.latest_request.options]


def make_immune(state, hero_id: str) -> None:
    state.active_effects.append(
        ActiveEffect(
            id=f"immune_{hero_id}",
            source_id=hero_id,
            effect_type=EffectType.IMMUNITY_ENEMY_ACTIONS,
            scope=EffectScope(shape=Shape.POINT, origin_id=hero_id, affects=AffectsFilter.SELF),
            duration=DurationType.THIS_TURN,
            created_at_turn=state.turn,
            created_at_round=state.round,
            is_active=True,
        )
    )


# ---------------------------------------------------------------------------
# §8 Proven Warrior (radius 3)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_proven_warrior_h1_enemy_discards_a_card_of_the_chosen_color():
    state = punish_state("proven_warrior")
    give_discard(state, ALLY, colored("ally_red", CardColor.RED))
    give_hand(
        state, ENEMY, colored("enemy_red", CardColor.RED), colored("enemy_blue", CardColor.BLUE)
    )

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)  # discard owner
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_red")  # color source
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)  # victim
    run.expect_input(InputRequestType.SELECT_CARD)
    assert run.latest_request.player_id == ENEMY  # the victim picks which card
    run.choose("enemy_red").finish()

    enemy = state.get_hero(ENEMY)
    assert [c.id for c in enemy.discard_pile] == ["enemy_red"]
    assert [c.id for c in enemy.hand] == ["enemy_blue"]


@pytest.mark.effect_flow
def test_proven_warrior_h2_gold_color_source_forces_a_gold_discard():
    state = punish_state("proven_warrior")
    give_discard(state, ALLY, colored("ally_gold", CardColor.GOLD))
    give_hand(
        state, ENEMY, colored("enemy_gold", CardColor.GOLD), colored("enemy_red", CardColor.RED)
    )

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_gold")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD)

    assert option_ids(run) == ["enemy_gold"]
    run.choose("enemy_gold").finish()
    assert [c.id for c in state.get_hero(ENEMY).discard_pile] == ["enemy_gold"]


@pytest.mark.effect_flow
def test_proven_warrior_h3_victim_chooses_among_matching_cards():
    state = punish_state("proven_warrior")
    give_discard(state, ALLY, colored("ally_red", CardColor.RED))
    give_hand(
        state, ENEMY, colored("enemy_red1", CardColor.RED), colored("enemy_red2", CardColor.RED)
    )

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_red")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD)

    assert set(option_ids(run)) == {"enemy_red1", "enemy_red2"}
    run.choose("enemy_red2").finish()
    assert [c.id for c in state.get_hero(ENEMY).discard_pile] == ["enemy_red2"]


@pytest.mark.effect_flow
def test_proven_warrior_u1_victim_without_the_color_is_a_spent_pick():
    state = punish_state("proven_warrior")
    give_discard(state, ALLY, colored("ally_red", CardColor.RED))
    give_hand(state, ENEMY, colored("enemy_blue", CardColor.BLUE))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_red")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.finish()  # no discard prompt

    enemy = state.get_hero(ENEMY)
    assert enemy.discard_pile == []
    assert [c.id for c in enemy.hand] == ["enemy_blue"]


@pytest.mark.effect_flow
def test_proven_warrior_u2_no_friendly_discard_fizzles():
    state = punish_state("proven_warrior")
    give_hand(state, ENEMY, colored("enemy_red", CardColor.RED))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).expect_option_absent("SKILL")

    assert state.get_hero(ENEMY).discard_pile == []


@pytest.mark.effect_flow
def test_proven_warrior_u3_no_enemy_in_radius_still_resolves_cleanly():
    state = punish_state("proven_warrior", enemies=[(4, 0, -4)])  # radius 3 < distance 4
    give_discard(state, ALLY, colored("ally_red", CardColor.RED))
    give_hand(state, ENEMY, colored("enemy_red", CardColor.RED))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_red")
    run.finish()  # no victim prompt, no abort

    assert state.get_hero(ENEMY).discard_pile == []


@pytest.mark.effect_flow
def test_proven_warrior_u4_takahide_is_not_a_color_source():
    state = punish_state("proven_warrior")
    give_discard(state, ALLY, colored("ally_red", CardColor.RED))
    give_discard(state, TAKAHIDE, colored("taka_blue", CardColor.BLUE))
    give_hand(state, ENEMY, colored("enemy_red", CardColor.RED))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT)

    assert option_ids(run) == [ALLY]


@pytest.mark.effect_flow
def test_proven_warrior_u5_facedown_discard_is_not_a_color_source():
    state = punish_state("proven_warrior")
    faceup = colored("ally_red", CardColor.RED)
    hidden = colored("ally_hidden", CardColor.BLUE)
    give_discard(state, ALLY, faceup, hidden)
    hidden.is_facedown = True
    give_hand(state, ENEMY, colored("enemy_red", CardColor.RED))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD)

    assert option_ids(run) == ["ally_red"]


@pytest.mark.effect_flow
def test_proven_warrior_u5b_ally_with_only_facedown_discards_is_not_selectable():
    state = punish_state("proven_warrior")
    hidden = colored("ally_hidden", CardColor.BLUE)
    give_discard(state, ALLY, hidden)
    hidden.is_facedown = True

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).expect_option_absent("SKILL")


@pytest.mark.effect_flow
def test_proven_warrior_u6_immune_enemy_heroes_are_not_selectable():
    state = punish_state("proven_warrior", enemies=[(0, 2, -2), (2, 1, -3)])
    give_discard(state, ALLY, colored("ally_red", CardColor.RED))
    give_hand(state, ENEMY, colored("enemy_red", CardColor.RED))
    give_hand(state, ENEMY_2, colored("enemy2_red", CardColor.RED))
    make_immune(state, ENEMY)

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_red")
    run.expect_input(InputRequestType.SELECT_UNIT)

    assert option_ids(run) == [ENEMY_2]


@pytest.mark.effect_flow
def test_proven_warrior_u7_only_the_victims_hand_counts():
    state = punish_state("proven_warrior")
    give_discard(state, ALLY, colored("ally_red", CardColor.RED))
    give_played(state, ENEMY, colored("enemy_red_played", CardColor.RED))
    give_hand(state, ENEMY, colored("enemy_blue", CardColor.BLUE))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_red")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.finish()

    enemy = state.get_hero(ENEMY)
    assert enemy.discard_pile == []
    assert [c.id for c in enemy.played_cards] == ["enemy_red_played"]


# ---------------------------------------------------------------------------
# §9 Chosen Champion (radius 4)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_chosen_champion_h1_full_flow_at_radius_four():
    state = punish_state("chosen_champion", ally_at=(4, 0, -4), enemies=[(0, 4, -4)])
    give_discard(state, ALLY, colored("ally_green", CardColor.GREEN))
    give_hand(state, ENEMY, colored("enemy_green", CardColor.GREEN))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_green")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("enemy_green")
    run.finish()

    assert [c.id for c in state.get_hero(ENEMY).discard_pile] == ["enemy_green"]


# ---------------------------------------------------------------------------
# §10 The Right Hand (radius 4, up to two victims)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_the_right_hand_h1_two_enemies_each_discard_a_matching_card():
    state = punish_state("the_right_hand", enemies=[(0, 2, -2), (2, 1, -3)])
    give_discard(state, ALLY, colored("ally_red", CardColor.RED))
    give_hand(state, ENEMY, colored("e1_red", CardColor.RED))
    give_hand(state, ENEMY_2, colored("e2_red", CardColor.RED))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_red")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("e1_red")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY_2)
    run.expect_input(InputRequestType.SELECT_CARD).choose("e2_red")
    run.finish()

    assert [c.id for c in state.get_hero(ENEMY).discard_pile] == ["e1_red"]
    assert [c.id for c in state.get_hero(ENEMY_2).discard_pile] == ["e2_red"]


@pytest.mark.effect_flow
def test_the_right_hand_h2_takahide_may_stop_after_one_victim():
    state = punish_state("the_right_hand", enemies=[(0, 2, -2), (2, 1, -3)])
    give_discard(state, ALLY, colored("ally_red", CardColor.RED))
    give_hand(state, ENEMY, colored("e1_red", CardColor.RED))
    give_hand(state, ENEMY_2, colored("e2_red", CardColor.RED))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_red")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("e1_red")
    run.expect_input(InputRequestType.SELECT_UNIT).skip()
    run.finish()

    assert [c.id for c in state.get_hero(ENEMY).discard_pile] == ["e1_red"]
    assert state.get_hero(ENEMY_2).discard_pile == []


@pytest.mark.effect_flow
def test_the_right_hand_h2b_takahide_may_pick_no_victim_at_all():
    state = punish_state("the_right_hand", enemies=[(0, 2, -2)])
    give_discard(state, ALLY, colored("ally_red", CardColor.RED))
    give_hand(state, ENEMY, colored("e1_red", CardColor.RED))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_red")
    run.expect_input(InputRequestType.SELECT_UNIT).skip()
    run.finish()

    assert state.get_hero(ENEMY).discard_pile == []


@pytest.mark.effect_flow
def test_the_right_hand_u1_the_same_enemy_cannot_be_picked_twice():
    state = punish_state("the_right_hand", enemies=[(0, 2, -2), (2, 1, -3)])
    give_discard(state, ALLY, colored("ally_red", CardColor.RED))
    give_hand(state, ENEMY, colored("e1_red", CardColor.RED))
    give_hand(state, ENEMY_2, colored("e2_red", CardColor.RED))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_red")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("e1_red")
    run.expect_input(InputRequestType.SELECT_UNIT)

    assert option_ids(run) == [ENEMY_2]


@pytest.mark.effect_flow
def test_the_right_hand_u2_second_victim_without_the_color_no_ops():
    state = punish_state("the_right_hand", enemies=[(0, 2, -2), (2, 1, -3)])
    give_discard(state, ALLY, colored("ally_red", CardColor.RED))
    give_hand(state, ENEMY, colored("e1_red", CardColor.RED))
    give_hand(state, ENEMY_2, colored("e2_blue", CardColor.BLUE))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_red")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("e1_red")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ENEMY_2)
    run.finish()

    assert [c.id for c in state.get_hero(ENEMY).discard_pile] == ["e1_red"]
    assert state.get_hero(ENEMY_2).discard_pile == []
    assert [c.id for c in state.get_hero(ENEMY_2).hand] == ["e2_blue"]

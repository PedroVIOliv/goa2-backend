"""Takahide's discard-support families (TDD §1-§7).

Every card here runs the same gate: Takahide picks a friendly hero in
range/radius, that hero MAY discard a card (their own decision), and the
benefit fires when that hero has a card in the discard afterwards — including
a pre-existing one (interp 5).

Range/radius uses the engine's topology service (RangeFilter). Topology
distance is cube distance plus reality-split awareness; obstacles do not
lengthen it, so the "topology" paths below assert range bounds, not walls.
"""

from __future__ import annotations

import pytest

from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import ActionType, Card, CardColor, CardState, CardTier

from ..runner import EffectRun, run_card
from ..takahide_common import TAKAHIDE, takahide_state

ALLY = "hero_ally_1"


def _card(card_id: str, *, action: ActionType = ActionType.SKILL, value: int | None = None) -> Card:
    return Card(
        id=card_id,
        name=card_id.replace("_", " ").title(),
        tier=CardTier.I,
        color=CardColor.GREEN,
        initiative=5,
        primary_action=action,
        primary_action_value=value,
        secondary_actions={},
        effect_id="",
        effect_text="",
        is_facedown=False,
    )


def attack_card(card_id: str) -> Card:
    return _card(card_id, action=ActionType.ATTACK, value=2)


def give_hand(state, hero_id: str, *cards: Card) -> list[Card]:
    hero = state.get_hero(hero_id)
    assert hero is not None
    for card in cards:
        card.state = CardState.HAND
        hero.deck.append(card)
        hero.hand.append(card)
    return list(cards)


def give_discard(state, hero_id: str, *cards: Card) -> list[Card]:
    hero = state.get_hero(hero_id)
    assert hero is not None
    for card in cards:
        card.state = CardState.DISCARD
        card.is_facedown = False
        hero.deck.append(card)
        hero.discard_pile.append(card)
    return list(cards)


def discard_from_hand(state, hero_id: str, card_id: str, *, facedown: bool = False) -> Card:
    """Move a card the hero already owns from their hand to their discard pile."""
    hero = state.get_hero(hero_id)
    assert hero is not None
    card = next(c for c in hero.hand if c.id == card_id)
    hero.hand.remove(card)
    card.state = CardState.DISCARD
    card.is_facedown = facedown
    hero.discard_pile.append(card)
    return card


def board(radius: int = 4) -> list[tuple[int, int, int]]:
    return [
        (q, r, -q - r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if max(abs(q), abs(r), abs(-q - r)) <= radius
    ]


def support_state(card_id: str, *, ally_at=(2, 0, -2), enemy_at=(-4, 0, 4), **kwargs):
    return takahide_state(
        card_id,
        allies=[ally_at],
        enemies=[enemy_at],
        hexes=board(),
        **kwargs,
    )


def option_ids(run: EffectRun) -> list[str]:
    assert run.latest_request is not None
    return [opt.id for opt in run.latest_request.options]


def offered_hexes(run: EffectRun) -> set[Hex]:
    assert run.latest_request is not None
    return {Hex(**opt.metadata["hex"]) for opt in run.latest_request.options}


def make_terrain(state, *coords: tuple[int, int, int]) -> None:
    for q, r, s in coords:
        state.board.tiles[Hex(q=q, r=r, s=s)].is_terrain = True


# ---------------------------------------------------------------------------
# §1 Come to Aid (range 3, "you may move up to 3")
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_come_to_aid_h1_ally_discards_then_takahide_moves():
    state = support_state("come_to_aid")
    give_hand(state, ALLY, _card("ally_a"), _card("ally_b"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_a")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 1, "r": 1, "s": -2})
    run.finish()

    ally = state.get_hero(ALLY)
    assert [c.id for c in ally.discard_pile] == ["ally_a"]
    assert state.get_position(TAKAHIDE) == Hex(q=1, r=1, s=-2)


@pytest.mark.effect_flow
def test_come_to_aid_h4_discard_prompt_is_routed_to_the_ally():
    state = support_state("come_to_aid")
    give_hand(state, ALLY, _card("ally_a"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD)

    assert run.latest_request.player_id == ALLY
    assert run.latest_request.can_skip is True


@pytest.mark.effect_flow
def test_come_to_aid_h2_decline_with_preexisting_discard_still_moves():
    state = support_state("come_to_aid")
    give_hand(state, ALLY, _card("ally_a"))
    give_discard(state, ALLY, _card("old_card"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).skip()
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 1, "r": 1, "s": -2})
    run.finish()

    ally = state.get_hero(ALLY)
    assert [c.id for c in ally.discard_pile] == ["old_card"]
    assert state.get_position(TAKAHIDE) == Hex(q=1, r=1, s=-2)


@pytest.mark.effect_flow
def test_come_to_aid_h3_move_is_optional_and_capped_at_three():
    state = support_state("come_to_aid")
    give_hand(state, ALLY, _card("ally_a"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_a")
    run.expect_input(InputRequestType.SELECT_HEX)

    hexes = offered_hexes(run)
    assert run.latest_request.can_skip is True
    assert Hex(q=0, r=3, s=-3) in hexes  # exactly 3 spaces
    assert Hex(q=0, r=4, s=-4) not in hexes  # 4 spaces is too far

    run.skip().finish()
    assert state.get_position(TAKAHIDE) == Hex(q=0, r=0, s=0)


@pytest.mark.effect_flow
def test_come_to_aid_u1_no_ally_in_range_fizzles():
    state = takahide_state("come_to_aid", allies=[], enemies=[(4, 0, -4)], hexes=board())

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).expect_option_absent("SKILL")

    assert state.get_position(TAKAHIDE) == Hex(q=0, r=0, s=0)


@pytest.mark.effect_flow
def test_come_to_aid_u2_decline_with_empty_discard_grants_no_move():
    state = support_state("come_to_aid")
    give_hand(state, ALLY, _card("ally_a"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).skip()
    run.finish()

    assert state.get_position(TAKAHIDE) == Hex(q=0, r=0, s=0)


@pytest.mark.effect_flow
def test_come_to_aid_u3_ally_with_empty_hand_and_discard_gets_no_prompt():
    state = support_state("come_to_aid")

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.finish()  # no discard prompt, no move prompt

    assert state.get_position(TAKAHIDE) == Hex(q=0, r=0, s=0)


@pytest.mark.effect_flow
def test_come_to_aid_u4_ally_beyond_topology_range_is_not_selectable():
    state = support_state("come_to_aid", ally_at=(4, 0, -4))  # topology distance 4 > range 3
    give_hand(state, ALLY, _card("ally_a"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).expect_option_absent("SKILL")


@pytest.mark.effect_flow
def test_come_to_aid_u5_takahide_is_never_the_friendly_hero():
    state = support_state("come_to_aid")
    give_hand(state, ALLY, _card("ally_a"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT)

    assert option_ids(run) == [ALLY]


@pytest.mark.effect_flow
def test_come_to_aid_enemy_heroes_are_not_selectable():
    state = support_state("come_to_aid")
    give_hand(state, ALLY, _card("ally_a"))
    give_hand(state, "hero_enemy_1", _card("enemy_a"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT)

    assert "hero_enemy_1" not in option_ids(run)


# ---------------------------------------------------------------------------
# §2 Bring the Relief (range 4, move 4)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_bring_the_relief_h1_range_four_and_move_four():
    state = support_state("bring_the_relief", ally_at=(4, 0, -4))
    give_hand(state, ALLY, _card("ally_a"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_a")
    run.expect_input(InputRequestType.SELECT_HEX)

    hexes = offered_hexes(run)
    assert Hex(q=0, r=4, s=-4) in hexes  # exactly 4 spaces away
    assert Hex(q=0, r=-1, s=1) in hexes

    run.choose({"q": 0, "r": 4, "s": -4}).finish()
    assert state.get_position(TAKAHIDE) == Hex(q=0, r=4, s=-4)


@pytest.mark.effect_flow
def test_bring_the_relief_u1_destinations_beyond_four_are_not_offered():
    state = support_state("bring_the_relief", ally_at=(4, 0, -4))
    give_hand(state, ALLY, _card("ally_a"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_a")
    run.expect_input(InputRequestType.SELECT_HEX)

    assert all(Hex(q=0, r=0, s=0).distance(h) <= 4 for h in offered_hexes(run))


# ---------------------------------------------------------------------------
# §3 Commit Reserves (range 4, move 4 ignoring obstacles)
# ---------------------------------------------------------------------------

RING = [(1, 0, -1), (1, -1, 0), (0, -1, 1), (-1, 0, 1), (-1, 1, 0), (0, 1, -1)]


@pytest.mark.effect_flow
def test_commit_reserves_h1_move_paths_through_obstacles():
    state = support_state("commit_reserves", ally_at=(3, 0, -3))
    give_hand(state, ALLY, _card("ally_a"))
    make_terrain(state, *RING)  # Takahide is walled in

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_a")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 2, "r": 0, "s": -2})
    run.finish()

    assert state.get_position(TAKAHIDE) == Hex(q=2, r=0, s=-2)


@pytest.mark.effect_flow
def test_commit_reserves_u1_obstacle_and_occupied_hexes_are_not_landing_spots():
    state = support_state("commit_reserves", ally_at=(3, 0, -3))
    give_hand(state, ALLY, _card("ally_a"))
    make_terrain(state, *RING)

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_a")
    run.expect_input(InputRequestType.SELECT_HEX)

    hexes = offered_hexes(run)
    assert Hex(q=1, r=0, s=-1) not in hexes  # terrain
    assert Hex(q=3, r=0, s=-3) not in hexes  # occupied by the ally


@pytest.mark.effect_flow
def test_commit_reserves_u2_without_the_condition_no_move():
    state = support_state("commit_reserves", ally_at=(3, 0, -3))
    give_hand(state, ALLY, _card("ally_a"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).skip()
    run.finish()

    assert state.get_position(TAKAHIDE) == Hex(q=0, r=0, s=0)


@pytest.mark.effect_flow
def test_come_to_aid_cannot_path_through_obstacles():
    """The non-'ignoring obstacles' version cannot leave a walled-in Takahide."""
    state = support_state("come_to_aid", ally_at=(3, 0, -3))
    give_hand(state, ALLY, _card("ally_a"))
    make_terrain(state, *RING)

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_a")
    run.finish()  # no reachable destination → optional move skipped

    assert state.get_position(TAKAHIDE) == Hex(q=0, r=0, s=0)


# ---------------------------------------------------------------------------
# §4 Pledge of Allegiance (range 4, 1 coin each + retrieve)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_pledge_h1_coins_for_both_then_takahide_retrieves():
    state = support_state("pledge_of_allegiance")
    give_hand(state, ALLY, _card("ally_a"))
    discard_from_hand(state, TAKAHIDE, "proven_warrior")
    taka, ally = state.get_hero(TAKAHIDE), state.get_hero(ALLY)

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_a")
    run.expect_input(InputRequestType.SELECT_CARD)
    assert run.latest_request.player_id == TAKAHIDE  # Takahide's own discard
    run.choose("proven_warrior").finish()

    assert taka.gold == 1
    assert ally.gold == 1
    assert "proven_warrior" in [c.id for c in taka.hand]
    assert taka.discard_pile == []


@pytest.mark.effect_flow
def test_pledge_h2_decline_with_preexisting_discard_still_pays_and_retrieves():
    state = support_state("pledge_of_allegiance")
    give_hand(state, ALLY, _card("ally_a"))
    give_discard(state, ALLY, _card("old_card"))
    discard_from_hand(state, TAKAHIDE, "proven_warrior")

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).skip()
    run.expect_input(InputRequestType.SELECT_CARD).choose("proven_warrior")
    run.finish()

    assert state.get_hero(TAKAHIDE).gold == 1
    assert state.get_hero(ALLY).gold == 1
    assert "proven_warrior" in [c.id for c in state.get_hero(TAKAHIDE).hand]


@pytest.mark.effect_flow
def test_pledge_h3_retrieve_declined_leaves_only_the_coins():
    state = support_state("pledge_of_allegiance")
    give_hand(state, ALLY, _card("ally_a"))
    discard_from_hand(state, TAKAHIDE, "proven_warrior")

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_a")
    run.expect_input(InputRequestType.SELECT_CARD).skip()
    run.finish()

    taka = state.get_hero(TAKAHIDE)
    assert taka.gold == 1
    assert [c.id for c in taka.discard_pile] == ["proven_warrior"]


@pytest.mark.effect_flow
def test_pledge_h4_facedown_own_discard_card_is_retrievable_and_turns_faceup():
    state = support_state("pledge_of_allegiance")
    give_hand(state, ALLY, _card("ally_a"))
    hidden = discard_from_hand(state, TAKAHIDE, "proven_warrior", facedown=True)

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_a")
    run.expect_input(InputRequestType.SELECT_CARD)
    assert "proven_warrior" in option_ids(run)
    run.choose("proven_warrior").finish()

    assert hidden in state.get_hero(TAKAHIDE).hand
    assert hidden.is_facedown is False


@pytest.mark.effect_flow
def test_pledge_u1_condition_unmet_pays_nothing():
    state = support_state("pledge_of_allegiance")
    give_hand(state, ALLY, _card("ally_a"))
    discard_from_hand(state, TAKAHIDE, "proven_warrior")

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).skip()
    run.finish()

    taka = state.get_hero(TAKAHIDE)
    assert taka.gold == 0
    assert state.get_hero(ALLY).gold == 0
    assert [c.id for c in taka.discard_pile] == ["proven_warrior"]


@pytest.mark.effect_flow
def test_pledge_u2_empty_own_discard_pays_coins_without_a_retrieve_prompt():
    state = support_state("pledge_of_allegiance")
    give_hand(state, ALLY, _card("ally_a"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_a")
    run.finish()  # no retrieve prompt

    assert state.get_hero(TAKAHIDE).gold == 1
    assert state.get_hero(ALLY).gold == 1


@pytest.mark.effect_flow
def test_pledge_u3_allys_discarded_card_is_not_retrievable():
    state = support_state("pledge_of_allegiance")
    give_hand(state, ALLY, _card("ally_a"))
    discard_from_hand(state, TAKAHIDE, "proven_warrior")

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_a")
    run.expect_input(InputRequestType.SELECT_CARD)

    assert option_ids(run) == ["proven_warrior"]  # the ally's card is in THEIR discard


# ---------------------------------------------------------------------------
# §5 Loyal Retainer (range 4, 2 coins each + retrieve)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_loyal_retainer_h1_pays_two_coins_each_and_retrieves():
    state = support_state("loyal_retainer", ally_at=(4, 0, -4))
    give_hand(state, ALLY, _card("ally_a"))
    discard_from_hand(state, TAKAHIDE, "come_to_aid")

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_a")
    run.expect_input(InputRequestType.SELECT_CARD).choose("come_to_aid")
    run.finish()

    assert state.get_hero(TAKAHIDE).gold == 2
    assert state.get_hero(ALLY).gold == 2
    assert "come_to_aid" in [c.id for c in state.get_hero(TAKAHIDE).hand]


# ---------------------------------------------------------------------------
# §6 Calculated Risk (radius 4, ally may move up to 2)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_calculated_risk_h1_ally_discards_an_attack_card_then_moves_itself():
    state = support_state("calculated_risk")
    give_hand(state, ALLY, attack_card("ally_axe"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_axe")
    run.expect_input(InputRequestType.SELECT_HEX)

    assert run.latest_request.player_id == ALLY  # the ALLY picks their destination
    run.choose({"q": 3, "r": 0, "s": -3}).finish()

    assert state.get_position(ALLY) == Hex(q=3, r=0, s=-3)
    assert state.get_position(TAKAHIDE) == Hex(q=0, r=0, s=0)
    assert [c.id for c in state.get_hero(ALLY).discard_pile] == ["ally_axe"]


@pytest.mark.effect_flow
def test_calculated_risk_h2_preexisting_discard_of_any_card_enables_the_move():
    state = support_state("calculated_risk")
    give_discard(state, ALLY, _card("old_skill"))  # not an attack card

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 3, "r": 0, "s": -3})
    run.finish()

    assert state.get_position(ALLY) == Hex(q=3, r=0, s=-3)


@pytest.mark.effect_flow
def test_calculated_risk_h3_only_attack_primary_cards_are_offered():
    state = support_state("calculated_risk")
    give_hand(state, ALLY, attack_card("ally_axe"), _card("ally_skill"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD)

    assert option_ids(run) == ["ally_axe"]


@pytest.mark.effect_flow
def test_calculated_risk_u1_no_attack_card_and_empty_discard_means_nothing_happens():
    state = support_state("calculated_risk")
    give_hand(state, ALLY, _card("ally_skill"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.finish()  # no discard prompt (no attack card), no move

    assert state.get_position(ALLY) == Hex(q=2, r=0, s=-2)
    assert state.get_hero(ALLY).discard_pile == []


@pytest.mark.effect_flow
def test_calculated_risk_u2_ally_may_decline_the_move():
    state = support_state("calculated_risk")
    give_hand(state, ALLY, attack_card("ally_axe"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_axe")
    run.expect_input(InputRequestType.SELECT_HEX).skip()
    run.finish()

    assert state.get_position(ALLY) == Hex(q=2, r=0, s=-2)


@pytest.mark.effect_flow
def test_calculated_risk_u3_no_ally_in_radius_fizzles():
    state = takahide_state("calculated_risk", allies=[], enemies=[(4, 0, -4)], hexes=board())

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).expect_option_absent("SKILL")


@pytest.mark.effect_flow
def test_calculated_risk_move_is_capped_at_two_spaces():
    state = support_state("calculated_risk")
    give_hand(state, ALLY, attack_card("ally_axe"))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_axe")
    run.expect_input(InputRequestType.SELECT_HEX)

    hexes = offered_hexes(run)
    ally_hex = Hex(q=2, r=0, s=-2)
    assert Hex(q=4, r=0, s=-4) in hexes  # exactly 2 from the ally
    assert all(ally_hex.distance(h) <= 2 for h in hexes)


# ---------------------------------------------------------------------------
# §7 Tactical Gambit (radius 4, ally moves 2 ignoring obstacles)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_tactical_gambit_h1_ally_paths_through_an_obstacle():
    state = support_state("tactical_gambit")
    give_hand(state, ALLY, attack_card("ally_axe"))
    # Wall the ally (at 2,0,-2) in completely.
    make_terrain(state, (3, 0, -3), (3, -1, -2), (2, -1, -1), (1, 0, -1), (1, 1, -2), (2, 1, -3))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_axe")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 4, "r": 0, "s": -4})
    run.finish()

    assert state.get_position(ALLY) == Hex(q=4, r=0, s=-4)


@pytest.mark.effect_flow
def test_tactical_gambit_u1_obstacle_destinations_are_still_illegal():
    state = support_state("tactical_gambit")
    give_hand(state, ALLY, attack_card("ally_axe"))
    make_terrain(state, (3, 0, -3), (3, -1, -2), (2, -1, -1), (1, 0, -1), (1, 1, -2), (2, 1, -3))

    run = run_card(state, TAKAHIDE)
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose(ALLY)
    run.expect_input(InputRequestType.SELECT_CARD).choose("ally_axe")
    run.expect_input(InputRequestType.SELECT_HEX)

    hexes = offered_hexes(run)
    assert Hex(q=3, r=0, s=-3) not in hexes  # terrain
    assert Hex(q=0, r=0, s=0) not in hexes  # occupied by Takahide

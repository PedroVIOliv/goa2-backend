"""Wuk effect flow tests."""

from __future__ import annotations

import pytest

import goa2.data.heroes.wuk
import goa2.scripts.wuk_effects  # noqa: F401  (register effects)
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import MinionType, Token, TokenType
from goa2.domain.models.effect import EffectType
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import EndPhaseStep

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _add_tree(state: GameState, token_id: str, at: Hex) -> None:
    tree = Token(id=BoardEntityID(token_id), name="Tree", token_type=TokenType.TREE)
    state.register_entity(tree, "token")
    state.place_entity(token_id, at)


def _add_tree_pool(state: GameState, count: int = 3) -> None:
    """Register `count` unplaced Tree tokens into the supply pool."""
    state.token_pool[TokenType.TREE] = []
    for i in range(count):
        tree = Token(id=BoardEntityID(f"tree_pool_{i}"), name="Tree", token_type=TokenType.TREE)
        state.register_entity(tree, "token")
        state.token_pool[TokenType.TREE].append(tree)


def _placed_trees(state: GameState) -> list[str]:
    return [
        str(t.id)
        for t in state.token_pool.get(TokenType.TREE, [])
        if BoardEntityID(str(t.id)) in state.entity_locations
    ]


def _wuk_at_origin(card_id: str) -> EffectScenarioBuilder:
    return (
        EffectScenarioBuilder()
        .line_board(5)
        .red_hero("hero_wuk", at=(0, 0, 0), current_card=hero_card("Wuk", card_id))
        .with_actor("hero_wuk")
    )


@pytest.mark.effect_flow
def test_toss_away_throws_adjacent_enemy_into_range() -> None:
    state = _wuk_at_origin("toss_away").blue_minion("blue_minion", at=(1, 0, -1)).build()

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("blue_minion")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=3, r=0, s=-3))
    run.finish()

    assert state.entity_locations["blue_minion"] == Hex(q=3, r=0, s=-3)


@pytest.mark.effect_flow
def test_toss_away_throws_tree_token() -> None:
    state = _wuk_at_origin("toss_away").build()
    _add_tree(state, "tree_1", Hex(q=1, r=0, s=-1))

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("tree_1")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=2, r=0, s=-2))
    run.finish()

    assert state.entity_locations["tree_1"] == Hex(q=2, r=0, s=-2)


@pytest.mark.effect_flow
def test_monstrous_throw_repeats_on_second_target() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero("hero_wuk", at=(0, 0, 0), current_card=hero_card("Wuk", "monstrous_throw"))
        .with_actor("hero_wuk")
        .blue_minion("m1", at=(1, 0, -1))
        .blue_minion("m2", at=(0, 1, -1))
        .build()
    )

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    # First throw
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("m1")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=4, r=0, s=-4))
    # Repeat -> yes, second throw
    run.expect_input(InputRequestType.SELECT_OPTION).choose("YES")
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("m2")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=3, r=0, s=-3))
    run.finish()

    assert state.entity_locations["m1"] == Hex(q=4, r=0, s=-4)
    assert state.entity_locations["m2"] == Hex(q=3, r=0, s=-3)


@pytest.mark.effect_flow
def test_into_the_canopy_swap_self_with_tree() -> None:
    state = _wuk_at_origin("into_the_canopy").build()
    _add_tree(state, "tree_1", Hex(q=2, r=0, s=-2))

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("tree_1")
    run.finish()

    assert state.entity_locations["hero_wuk"] == Hex(q=2, r=0, s=-2)
    assert state.entity_locations["tree_1"] == Hex(q=0, r=0, s=0)


@pytest.mark.effect_flow
def test_into_the_canopy_swap_friendly_with_tree() -> None:
    state = _wuk_at_origin("into_the_canopy").red_minion("ally", at=(1, 0, -1)).build()
    _add_tree(state, "tree_1", Hex(q=2, r=0, s=-2))

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("ally")
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("tree_1")
    run.finish()

    assert state.entity_locations["ally"] == Hex(q=2, r=0, s=-2)
    assert state.entity_locations["tree_1"] == Hex(q=1, r=0, s=-1)


@pytest.mark.effect_flow
def test_treetop_ride_swaps_twice() -> None:
    state = _wuk_at_origin("treetop_ride").build()
    _add_tree(state, "tree_1", Hex(q=1, r=0, s=-1))
    _add_tree(state, "tree_2", Hex(q=2, r=0, s=-2))

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("YES")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("tree_1")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("YES")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("tree_2")
    run.finish()

    assert state.entity_locations["hero_wuk"] == Hex(q=2, r=0, s=-2)
    assert state.entity_locations["tree_2"] == Hex(q=1, r=0, s=-1)
    assert state.entity_locations["tree_1"] == Hex(q=0, r=0, s=0)


def _exclusion_effects(state: GameState):
    return [e for e in state.active_effects if e.effect_type == EffectType.MINION_BATTLE_EXCLUSION]


@pytest.mark.effect_flow
def test_claim_dominance_creates_exclusion_cap_1() -> None:
    state = _wuk_at_origin("claim_dominance").build()
    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.finish()

    effects = _exclusion_effects(state)
    assert len(effects) == 1
    assert effects[0].max_value == 1
    assert effects[0].source_id == "hero_wuk"
    assert effects[0].is_active is True


@pytest.mark.effect_flow
def test_assert_dominance_creates_exclusion_cap_2() -> None:
    state = _wuk_at_origin("assert_dominance").build()
    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.finish()

    effects = _exclusion_effects(state)
    assert len(effects) == 1
    assert effects[0].max_value == 2


@pytest.mark.effect_flow
def test_claim_dominance_excludes_minion_in_real_end_phase_battle() -> None:
    # Wuk (RED) in the active battle zone, adjacent to one BLUE minion.
    # Zone counts: RED 1 minion, BLUE 1 minion -> without dominance the battle
    # is a tie (nobody removed). Claim Dominance makes the adjacent BLUE minion
    # not count -> BLUE 0 -> BLUE loses its minion. This drives the REAL
    # EndPhaseStep (THIS_ROUND expiry + lazy minion battle), so it catches the
    # effect expiring before the battle.
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (0, 1, -1), (2, 0, -2)])
        .red_hero("hero_wuk", at=(0, 0, 0), current_card=hero_card("Wuk", "claim_dominance"))
        .with_actor("hero_wuk")
        .red_minion("r1", at=(2, 0, -2))
        .blue_minion("b1", at=(1, 0, -1))  # adjacent to Wuk, in the zone
        .build()
    )
    state.active_zone_id = "z1"

    # Play the card (creates the exclusion effect).
    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.finish()

    # Resolve the real End Phase (battle included).
    push_steps(state, [EndPhaseStep()])
    result = process_stack(state)
    assert result.input_request is None  # auto-resolves (no choice needed)

    # BLUE minion excluded -> BLUE loses it; RED minion survives.
    assert state.entity_locations.get("b1") is None
    assert state.entity_locations.get("r1") is not None
    # And the exclusion effect is cleaned up by end-of-round (no leak into next round).
    assert not _exclusion_effects(state)


@pytest.mark.effect_flow
def test_gifts_of_nature_removes_tree_and_retrieves() -> None:
    state = _wuk_at_origin("gifts_of_nature").build()
    _add_tree(state, "tree_1", Hex(q=2, r=0, s=-2))
    wuk = state.get_hero("hero_wuk")
    discarded = hero_card("Wuk", "tree_slam")
    wuk.discard_pile = [discarded]

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("tree_1")
    run.expect_input(InputRequestType.SELECT_CARD).choose("tree_slam")
    run.finish()

    assert state.entity_locations.get("tree_1") is None  # tree removed (cost)
    assert discarded in wuk.hand
    assert discarded not in wuk.discard_pile


@pytest.mark.effect_flow
def test_gifts_of_nature_requires_tree_in_radius() -> None:
    # No tree in radius -> mandatory tree select aborts; nothing retrieved.
    state = _wuk_at_origin("gifts_of_nature").build()
    wuk = state.get_hero("hero_wuk")
    discarded = hero_card("Wuk", "tree_slam")
    wuk.discard_pile = [discarded]

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.finish()

    assert discarded in wuk.discard_pile  # not retrieved (no tree to remove)


@pytest.mark.effect_flow
def test_tree_of_plenty_friendly_hero_retrieves() -> None:
    state = _wuk_at_origin("tree_of_plenty").red_hero("ally", at=(1, 0, -1)).build()
    _add_tree(state, "tree_1", Hex(q=2, r=0, s=-2))
    ally = state.get_hero("ally")
    ally_card = hero_card("Wuk", "trample")
    ally.discard_pile = [ally_card]

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("tree_1")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("ally")
    run.expect_input(InputRequestType.SELECT_CARD).choose("trample")
    run.finish()

    assert ally_card in ally.hand
    assert ally_card not in ally.discard_pile


@pytest.mark.effect_flow
def test_abundance_retrieves_both_self_and_friendly() -> None:
    state = _wuk_at_origin("abundance").red_hero("ally", at=(1, 0, -1)).build()
    _add_tree(state, "tree_1", Hex(q=2, r=0, s=-2))
    wuk = state.get_hero("hero_wuk")
    self_card = hero_card("Wuk", "tree_slam")
    wuk.discard_pile = [self_card]
    ally = state.get_hero("ally")
    ally_card = hero_card("Wuk", "trample")
    ally.discard_pile = [ally_card]

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("tree_1")
    run.expect_input(InputRequestType.SELECT_CARD).choose("tree_slam")  # self
    run.expect_input(InputRequestType.SELECT_UNIT).choose("ally")
    run.expect_input(InputRequestType.SELECT_CARD).choose("trample")  # friendly
    run.finish()

    assert self_card in wuk.hand
    assert ally_card in ally.hand


@pytest.mark.effect_flow
def test_natures_protector_mode2_targets_unit_adjacent_to_tree() -> None:
    # Enemy minion at range 2, with a tree adjacent to it (not adjacent to Wuk-as-melee).
    state = _wuk_at_origin("natures_protector").blue_minion("victim", at=(2, 0, -2)).build()
    _add_tree(state, "tree_1", Hex(q=3, r=0, s=-3))  # adjacent to victim

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("victim")
    run.finish()

    # value-2 minion takes 5 -> defeated/removed
    assert state.entity_locations.get("victim") is None


@pytest.mark.effect_flow
def test_natures_protector_mode2_requires_tree_adjacent() -> None:
    # Same enemy at range 2 but NO tree adjacent -> not a valid mode-2 target.
    state = _wuk_at_origin("natures_protector").blue_minion("victim", at=(2, 0, -2)).build()

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)
    # mandatory select with no valid target -> aborts; victim survives
    run.finish()
    assert state.entity_locations.get("victim") == Hex(q=2, r=0, s=-2)


@pytest.mark.effect_flow
def test_natures_protector_mode1_targets_adjacent_hero() -> None:
    state = _wuk_at_origin("natures_protector").blue_hero("enemy", at=(1, 0, -1)).build()

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy")
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.finish()

    combat = [e for e in run.events if e.event_type.value == "COMBAT_RESOLVED"]
    assert combat


@pytest.mark.effect_flow
def test_natures_champion_attacks_both_targets() -> None:
    state = (
        _wuk_at_origin("natures_champion")
        .blue_hero("enemy", at=(1, 0, -1))
        .blue_minion("victim", at=(2, 0, -2))
        .build()
    )
    _add_tree(state, "tree_1", Hex(q=3, r=0, s=-3))  # adjacent to victim

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)  # hero first
    # mode 1: adjacent hero (optional)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy")
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    # mode 2: unit in range adjacent to tree (different target)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("victim")
    run.finish()

    assert state.entity_locations.get("victim") is None  # 6 dmg defeats value-2 minion
    combat = [e for e in run.events if e.event_type.value == "COMBAT_RESOLVED"]
    assert len(combat) >= 2


@pytest.mark.effect_flow
def test_natures_champion_can_attack_tree_unit_before_hero() -> None:
    """ "In any order": the tree-anchored attack (mode 2) may resolve before the
    adjacent-hero attack (mode 1)."""
    state = (
        _wuk_at_origin("natures_champion")
        .blue_hero("enemy", at=(1, 0, -1))
        .blue_minion("victim", at=(2, 0, -2))
        .build()
    )
    _add_tree(state, "tree_1", Hex(q=3, r=0, s=-3))  # adjacent to victim

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)  # tree unit first
    # mode 2: unit in range adjacent to tree
    run.expect_input(InputRequestType.SELECT_UNIT).choose("victim")
    # mode 1: adjacent enemy hero (different target)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy")
    run.expect_input(InputRequestType.SELECT_CARD_OR_PASS).choose("PASS")
    run.finish()

    assert state.entity_locations.get("victim") is None  # 6 dmg defeats value-2 minion
    combat = [e for e in run.events if e.event_type.value == "COMBAT_RESOLVED"]
    assert len(combat) >= 2


@pytest.mark.effect_flow
def test_mystic_saplings_places_three_trees() -> None:
    state = _wuk_at_origin("mystic_saplings").build()
    _add_tree_pool(state, 3)

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=1, r=0, s=-1))
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=2, r=0, s=-2))
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=3, r=0, s=-3))
    run.finish()

    assert len(_placed_trees(state)) == 3


@pytest.mark.effect_flow
def test_mystic_saplings_can_stop_early() -> None:
    state = _wuk_at_origin("mystic_saplings").build()
    _add_tree_pool(state, 3)

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=1, r=0, s=-1))
    run.expect_input(InputRequestType.SELECT_HEX).skip()  # stop after one
    run.finish()

    assert len(_placed_trees(state)) == 1


@pytest.mark.effect_flow
def test_tree_slam_mode1_attacks_adjacent_minion() -> None:
    state = _wuk_at_origin("tree_slam").blue_minion("victim", at=(1, 0, -1)).build()

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("victim")
    run.finish()

    assert state.entity_locations.get("victim") is None  # 4 dmg defeats value-2 minion


@pytest.mark.effect_flow
def test_tree_slam_mode2_removes_tree_then_attacks_in_range() -> None:
    state = _wuk_at_origin("tree_slam").blue_minion("victim", at=(2, 0, -2)).build()
    _add_tree(state, "tree_1", Hex(q=1, r=0, s=-1))  # adjacent to Wuk

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)
    run.expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN).choose("tree_1")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("victim")
    run.finish()

    assert state.entity_locations.get("tree_1") is None  # tree removed (cost)
    assert state.entity_locations.get("victim") is None  # attacked in range


@pytest.mark.effect_flow
def test_march_of_nature_places_tree_after_resolving_card() -> None:
    state = _wuk_at_origin("claim_dominance").build()
    wuk = state.get_hero("hero_wuk")
    wuk.level = 8
    wuk.ultimate_card = hero_card("Wuk", "march_of_nature")
    _add_tree_pool(state, 3)

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")  # claim_dominance
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).choose("YES")  # March
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=2, r=0, s=-2))
    run.finish()

    assert len(_placed_trees(state)) == 1


@pytest.mark.effect_flow
def test_march_of_nature_can_decline() -> None:
    state = _wuk_at_origin("claim_dominance").build()
    wuk = state.get_hero("hero_wuk")
    wuk.level = 8
    wuk.ultimate_card = hero_card("Wuk", "march_of_nature")
    _add_tree_pool(state, 3)

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.CONFIRM_PASSIVE).choose("NO")
    run.finish()

    assert len(_placed_trees(state)) == 0


@pytest.mark.effect_flow
def test_trample_crosses_hero_and_minion() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(6)
        .red_hero("hero_wuk", at=(0, 0, 0), current_card=hero_card("Wuk", "trample"))
        .with_actor("hero_wuk")
        .blue_hero("eh", at=(1, 0, -1))  # no cards -> defeated by discard-or-defeat
        .blue_minion("em", at=(2, 0, -2))
        .build()
    )

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("MOVEMENT")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=3, r=0, s=-3))
    # crossed heroes are auto-affected (no player choice); only the optional
    # minion defeat prompts.
    run.expect_input(InputRequestType.SELECT_UNIT).choose("em")
    run.finish()

    assert state.entity_locations.get("hero_wuk") == Hex(q=3, r=0, s=-3)
    assert state.entity_locations.get("eh") is None  # defeated (no cards)
    assert state.entity_locations.get("em") is None  # defeated minion


@pytest.mark.effect_contract
def test_trample_defeat_credits_wuk_the_bounty() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(6)
        .red_hero("hero_wuk", at=(0, 0, 0), current_card=hero_card("Wuk", "trample"))
        .with_actor("hero_wuk")
        .blue_minion("em", at=(1, 0, -1))
        .build()
    )
    wuk = state.get_hero("hero_wuk")
    wuk.gold = 0
    bounty = state.get_unit("em").value

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("MOVEMENT")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=2, r=0, s=-2))
    run.expect_input(InputRequestType.SELECT_UNIT).choose("em")
    run.finish()

    assert state.entity_locations.get("em") is None
    assert wuk.gold == bounty


@pytest.mark.effect_flow
def test_trample_affects_all_crossed_heroes_without_choice() -> None:
    # Two enemy heroes crossed (no cards); both must be defeated with NO
    # selection prompt — the player cannot choose which heroes are affected.
    state = (
        EffectScenarioBuilder()
        .line_board(6)
        .red_hero("hero_wuk", at=(0, 0, 0), current_card=hero_card("Wuk", "trample"))
        .with_actor("hero_wuk")
        .blue_hero("eh1", at=(1, 0, -1))
        .blue_hero("eh2", at=(2, 0, -2))
        .build()
    )

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("MOVEMENT")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=3, r=0, s=-3))
    # no hero prompt, no minion candidates -> resolves with no further input
    run.finish()

    assert state.entity_locations.get("eh1") is None
    assert state.entity_locations.get("eh2") is None


@pytest.mark.effect_flow
def test_angry_stampede_defeats_support_then_heavy() -> None:
    # Heavy is immune while supported by the adjacent normal minion; defeating
    # the support first must unlock the heavy for the second minion select.
    state = (
        EffectScenarioBuilder()
        .line_board(6)
        .red_hero("hero_wuk", at=(0, 0, 0), current_card=hero_card("Wuk", "angry_stampede"))
        .with_actor("hero_wuk")
        .blue_minion("supp", at=(1, 0, -1))
        .blue_minion("hvy", at=(2, 0, -2), minion_type=MinionType.HEAVY)
        .build()
    )

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("MOVEMENT")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=3, r=0, s=-3))
    # no heroes crossed -> hero multi-select auto-finishes
    # minion 1: only the support is selectable (heavy is immune)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("supp")
    # minion 2: heavy now unsupported -> selectable
    run.expect_input(InputRequestType.SELECT_UNIT).choose("hvy")
    run.finish()

    assert state.entity_locations.get("supp") is None
    assert state.entity_locations.get("hvy") is None


@pytest.mark.effect_flow
def test_trample_normal_mode_may_detour_to_aligned_destination() -> None:
    state = (
        EffectScenarioBuilder()
        .small_arena()
        .red_hero("hero_wuk", at=(0, 0, 0), current_card=hero_card("Wuk", "trample"))
        .with_actor("hero_wuk")
        .blue_hero("eh", at=(1, 0, -1))
        .build()
    )

    run = run_card(state, "hero_wuk")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("MOVEMENT")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_HEX).choose(Hex(q=2, r=0, s=-2))
    run.finish()

    assert state.entity_locations.get("hero_wuk") == Hex(q=2, r=0, s=-2)
    assert state.entity_locations.get("eh") == Hex(q=1, r=0, s=-1)

"""Brynn card effect flow tests.

Brynn synergises with enemies who are "adjacent to 3 or more obstacles". Her
signature filter (AdjacentToObstaclesFilter) is unit-tested separately in
tests/engine/test_adjacent_to_obstacles_filter.py; here we drive whole cards.
"""

from __future__ import annotations

import pytest

from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import ActionType, Card, CardColor, CardTier, MinionType

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _fodder(card_id: str) -> Card:
    """A minimal discardable card for stocking a victim's hand."""
    return Card(
        id=card_id,
        name=card_id,
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=1,
        primary_action=ActionType.ATTACK,
        primary_action_value=1,
        secondary_actions={},
        is_ranged=False,
        range_value=0,
        effect_id="",
        effect_text="",
        is_facedown=False,
    )


def _radius_board(radius: int) -> list[tuple[int, int, int]]:
    coords = []
    for q in range(-radius, radius + 1):
        for r in range(-radius, radius + 1):
            s = -q - r
            if max(abs(q), abs(r), abs(s)) <= radius:
                coords.append((q, r, s))
    return coords


def _radius3() -> list[tuple[int, int, int]]:
    return _radius_board(3)


def _option_set(run) -> set:
    assert run.latest_request is not None
    options = set()
    for option in run.latest_request.options:
        if getattr(option, "metadata", None) and "raw" in option.metadata:
            options.add(option.metadata.get("raw"))
        else:
            options.add(option.id)
    return options


def _make_terrain(state, *coords: tuple[int, int, int]) -> None:
    for c in coords:
        state.board.tiles[Hex(q=c[0], r=c[1], s=c[2])].is_terrain = True


# ---------------------------------------------------------------------------
# Tread Lightly (swap only) — exercises the shared swap target set.
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_tread_lightly_swaps_with_adjacent_friendly_minion() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "tread_lightly"))
        .red_minion("red_minion", at=(1, 0, -1))
        .with_actor("hero_brynn")
        .build()
    )

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("red_minion").finish()

    assert state.entity_locations.get("hero_brynn") == Hex(q=1, r=0, s=-1)
    assert state.entity_locations.get("red_minion") == Hex(q=0, r=0, s=0)


@pytest.mark.effect_flow
def test_tread_lightly_swaps_with_distant_enemy_hero_adjacent_to_obstacles() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "tread_lightly"))
        .blue_hero("enemy_hero", at=(2, 0, -2))
        .with_actor("hero_brynn")
        .build()
    )
    # Three terrain neighbours on the far side of the enemy (won't lengthen the
    # pathfinding distance from Brynn) -> enemy is adjacent to 3+ obstacles.
    _make_terrain(state, (3, -1, -2), (3, 0, -3), (2, 1, -3))

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_hero").finish()

    assert state.entity_locations.get("hero_brynn") == Hex(q=2, r=0, s=-2)
    assert state.entity_locations.get("enemy_hero") == Hex(q=0, r=0, s=0)


@pytest.mark.effect_flow
def test_tread_lightly_distant_enemy_hero_without_obstacles_not_swappable() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "tread_lightly"))
        .red_minion("red_minion", at=(1, 0, -1))  # keeps a valid target so we get SELECT_UNIT
        .blue_hero("enemy_hero", at=(2, 0, -2))  # in radius 2, but open ground
        .with_actor("hero_brynn")
        .build()
    )

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT)
    options = _option_set(run)
    assert "red_minion" in options
    assert "enemy_hero" not in options


@pytest.mark.effect_flow
def test_tread_lightly_radius_minion_with_obstacles_not_swappable() -> None:
    # User-requested edge case: an enemy minion in radius that IS adjacent to
    # 3+ obstacles but is NOT adjacent to Brynn is still not a valid swap — the
    # radius branch is hero-only, and it fails the adjacent branch.
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "tread_lightly"))
        .red_minion("red_minion", at=(1, 0, -1))
        .blue_minion("enemy_minion", at=(2, 0, -2))
        .with_actor("hero_brynn")
        .build()
    )
    _make_terrain(state, (3, -1, -2), (3, 0, -3), (2, 1, -3))

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT)
    options = _option_set(run)
    assert "red_minion" in options
    assert "enemy_minion" not in options


@pytest.mark.effect_flow
def test_tread_lightly_adjacent_immune_minion_excluded() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "tread_lightly"))
        .red_minion("red_minion", at=(0, 1, -1))
        .blue_minion("heavy", at=(1, 0, -1), minion_type=MinionType.HEAVY)
        .blue_minion("support", at=(1, 1, -2))  # keeps heavy immune (friendly support in zone)
        .with_actor("hero_brynn")
        .build()
    )
    state.active_zone_id = "z1"

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT)
    options = _option_set(run)
    assert "red_minion" in options
    assert "heavy" not in options


# ---------------------------------------------------------------------------
# Cover Tracks (swap + move 1) / Hide Traces (swap + move 2)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_cover_tracks_swaps_then_moves_one() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "cover_tracks"))
        .red_minion("red_minion", at=(1, 0, -1))
        .with_actor("hero_brynn")
        .build()
    )

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("red_minion")
    # After swap Brynn is at (1,0,-1); optional 1-space move to (2,0,-2).
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 2, "r": 0, "s": -2}).finish()

    assert state.entity_locations.get("hero_brynn") == Hex(q=2, r=0, s=-2)
    assert state.entity_locations.get("red_minion") == Hex(q=0, r=0, s=0)


@pytest.mark.effect_flow
def test_hide_traces_swaps_then_may_skip_move() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "hide_traces"))
        .red_minion("red_minion", at=(1, 0, -1))
        .with_actor("hero_brynn")
        .build()
    )

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("red_minion")
    run.expect_input(InputRequestType.SELECT_HEX).skip().finish()

    assert state.entity_locations.get("hero_brynn") == Hex(q=1, r=0, s=-1)
    assert state.entity_locations.get("red_minion") == Hex(q=0, r=0, s=0)


# ---------------------------------------------------------------------------
# Mountain Guide (move friendly 2, + second if enemy qualifies) /
# Expedition Leader (move friendly 3)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_mountain_guide_moves_adjacent_friendly_no_second_without_enemy() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "mountain_guide"))
        .red_minion("red_minion", at=(1, 0, -1))
        .with_actor("hero_brynn")
        .build()
    )

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    # Choose the adjacent friendly to move, then its destination up to 2 away.
    run.expect_input(InputRequestType.SELECT_UNIT).choose("red_minion")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 3, "r": 0, "s": -3}).finish()

    assert state.entity_locations.get("red_minion") == Hex(q=3, r=0, s=-3)


@pytest.mark.effect_flow
def test_mountain_guide_second_move_when_enemy_adjacent_to_obstacles() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "mountain_guide"))
        .red_minion("red_minion", at=(1, 0, -1))
        .red_minion("red_minion_2", at=(0, 1, -1))
        .blue_hero("enemy_hero", at=(2, 0, -2))
        .with_actor("hero_brynn")
        .build()
    )
    _make_terrain(state, (3, -1, -2), (3, 0, -3), (2, 1, -3))

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("red_minion")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 1, "r": 1, "s": -2})
    # Enemy hero qualifies -> a DIFFERENT friendly in radius may also move.
    run.expect_input(InputRequestType.SELECT_UNIT)
    options = _option_set(run)
    assert "red_minion_2" in options
    assert "red_minion" not in options  # already moved
    run.choose("red_minion_2")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": -1, "r": 1, "s": 0}).finish()

    assert state.entity_locations.get("red_minion_2") == Hex(q=-1, r=1, s=0)


@pytest.mark.effect_flow
def test_expedition_leader_moves_friendly_three() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "expedition_leader"))
        .red_minion("red_minion", at=(1, 0, -1))
        .with_actor("hero_brynn")
        .build()
    )

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("red_minion")
    # 3 spaces from (1,0,-1); path clear of Brynn at the origin.
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 1, "r": -3, "s": 2}).finish()

    assert state.entity_locations.get("red_minion") == Hex(q=1, r=-3, s=2)


# ---------------------------------------------------------------------------
# Green chain — Traps: Bear Trap / Log Trap (discard) / Deadfall Trap (or defeat)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_bear_trap_bullet_a_adjacent_hero_discards() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "bear_trap"))
        .blue_hero("enemy_hero", at=(1, 0, -1))
        .with_actor("hero_brynn")
        .build()
    )
    state.get_hero("enemy_hero").hand = [_fodder("fodder")]

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)  # bullet A: adjacent hero
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_hero")
    run.expect_input(InputRequestType.SELECT_CARD).choose("fodder").finish()

    victim = state.get_hero("enemy_hero")
    assert not victim.hand
    assert any(c.id == "fodder" for c in victim.discard_pile)


@pytest.mark.effect_flow
def test_log_trap_bullet_b_radius_hero_with_obstacles_discards() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "log_trap"))
        .blue_hero("enemy_hero", at=(2, 0, -2))
        .with_actor("hero_brynn")
        .build()
    )
    _make_terrain(state, (3, -1, -2), (3, 0, -3), (2, 1, -3))
    state.get_hero("enemy_hero").hand = [_fodder("fodder")]

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)  # bullet B: radius + obstacles
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_hero")
    run.expect_input(InputRequestType.SELECT_CARD).choose("fodder").finish()

    assert not state.get_hero("enemy_hero").hand


@pytest.mark.effect_flow
def test_bear_trap_bullet_b_excludes_open_hero_offers_qualifying_hero() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "bear_trap"))
        .blue_hero("open_hero", at=(0, 2, -2))  # in radius 3, no obstacles
        .blue_hero("trapped_hero", at=(2, 0, -2))  # in radius, adjacent to 3 obstacles
        .with_actor("hero_brynn")
        .build()
    )
    _make_terrain(state, (3, -1, -2), (3, 0, -3), (2, 1, -3))

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)
    run.expect_input(InputRequestType.SELECT_UNIT)
    options = _option_set(run)
    assert "trapped_hero" in options
    assert "open_hero" not in options


@pytest.mark.effect_flow
def test_bear_trap_victim_without_cards_no_effect() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "bear_trap"))
        .blue_hero("enemy_hero", at=(1, 0, -1))
        .with_actor("hero_brynn")
        .build()
    )
    # enemy_hero has an empty hand -> "discards a card, if able" does nothing.

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_hero").finish()

    assert state.entity_locations.get("enemy_hero") == Hex(q=1, r=0, s=-1)
    assert not any(e.event_type == GameEventType.UNIT_DEFEATED for e in run.events)


@pytest.mark.effect_flow
def test_deadfall_trap_victim_without_cards_is_defeated() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "deadfall_trap"))
        .blue_hero("enemy_hero", at=(1, 0, -1))
        .with_actor("hero_brynn")
        .build()
    )
    # enemy_hero has no cards -> "discards a card, or is defeated" -> defeated.

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_hero").finish()

    assert any(e.event_type == GameEventType.UNIT_DEFEATED for e in run.events)


# ---------------------------------------------------------------------------
# Green chain — Retrieve: True Grit (move 3) / Die Hard (move 4)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_true_grit_retrieves_attack_card_only() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "true_grit"))
        .with_actor("hero_brynn")
        .build()
    )
    brynn = state.get_hero("hero_brynn")
    attack_card = hero_card("Brynn", "brynn_high_ground")
    skill_card = hero_card("Brynn", "tread_lightly")
    brynn.discard_pile = [attack_card, skill_card]

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_CARD)
    options = _option_set(run)
    assert "brynn_high_ground" in options
    assert "tread_lightly" not in options
    run.choose("brynn_high_ground").finish()

    assert any(c.id == "brynn_high_ground" for c in brynn.hand)
    assert any(e.event_type == GameEventType.CARD_RETRIEVED for e in run.events)


@pytest.mark.effect_flow
def test_true_grit_moves_when_enemy_adjacent_to_obstacles() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "true_grit"))
        .blue_hero("enemy_hero", at=(2, 0, -2))
        .with_actor("hero_brynn")
        .build()
    )
    _make_terrain(state, (3, -1, -2), (3, 0, -3), (2, 1, -3))
    state.get_hero("hero_brynn").discard_pile = [hero_card("Brynn", "brynn_high_ground")]

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_CARD).skip()  # decline the retrieve
    # Qualifying enemy hero in radius -> Brynn may move up to 3 spaces.
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": -3, "r": 0, "s": 3}).finish()

    assert state.entity_locations.get("hero_brynn") == Hex(q=-3, r=0, s=3)


@pytest.mark.effect_flow
def test_true_grit_no_move_without_qualifying_enemy() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "true_grit"))
        .blue_hero("enemy_hero", at=(2, 0, -2))  # in radius, but open ground
        .with_actor("hero_brynn")
        .build()
    )
    state.get_hero("hero_brynn").discard_pile = [hero_card("Brynn", "brynn_high_ground")]

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_CARD).skip().finish()

    assert state.entity_locations.get("hero_brynn") == Hex(q=0, r=0, s=0)


# ---------------------------------------------------------------------------
# Red chain — Melee attacks: High Ground / Elevated Ambush / Peak Precision
# ---------------------------------------------------------------------------


def _last_attack_value(run) -> int:
    combat = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert combat, "no COMBAT_RESOLVED event"
    return combat[-1].metadata["attack_value"]


@pytest.mark.effect_flow
def test_high_ground_bonus_when_target_hero_adjacent_to_obstacles() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "brynn_high_ground"))
        .blue_hero("enemy_hero", at=(1, 0, -1))
        .with_actor("hero_brynn")
        .build()
    )
    # Three terrain neighbours of the adjacent enemy hero (far side).
    _make_terrain(state, (2, 0, -2), (2, -1, -1), (1, 1, -2))

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_hero")
    run.expect_input("SELECT_CARD_OR_PASS").choose("PASS").finish()

    assert _last_attack_value(run) == 6  # base 4 + 2


@pytest.mark.effect_flow
def test_high_ground_no_bonus_against_open_hero() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "brynn_high_ground"))
        .blue_hero("enemy_hero", at=(1, 0, -1))
        .with_actor("hero_brynn")
        .build()
    )

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_hero")
    run.expect_input("SELECT_CARD_OR_PASS").choose("PASS").finish()

    assert _last_attack_value(run) == 4  # no bonus


@pytest.mark.effect_flow
def test_high_ground_no_bonus_against_minion() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "brynn_high_ground"))
        .blue_minion("enemy_minion", at=(1, 0, -1))
        .with_actor("hero_brynn")
        .build()
    )
    _make_terrain(state, (2, 0, -2), (2, -1, -1), (1, 1, -2))

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_minion")
    run.finish()

    assert _last_attack_value(run) == 4  # bonus is hero-only


@pytest.mark.effect_flow
def test_elevated_ambush_bonus() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "elevated_ambush"))
        .blue_hero("enemy_hero", at=(1, 0, -1))
        .with_actor("hero_brynn")
        .build()
    )
    _make_terrain(state, (2, 0, -2), (2, -1, -1), (1, 1, -2))

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_hero")
    run.expect_input("SELECT_CARD_OR_PASS").choose("PASS").finish()

    assert _last_attack_value(run) == 7  # base 5 + 2


@pytest.mark.effect_flow
def test_peak_precision_bonus_and_retrieves_itself() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "peak_precision"))
        .blue_hero("enemy_hero", at=(1, 0, -1))
        .with_actor("hero_brynn")
        .build()
    )
    _make_terrain(state, (2, 0, -2), (2, -1, -1), (1, 1, -2))

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_hero")
    run.expect_input("SELECT_CARD_OR_PASS").choose("PASS")
    # Qualifying target -> +2 and an offer to retrieve this card.
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)
    run.finish()

    assert _last_attack_value(run) == 7  # base 5 + 2
    brynn = state.get_hero("hero_brynn")
    assert any(c.id == "peak_precision" for c in brynn.hand)
    assert any(e.event_type == GameEventType.CARD_RETRIEVED for e in run.events)


@pytest.mark.effect_flow
def test_peak_precision_no_offer_against_open_target() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "peak_precision"))
        .blue_hero("enemy_hero", at=(1, 0, -1))
        .with_actor("hero_brynn")
        .build()
    )

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_hero")
    run.expect_input("SELECT_CARD_OR_PASS").choose("PASS").finish()  # no retrieve offer

    assert _last_attack_value(run) == 5  # no bonus
    brynn = state.get_hero("hero_brynn")
    assert not any(c.id == "peak_precision" for c in brynn.hand)


# ---------------------------------------------------------------------------
# Red chain — Splits: Split Attack (repeat adjacent) / Split Throw (repeat in range)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_split_attack_repeats_when_first_target_qualifies() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "split_attack"))
        .blue_hero("enemy_hero", at=(2, 0, -2))  # in range 2, adjacent to obstacles
        .blue_minion("adj_minion", at=(1, 0, -1))  # adjacent to Brynn -> repeat target
        .with_actor("hero_brynn")
        .build()
    )
    _make_terrain(state, (3, -1, -2), (3, 0, -3), (2, 1, -3))

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_hero")
    run.expect_input("SELECT_CARD_OR_PASS").choose("PASS")
    # First target qualifies -> may repeat once on a different unit adjacent to you.
    run.expect_input(InputRequestType.SELECT_OPTION).choose("YES")
    run.expect_input(InputRequestType.SELECT_UNIT)
    options = _option_set(run)
    assert "adj_minion" in options
    assert "enemy_hero" not in options  # must be a DIFFERENT unit
    run.choose("adj_minion").finish()

    combat = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert len(combat) == 2


@pytest.mark.effect_flow
def test_split_attack_no_repeat_when_first_target_is_minion() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "split_attack"))
        .blue_minion("enemy_minion", at=(2, 0, -2))
        .blue_minion("adj_minion", at=(1, 0, -1))
        .with_actor("hero_brynn")
        .build()
    )
    _make_terrain(state, (3, -1, -2), (3, 0, -3), (2, 1, -3))

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_minion")
    run.finish()  # no repeat offered

    combat = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert len(combat) == 1


@pytest.mark.effect_flow
def test_split_throw_repeat_uses_card_range() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "split_throw"))
        .blue_hero("enemy_hero", at=(2, 0, -2))  # first target, qualifies
        .blue_minion("range_minion", at=(0, 2, -2))  # range 2 from Brynn, NOT adjacent
        .with_actor("hero_brynn")
        .build()
    )
    _make_terrain(state, (3, -1, -2), (3, 0, -3), (2, 1, -3))

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_hero")
    run.expect_input("SELECT_CARD_OR_PASS").choose("PASS")
    run.expect_input(InputRequestType.SELECT_OPTION).choose("YES")
    run.expect_input(InputRequestType.SELECT_UNIT)
    options = _option_set(run)
    assert "range_minion" in options  # repeat target may be anywhere in range
    run.choose("range_minion").finish()

    combat = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert len(combat) == 2


# ---------------------------------------------------------------------------
# Untiered — Decoy (move up to 2 enemies) / Familiar Ground (basic ranged attack)
# ---------------------------------------------------------------------------


@pytest.mark.effect_flow
def test_decoy_moves_two_enemy_minions_on_different_targets() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "decoy"))
        .blue_minion("minion_a", at=(2, 0, -2))
        .blue_minion("minion_b", at=(0, 2, -2))
        .with_actor("hero_brynn")
        .build()
    )

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("minion_a")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 3, "r": 0, "s": -3})
    # Second pick must be a DIFFERENT target.
    run.expect_input(InputRequestType.SELECT_UNIT)
    options = _option_set(run)
    assert "minion_b" in options
    assert "minion_a" not in options
    run.choose("minion_b")
    run.expect_input(InputRequestType.SELECT_HEX).choose({"q": 1, "r": 2, "s": -3}).finish()

    assert state.entity_locations.get("minion_a") == Hex(q=3, r=0, s=-3)
    assert state.entity_locations.get("minion_b") == Hex(q=1, r=2, s=-3)


@pytest.mark.effect_flow
def test_decoy_open_hero_not_targetable() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "decoy"))
        .blue_minion("minion_a", at=(2, 0, -2))
        .blue_hero("open_hero", at=(0, 2, -2))
        .with_actor("hero_brynn")
        .build()
    )

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("SKILL")
    run.expect_input(InputRequestType.SELECT_UNIT)
    options = _option_set(run)
    assert "minion_a" in options
    assert "open_hero" not in options  # hero needs 3+ obstacles (bullet B)


@pytest.mark.effect_flow
def test_familiar_ground_bullet_a_attacks_adjacent_minion() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "familiar_ground"))
        .blue_minion("enemy_minion", at=(1, 0, -1))
        .with_actor("hero_brynn")
        .build()
    )

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(1)  # bullet A
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_minion").finish()

    combat = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert len(combat) == 1


@pytest.mark.effect_flow
def test_familiar_ground_bullet_b_hero_in_range_with_obstacles() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius_board(4))
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "familiar_ground"))
        .blue_hero("enemy_hero", at=(3, 0, -3))  # range 3, interior on a radius-4 board
        .with_actor("hero_brynn")
        .build()
    )
    _make_terrain(state, (3, -1, -2), (2, 1, -3), (3, 1, -4))

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)  # bullet B
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_hero")
    run.expect_input("SELECT_CARD_OR_PASS").choose("PASS").finish()

    combat = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert len(combat) == 1


@pytest.mark.effect_flow
def test_familiar_ground_bullet_b_open_hero_not_targetable() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius_board(4))
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "familiar_ground"))
        .blue_hero("enemy_hero", at=(3, 0, -3))  # in range, interior, open ground
        .with_actor("hero_brynn")
        .build()
    )

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_NUMBER).choose(2)  # bullet B
    # No valid target -> mandatory select aborts without a combat.
    run.finish()

    combat = [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    assert not combat


# ---------------------------------------------------------------------------
# Ultimate — Over the Top: enemy heroes count as adjacent to 3+ obstacles
# ---------------------------------------------------------------------------


def _unlock_ultimate(state) -> None:
    from goa2.data.heroes.brynn import create_brynn

    brynn = state.get_hero("hero_brynn")
    brynn.level = 8
    brynn.ultimate_card = create_brynn().ultimate_card


@pytest.mark.effect_flow
def test_over_the_top_grants_bonus_against_open_hero() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_radius3())
        .red_hero("hero_brynn", at=(0, 0, 0), current_card=hero_card("Brynn", "elevated_ambush"))
        .blue_hero("enemy_hero", at=(1, 0, -1))  # fully in the open
        .with_actor("hero_brynn")
        .build()
    )
    _unlock_ultimate(state)

    run = run_card(state, "hero_brynn")
    run.expect_input(InputRequestType.CHOOSE_ACTION).choose("ATTACK")
    run.expect_input(InputRequestType.SELECT_UNIT).choose("enemy_hero")
    run.expect_input("SELECT_CARD_OR_PASS").choose("PASS").finish()

    assert _last_attack_value(run) == 7  # base 5 + 2 via ultimate

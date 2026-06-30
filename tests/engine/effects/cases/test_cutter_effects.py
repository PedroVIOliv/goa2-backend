"""Effect flow tests for the hero Cutter."""

import pytest

from goa2.domain.input import InputRequestType
from goa2.domain.models import MinionType, TeamColor
from goa2.engine.steps import PerformPrimaryActionStep, SetContextFlagStep

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _hex_disk(radius: int) -> list[tuple[int, int, int]]:
    return [
        (q, r, -q - r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if abs(q + r) <= radius
    ]


def _option_set(run) -> set:
    """Set of selectable values from the current request (raw metadata or option id)."""
    assert run.latest_request is not None
    options = set()
    for option in run.latest_request.options:
        if hasattr(option, "metadata") and option.metadata and "raw" in option.metadata:
            options.add(option.metadata.get("raw"))
        elif hasattr(option, "id"):
            options.add(option.id)
        else:
            options.add(option)
    return options


def _give_hand(state, hero_id: str, n: int = 1) -> list:
    hero = state.get_hero(hero_id)
    hand = [hero_card("Cutter", "daring_strike") for _ in range(n)]
    for i, c in enumerate(hand):
        c.id = f"{hero_id}_hand_{i}"
    hero.hand = hand
    return list(hand)


def _pos(state, uid) -> tuple:
    h = state.entity_locations.get(uid)
    return (h.q, h.r, h.s) if h is not None else None


# =============================================================================
# BLUE — Bombardment: "An enemy hero in radius, adjacent to another enemy unit
# and not adjacent to you, discards a card, if able."
# =============================================================================


def _bombardment_state():
    return (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        # Cutter at origin; enemy hero 2 away (in radius, not adjacent),
        # with a friendly (to it) minion adjacent to it.
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "bombardment"))
        .blue_hero("blue_hero", at=(2, 0, -2))
        .blue_minion("blue_minion", at=(3, 0, -3))
        .with_actor("hero_cutter")
        .build()
    )


@pytest.mark.effect_flow
def test_bombardment_forces_eligible_enemy_hero_to_discard() -> None:
    state = _bombardment_state()
    hand = _give_hand(state, "blue_hero")

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    assert "blue_hero" in _option_set(run)
    run.choose("blue_hero").expect_input(InputRequestType.SELECT_CARD)
    run.choose(hand[0].id).finish()

    victim = state.get_hero("blue_hero")
    assert hand[0] in victim.discard_pile
    assert hand[0] not in victim.hand


@pytest.mark.effect_flow
def test_bombardment_excludes_hero_adjacent_to_cutter() -> None:
    # Enemy hero adjacent to Cutter (distance 1) is NOT a valid target even
    # though it is adjacent to another enemy unit. A valid far hero is offered.
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "bombardment"))
        .blue_hero("blue_close", at=(1, 0, -1))  # adjacent to Cutter -> excluded
        .blue_minion("minion_close", at=(2, 0, -2))  # adjacent to blue_close
        .blue_hero("blue_far", at=(-2, 0, 2))  # eligible
        .blue_minion("minion_far", at=(-3, 0, 3))  # adjacent to blue_far
        .with_actor("hero_cutter")
        .build()
    )

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    options = _option_set(run)
    assert "blue_far" in options
    assert "blue_close" not in options


@pytest.mark.effect_flow
def test_bombardment_excludes_isolated_enemy_hero() -> None:
    # Enemy hero in radius and not adjacent to Cutter, but NOT adjacent to any
    # other enemy unit -> not a valid target. A non-isolated hero is offered.
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "bombardment"))
        .blue_hero("blue_iso", at=(2, 0, -2))  # isolated -> excluded
        .blue_hero("blue_ok", at=(-2, 0, 2))  # eligible
        .blue_minion("minion_ok", at=(-3, 0, 3))  # adjacent to blue_ok
        .with_actor("hero_cutter")
        .build()
    )

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    options = _option_set(run)
    assert "blue_ok" in options
    assert "blue_iso" not in options


@pytest.mark.effect_flow
def test_bombardment_adjacency_counts_immune_minion() -> None:
    # "Adjacent to another enemy unit" is a presence check: it must count an
    # immune (HEAVY) minion. CountMatchFilter runs only the supplied sub-filters
    # (no implicit immunity filter), so the hero remains a valid target.
    from goa2.engine.rules import is_immune

    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "bombardment"))
        .blue_hero("blue_hero", at=(2, 0, -2))
        .minion("blue_heavy", at=(3, 0, -3), team=TeamColor.BLUE, minion_type=MinionType.HEAVY)
        # A second friendly minion keeps the heavy immune ("until no more
        # friendly minions are present"), within the active battle zone.
        .blue_minion("blue_escort", at=(0, 3, -3))
        .with_actor("hero_cutter")
        .build()
    )
    state.active_zone_id = "z1"
    # Precondition: the flanking minion is genuinely immune.
    assert is_immune(state.get_unit("blue_heavy"), state)
    hand = _give_hand(state, "blue_hero")

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    assert "blue_hero" in _option_set(run)
    run.choose("blue_hero").expect_input(InputRequestType.SELECT_CARD)
    run.choose(hand[0].id).finish()
    assert hand[0] in state.get_hero("blue_hero").discard_pile


@pytest.mark.effect_flow
def test_broadside_may_repeat_on_a_different_target() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "broadside"))
        .blue_hero("blue_hero_a", at=(2, 0, -2))
        .blue_hero("blue_hero_b", at=(0, 2, -2))
        .blue_minion("blue_minion_a", at=(3, 0, -3))
        .blue_minion("blue_minion_b", at=(0, 3, -3))
        .with_actor("hero_cutter")
        .build()
    )
    hand_a = _give_hand(state, "blue_hero_a")
    hand_b = _give_hand(state, "blue_hero_b")

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_hero_a").expect_input(InputRequestType.SELECT_CARD)
    run.choose(hand_a[0].id)
    # Repeat prompt, then second target must exclude the first.
    run.expect_input(InputRequestType.SELECT_OPTION)
    run.choose("YES").expect_input(InputRequestType.SELECT_UNIT)
    second_options = _option_set(run)
    assert "blue_hero_b" in second_options
    assert "blue_hero_a" not in second_options
    run.choose("blue_hero_b").expect_input(InputRequestType.SELECT_CARD)
    run.choose(hand_b[0].id).finish()

    assert hand_a[0] in state.get_hero("blue_hero_a").discard_pile
    assert hand_b[0] in state.get_hero("blue_hero_b").discard_pile


# =============================================================================
# GREEN — Outmaneuver / Outsmart: "Swap with an enemy minion in radius; you may
# move that minion up to 2 / 3 spaces." (radius 3)
# =============================================================================


def _outmaneuver_state(card_id: str):
    return (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", card_id))
        .blue_minion("blue_minion", at=(2, 0, -2))
        .with_actor("hero_cutter")
        .build()
    )


@pytest.mark.effect_flow
def test_outmaneuver_swaps_with_enemy_minion_then_nudges() -> None:
    state = _outmaneuver_state("outmaneuver")

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    assert "blue_minion" in _option_set(run)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_HEX)
    # After swap, Cutter is at (2,0,-2) and the minion is at (0,0,0).
    assert _pos(state, "hero_cutter") == (2, 0, -2)
    assert _pos(state, "blue_minion") == (0, 0, 0)
    # Nudge the minion 2 spaces away from its new spot.
    run.choose({"q": -2, "r": 0, "s": 2}).finish()
    assert _pos(state, "blue_minion") == (-2, 0, 2)


@pytest.mark.effect_flow
def test_outmaneuver_nudge_is_optional() -> None:
    state = _outmaneuver_state("outmaneuver")

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_HEX)
    run.skip().finish()
    # Swap happened; minion stayed put after the skipped nudge.
    assert _pos(state, "hero_cutter") == (2, 0, -2)
    assert _pos(state, "blue_minion") == (0, 0, 0)


@pytest.mark.effect_flow
def test_outmaneuver_cannot_swap_with_hero_or_friendly_or_out_of_radius() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(6))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "outmaneuver"))
        .blue_minion("blue_minion_ok", at=(2, 0, -2))  # eligible
        .blue_hero("blue_hero", at=(1, 0, -1))  # hero, not a minion
        .red_minion("red_minion", at=(0, 1, -1))  # friendly
        .blue_minion("blue_minion_far", at=(5, 0, -5))  # out of radius 3
        .with_actor("hero_cutter")
        .build()
    )

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    options = _option_set(run)
    assert "blue_minion_ok" in options
    assert "blue_hero" not in options
    assert "red_minion" not in options
    assert "blue_minion_far" not in options


@pytest.mark.effect_flow
def test_outsmart_nudges_up_to_three() -> None:
    state = _outmaneuver_state("outsmart")

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_HEX)
    # Minion now at (0,0,0); a hex 3 away is reachable for Outsmart (range 3).
    run.choose({"q": 0, "r": 3, "s": -3}).finish()
    assert _pos(state, "blue_minion") == (0, 3, -3)


# =============================================================================
# BLUE — X Marks the Spot / A Fistful of Coins: "An enemy hero in radius chooses
# one — • You place that hero in a space in radius. • You gain N coins."
# (A Fistful: "If you have 13+ coins, you alone win the game." — win stubbed.)
# =============================================================================


def _coins_state(card_id: str):
    return (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", card_id))
        .blue_hero("blue_hero", at=(2, 0, -2))
        .with_actor("hero_cutter")
        .build()
    )


@pytest.mark.effect_flow
def test_x_marks_enemy_chooses_coins() -> None:
    state = _coins_state("x_marks_the_spot")
    cutter = state.get_hero("hero_cutter")
    assert cutter.gold == 0

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_hero").expect_input(InputRequestType.SELECT_NUMBER)
    # Enemy hero chooses option 2 (Cutter gains coins).
    run.choose(2).finish()
    assert cutter.gold == 2
    # Hero was not moved.
    assert _pos(state, "blue_hero") == (2, 0, -2)


@pytest.mark.effect_flow
def test_x_marks_enemy_chooses_placement() -> None:
    state = _coins_state("x_marks_the_spot")

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_hero").expect_input(InputRequestType.SELECT_NUMBER)
    # Enemy hero chooses option 1 (Cutter places them); Cutter picks the hex.
    run.choose(1).expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 0, "r": 3, "s": -3}).finish()
    assert _pos(state, "blue_hero") == (0, 3, -3)
    assert state.get_hero("hero_cutter").gold == 0


@pytest.mark.effect_flow
def test_x_marks_only_targets_enemy_hero_in_radius() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(6))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "x_marks_the_spot"))
        .blue_hero("blue_ok", at=(2, 0, -2))  # eligible
        .blue_minion("blue_minion", at=(1, 0, -1))  # minion
        .red_hero("red_ally", at=(0, 1, -1))  # friendly hero
        .blue_hero("blue_far", at=(5, 0, -5))  # out of radius 3
        .with_actor("hero_cutter")
        .build()
    )

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    options = _option_set(run)
    assert "blue_ok" in options
    assert "blue_minion" not in options
    assert "red_ally" not in options
    assert "blue_far" not in options


@pytest.mark.effect_flow
def test_fistful_gains_three_coins() -> None:
    state = _coins_state("a_fistful_of_coins")
    cutter = state.get_hero("hero_cutter")

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_hero").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(2).finish()
    assert cutter.gold == 3
    assert state.solo_win_pending is None


@pytest.mark.effect_flow
def test_fistful_solo_win_pending_at_thirteen() -> None:
    state = _coins_state("a_fistful_of_coins")
    cutter = state.get_hero("hero_cutter")
    cutter.gold = 10  # +3 = 13

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_hero").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(2).finish()
    assert cutter.gold == 13
    # Win is stubbed: flag is set, but the game does not actually end.
    assert state.solo_win_pending == "hero_cutter"
    assert state.winner is None


@pytest.mark.effect_flow
def test_fistful_no_solo_win_below_thirteen() -> None:
    state = _coins_state("a_fistful_of_coins")
    cutter = state.get_hero("hero_cutter")
    cutter.gold = 9  # +3 = 12

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_hero").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(2).finish()
    assert cutter.gold == 12
    assert state.solo_win_pending is None


def _hex_options(run) -> set:
    """Set of (q,r,s) tuples offered for a SELECT_HEX request."""
    opts = set()
    for raw in _option_set(run):
        if hasattr(raw, "q"):
            opts.add((raw.q, raw.r, raw.s))
    return opts


# =============================================================================
# GREEN — Brace for Impact / Ramming Speed / Crashland
# "Move 3 / 3-4 / 3-4-5 in a straight line, ignoring obstacles, to a space
#  adjacent to an enemy hero; that hero discards a card, if able."
# =============================================================================


@pytest.mark.effect_flow
def test_brace_for_impact_charges_through_obstacle_and_forces_discard() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(6))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "brace_for_impact"))
        .blue_minion("blocker", at=(2, 0, -2))  # obstacle on the path
        .blue_hero("blue_hero", at=(4, 0, -4))
        .with_actor("hero_cutter")
        .build()
    )
    hand = _give_hand(state, "blue_hero")

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_HEX)
    # Lands exactly 3 away (dist 3), adjacent to the enemy hero, passing the blocker.
    assert (3, 0, -3) in _hex_options(run)
    run.choose({"q": 3, "r": 0, "s": -3}).expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_hero").expect_input(InputRequestType.SELECT_CARD)
    run.choose(hand[0].id).finish()

    assert _pos(state, "hero_cutter") == (3, 0, -3)
    assert hand[0] in state.get_hero("blue_hero").discard_pile


@pytest.mark.effect_flow
def test_ramming_speed_allows_distance_four() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(6))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "ramming_speed"))
        .blue_hero("blue_hero", at=(5, 0, -5))
        .with_actor("hero_cutter")
        .build()
    )
    hand = _give_hand(state, "blue_hero")

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_HEX)
    options = _hex_options(run)
    assert (4, 0, -4) in options  # distance 4 allowed
    assert (2, 0, -2) not in options  # distance 2 below min
    run.choose({"q": 4, "r": 0, "s": -4}).expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_hero").expect_input(InputRequestType.SELECT_CARD)
    run.choose(hand[0].id).finish()
    assert _pos(state, "hero_cutter") == (4, 0, -4)


@pytest.mark.effect_flow
def test_crashland_allows_distance_five() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(7))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "crashland"))
        .blue_hero("blue_hero", at=(6, 0, -6))
        .with_actor("hero_cutter")
        .build()
    )
    hand = _give_hand(state, "blue_hero")

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_HEX)
    assert (5, 0, -5) in _hex_options(run)
    run.choose({"q": 5, "r": 0, "s": -5}).expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_hero").expect_input(InputRequestType.SELECT_CARD)
    run.choose(hand[0].id).finish()
    assert _pos(state, "hero_cutter") == (5, 0, -5)


@pytest.mark.effect_flow
def test_brace_landing_must_be_adjacent_to_enemy_hero_not_minion() -> None:
    # Only an enemy minion is around (no enemy hero) -> mandatory move has no
    # legal destination -> action aborts, nothing happens.
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(6))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "brace_for_impact"))
        .blue_minion("blue_minion", at=(4, 0, -4))
        .with_actor("hero_cutter")
        .build()
    )

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").finish()
    # Cutter did not move; no discard happened.
    assert _pos(state, "hero_cutter") == (0, 0, 0)


def _make_terrain(state, *coords) -> None:
    from goa2.domain.hex import Hex

    for q, r, s in coords:
        state.board.get_tile(Hex(q=q, r=r, s=s)).is_terrain = True


# =============================================================================
# SILVER — Grappling Bolt: "Target an obstacle in range and in a straight line,
# with no obstacles between you; ignore immunity. Move in a straight line towards
# that obstacle until you are adjacent to it." (range 5)
# =============================================================================


@pytest.mark.effect_flow
def test_grappling_bolt_pulls_self_adjacent_to_terrain() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(6))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "grappling_bolt"))
        .with_actor("hero_cutter")
        .build()
    )
    _make_terrain(state, (4, 0, -4))

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_HEX)
    assert (4, 0, -4) in _hex_options(run)
    run.choose({"q": 4, "r": 0, "s": -4}).finish()
    # Pulled along the line, stopping adjacent to the terrain.
    assert _pos(state, "hero_cutter") == (3, 0, -3)


@pytest.mark.effect_flow
def test_grappling_bolt_anchors_on_immune_minion() -> None:
    from goa2.engine.rules import is_immune

    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(6))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "grappling_bolt"))
        .minion("blue_heavy", at=(4, 0, -4), team=TeamColor.BLUE, minion_type=MinionType.HEAVY)
        .blue_minion("escort", at=(0, 4, -4))
        .with_actor("hero_cutter")
        .build()
    )
    state.active_zone_id = "z1"
    assert is_immune(state.get_unit("blue_heavy"), state)

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_HEX)
    # Ignore immunity: the immune minion's hex is a valid anchor.
    assert (4, 0, -4) in _hex_options(run)
    run.choose({"q": 4, "r": 0, "s": -4}).finish()
    assert _pos(state, "hero_cutter") == (3, 0, -3)


@pytest.mark.effect_flow
def test_grappling_bolt_blocked_by_obstacle_between() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(6))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "grappling_bolt"))
        .with_actor("hero_cutter")
        .build()
    )
    # Terrain at distance 2 blocks the line to the terrain at distance 4.
    _make_terrain(state, (2, 0, -2), (4, 0, -4))

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_HEX)
    options = _hex_options(run)
    assert (2, 0, -2) in options  # clear line to the near obstacle
    assert (4, 0, -4) not in options  # blocked by the obstacle between


@pytest.mark.effect_flow
def test_grappling_bolt_rejects_off_axis_and_out_of_range() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(8))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "grappling_bolt"))
        .with_actor("hero_cutter")
        .build()
    )
    _make_terrain(state, (2, 1, -3), (7, 0, -7), (3, 0, -3))

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_HEX)
    options = _hex_options(run)
    assert (3, 0, -3) in options  # in line, in range
    assert (2, 1, -3) not in options  # off-axis (not a straight line)
    assert (7, 0, -7) not in options  # out of range 5


def _combat_values(run) -> list:
    from goa2.domain.events import GameEventType

    return [
        e.metadata.get("attack_value")
        for e in run.events
        if e.event_type == GameEventType.COMBAT_RESOLVED
    ]


# =============================================================================
# RED — Daring Strike / Bold Thrust / Fearless Lunge
# "Choose one — • Move 1/2/3 in a straight line. Target a hero adjacent to you in
#  the direction of the move; +2 Attack. • Target a unit adjacent to you."
# Move (branch A) is committed independently of the follow-up attack.
# =============================================================================


@pytest.mark.effect_flow
def test_daring_strike_charge_hits_collinear_hero_with_plus_two() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(5))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "daring_strike"))
        .blue_hero("blue_hero", at=(2, 0, -2))  # collinear, 1 step beyond the landing
        .with_actor("hero_cutter")
        .build()
    )

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(1).expect_input(InputRequestType.SELECT_HEX)  # charge branch
    run.choose({"q": 1, "r": 0, "s": -1}).expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_hero").expect_input("SELECT_CARD_OR_PASS")
    run.choose("PASS").finish()

    assert _pos(state, "hero_cutter") == (1, 0, -1)
    # Daring Strike base attack 4, +2 from the charge branch.
    assert 6 in _combat_values(run)


@pytest.mark.effect_flow
def test_daring_strike_charge_move_stands_with_no_collinear_hero() -> None:
    # A hero adjacent to the landing but OFF the move axis is not a valid charge
    # target; the move still stands and no attack happens.
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(5))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "daring_strike"))
        .blue_hero("blue_offaxis", at=(1, -1, 0))  # adjacent to landing, off-axis
        .with_actor("hero_cutter")
        .build()
    )

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(1).expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 1, "r": 0, "s": -1}).finish()

    assert _pos(state, "hero_cutter") == (1, 0, -1)  # move committed
    assert _combat_values(run) == []  # no attack


@pytest.mark.effect_flow
def test_daring_strike_adjacent_attack_has_no_bonus() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(5))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "daring_strike"))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_cutter")
        .build()
    )

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(2).expect_input(InputRequestType.SELECT_UNIT)  # adjacent-attack branch
    run.choose("blue_minion").finish()

    assert _pos(state, "hero_cutter") == (0, 0, 0)  # no move
    assert 4 in _combat_values(run)  # base attack, no +2


@pytest.mark.effect_flow
def test_fearless_lunge_charges_up_to_three() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(6))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "fearless_lunge"))
        .blue_hero("blue_hero", at=(4, 0, -4))
        .with_actor("hero_cutter")
        .build()
    )

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(1).expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 3, "r": 0, "s": -3}).expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_hero").expect_input("SELECT_CARD_OR_PASS")
    run.choose("PASS").finish()

    assert _pos(state, "hero_cutter") == (3, 0, -3)
    assert 7 in _combat_values(run)  # Fearless base 5, +2


# =============================================================================
# RED — Evasive Shot / Tumble Shot
# "Target a unit in range and in a straight line. After the attack: Move up to
#  2 / 3 spaces in the opposite direction." (ranged, range 2)
# =============================================================================


@pytest.mark.effect_flow
def test_tumble_shot_attacks_in_line_then_retreats_opposite() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(6))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "tumble_shot"))
        .blue_minion("blue_minion", at=(2, 0, -2))  # in range 2, straight line
        .with_actor("hero_cutter")
        .build()
    )

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_HEX)
    options = _hex_options(run)
    assert (-3, 0, 3) in options  # opposite direction, up to 3 (Tumble)
    assert (1, 0, -1) not in options  # toward the target — not allowed
    assert (0, -1, 1) not in options  # sideways — not allowed
    run.choose({"q": -3, "r": 0, "s": 3}).finish()
    assert _pos(state, "hero_cutter") == (-3, 0, 3)
    assert _combat_values(run)  # an attack happened


@pytest.mark.effect_flow
def test_evasive_shot_retreat_capped_at_two_and_optional() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(6))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "evasive_shot"))
        .blue_minion("blue_minion", at=(2, 0, -2))
        .with_actor("hero_cutter")
        .build()
    )

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_HEX)
    options = _hex_options(run)
    assert (-2, 0, 2) in options  # distance 2 allowed
    assert (-3, 0, 3) not in options  # distance 3 exceeds Evasive's 2
    # Retreat is optional ("up to") — skip it.
    run.skip().finish()
    assert _pos(state, "hero_cutter") == (0, 0, 0)


@pytest.mark.effect_flow
def test_tumble_shot_target_must_be_in_straight_line_and_range() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(6))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "tumble_shot"))
        .blue_minion("in_line", at=(2, 0, -2))  # in range, straight line
        .blue_minion("off_axis", at=(1, 1, -2))  # not a straight line
        .blue_minion("too_far", at=(0, 4, -4))  # out of range 2
        .with_actor("hero_cutter")
        .build()
    )

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    options = _option_set(run)
    assert "in_line" in options
    assert "off_axis" not in options
    assert "too_far" not in options


# =============================================================================
# GOLD — Walk the Plank: "Choose one — • Push an enemy hero adjacent to you up to
#  4 spaces; if that hero is pushed into another zone, that hero discards a card,
#  or is defeated. • Defeat a minion adjacent to you."
# =============================================================================


def _two_zone_board() -> EffectScenarioBuilder:
    # Build a board split into two zones along the q axis.
    from goa2.domain.board import Board, Zone
    from goa2.domain.hex import Hex

    left = {Hex(q=q, r=0, s=-q) for q in range(-2, 1)}  # q in [-2,0] => zone L
    right = {Hex(q=q, r=0, s=-q) for q in range(1, 6)}  # q in [1,5]  => zone R
    board = Board()
    board.zones = {
        "zL": Zone(id="zL", hexes=left, neighbors=["zR"]),
        "zR": Zone(id="zR", hexes=right, neighbors=["zL"]),
    }
    board.populate_tiles_from_zones()
    builder = EffectScenarioBuilder()
    builder._board = board  # use the custom two-zone board
    return builder


@pytest.mark.effect_flow
def test_walk_the_plank_push_across_zone_forces_discard_or_defeat() -> None:
    builder = _two_zone_board()
    state = (
        builder.red_hero(
            "hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "walk_the_plank")
        )
        .blue_hero("blue_hero", at=(1, 0, -1))  # adjacent, in zone R already? no: q=1 is zR
        .with_actor("hero_cutter")
        .build()
    )
    # Place Cutter in zL and the hero in zL too so the push can cross into zR.
    from goa2.domain.hex import Hex

    state.move_unit("hero_cutter", Hex(q=-1, r=0, s=1))
    state.move_unit("blue_hero", Hex(q=0, r=0, s=0))
    hand = _give_hand(state, "blue_hero")

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)  # modal choose-one
    run.choose(1).expect_input(InputRequestType.SELECT_UNIT)  # push branch
    run.choose("blue_hero").expect_input(InputRequestType.SELECT_NUMBER)  # push distance
    run.choose(3).expect_input(InputRequestType.SELECT_CARD)  # crossed into zR -> discard
    run.choose(hand[0].id).finish()
    assert hand[0] in state.get_hero("blue_hero").discard_pile


@pytest.mark.effect_flow
def test_walk_the_plank_push_within_zone_no_penalty() -> None:
    builder = _two_zone_board()
    state = (
        builder.red_hero(
            "hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "walk_the_plank")
        )
        .blue_hero("blue_hero", at=(1, 0, -1))
        .with_actor("hero_cutter")
        .build()
    )
    from goa2.domain.hex import Hex

    state.move_unit("blue_hero", Hex(q=2, r=0, s=-2))  # vacate (1,0,-1) first
    state.move_unit("hero_cutter", Hex(q=1, r=0, s=-1))  # both in zR
    hand = _give_hand(state, "blue_hero")

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(1).expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_hero").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(2).finish()  # pushed deeper into zR, no zone change -> no discard
    assert hand[0] in state.get_hero("blue_hero").hand


@pytest.mark.effect_flow
def test_walk_the_plank_defeat_adjacent_minion() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "walk_the_plank"))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_cutter")
        .build()
    )

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(2).expect_input(InputRequestType.SELECT_UNIT)  # defeat branch
    run.choose("blue_minion").finish()
    assert _pos(state, "blue_minion") is None  # defeated/removed


@pytest.mark.effect_flow
def test_walk_the_plank_defeat_excludes_immune_minion() -> None:
    from goa2.engine.rules import is_immune

    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero("hero_cutter", at=(0, 0, 0), current_card=hero_card("Cutter", "walk_the_plank"))
        .minion("blue_heavy", at=(1, 0, -1), team=TeamColor.BLUE, minion_type=MinionType.HEAVY)
        .blue_minion("escort", at=(0, 1, -1))
        .blue_minion("plain", at=(-1, 0, 1))  # a legal defeat target
        .with_actor("hero_cutter")
        .build()
    )
    state.active_zone_id = "z1"
    assert is_immune(state.get_unit("blue_heavy"), state)

    run = run_card(state, "hero_cutter")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(2).expect_input(InputRequestType.SELECT_UNIT)
    options = _option_set(run)
    assert "plain" in options
    assert "blue_heavy" not in options  # immune minion not a valid defeat target


# =============================================================================
# ULTIMATE — Legend of the Skies: "The first time each turn after you perform a
# primary action, you may perform the primary action of a card in the previous
# turn slot."
# =============================================================================


def _legend_setup():
    from goa2.data.heroes.registry import HeroRegistry
    from goa2.engine.effects import CardEffectRegistry

    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero("hero_cutter", at=(0, 0, 0))
        .with_actor("hero_cutter")
        .build()
    )
    hero = state.get_hero("hero_cutter")
    ult = HeroRegistry.get("Cutter").ultimate_card
    effect = CardEffectRegistry.get("legend_of_the_skies")
    return state, hero, ult, effect


@pytest.mark.effect_contract
def test_legend_registers_after_primary_action_passive() -> None:
    from goa2.domain.models.enums import PassiveTrigger

    _, _, _, effect = _legend_setup()
    cfg = effect.get_passive_config()
    assert cfg is not None
    assert cfg.trigger == PassiveTrigger.AFTER_PRIMARY_ACTION
    assert cfg.uses_per_turn == 1
    assert cfg.is_optional is True


@pytest.mark.effect_contract
def test_after_primary_action_fires_only_on_primary() -> None:
    """Performing a card's SECONDARY action must not emit AFTER_PRIMARY_ACTION.

    Regression: Legend of the Skies (an AFTER_PRIMARY_ACTION passive) was
    offered after a secondary MOVEMENT because it was wired to AFTER_RESOLVE_CARD,
    which fires on any action. AFTER_RESOLVE_CARD must still fire for both (Wuk's
    March of Nature contract).
    """
    from goa2.domain.models.enums import PassiveTrigger
    from goa2.engine.steps.cards import ResolveCardStep
    from goa2.engine.steps.effects import CheckPassiveAbilitiesStep

    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(4))
        .red_hero(
            "hero_cutter",
            at=(0, 0, 0),
            current_card=hero_card("Cutter", "fearless_lunge"),  # ATTACK + 2ndary MOVEMENT
        )
        .with_actor("hero_cutter")
        .build()
    )

    def triggers_for(choice: str) -> set[str]:
        step = ResolveCardStep(hero_id="hero_cutter")
        step.pending_input = {"selection": choice}
        result = step.resolve(state, {})
        return {
            s.trigger for s in (result.new_steps or []) if isinstance(s, CheckPassiveAbilitiesStep)
        }

    primary = triggers_for("ATTACK")
    secondary = triggers_for("MOVEMENT")

    assert PassiveTrigger.AFTER_PRIMARY_ACTION.value in primary
    assert PassiveTrigger.AFTER_PRIMARY_ACTION.value not in secondary
    # AFTER_RESOLVE_CARD fires regardless of primary/secondary.
    assert PassiveTrigger.AFTER_RESOLVE_CARD.value in primary
    assert PassiveTrigger.AFTER_RESOLVE_CARD.value in secondary


@pytest.mark.effect_contract
def test_legend_offers_only_when_previous_slot_exists() -> None:
    from goa2.domain.models.enums import PassiveTrigger

    state, hero, ult, effect = _legend_setup()

    # First turn of the round: no previous slot -> no offer.
    hero.played_cards = []
    hero.resolved_turn_count = 0
    assert (
        effect.should_offer_passive(state, hero, ult, PassiveTrigger.AFTER_PRIMARY_ACTION, {})
        is False
    )

    # A card resolved on the previous turn fills slot 0 -> offered.
    prev = hero_card("Cutter", "daring_strike")
    hero.played_cards = [prev]
    hero.resolved_turn_count = 1
    assert (
        effect.should_offer_passive(state, hero, ult, PassiveTrigger.AFTER_PRIMARY_ACTION, {})
        is True
    )


@pytest.mark.effect_contract
def test_legend_performs_previous_slot_card() -> None:
    from goa2.domain.models.enums import PassiveTrigger

    state, hero, ult, effect = _legend_setup()
    prev = hero_card("Cutter", "daring_strike")
    hero.played_cards = [prev]
    hero.resolved_turn_count = 1

    steps = effect.get_passive_steps(state, hero, ult, PassiveTrigger.AFTER_PRIMARY_ACTION, {})
    perform = [s for s in steps if isinstance(s, PerformPrimaryActionStep)]
    assert len(perform) == 1
    assert perform[0].card_key == "ult_prev_card_id"
    # The id staged for the perform step is the previous slot's card, not current.
    flags = [s for s in steps if isinstance(s, SetContextFlagStep)]
    assert flags[0].value == prev.id


@pytest.mark.effect_contract
def test_legend_ignores_empty_previous_slot() -> None:
    from goa2.domain.models.enums import PassiveTrigger

    state, hero, ult, effect = _legend_setup()
    # Slot exists in the list but was emptied (card discarded/removed).
    hero.played_cards = [None]
    hero.resolved_turn_count = 1
    assert (
        effect.should_offer_passive(state, hero, ult, PassiveTrigger.AFTER_PRIMARY_ACTION, {})
        is False
    )
    assert effect.get_passive_steps(state, hero, ult, PassiveTrigger.AFTER_PRIMARY_ACTION, {}) == []

"""Effect flow tests for the hero Mrak."""

import pytest

from goa2.domain.events import GameEventType
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import Token, TokenType
from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.engine.effect_manager import EffectManager
from goa2.engine.steps import OfferRockUltimateStep

from ..builders import EffectScenarioBuilder, hero_card
from ..runner import run_card


def _place_rock(state, rock_id: str, at: tuple[int, int, int]) -> None:
    rock = Token(id=rock_id, name="Rock", token_type=TokenType.ROCK)
    state.register_entity(rock)
    state.place_entity(rock_id, Hex(q=at[0], r=at[1], s=at[2]))


def _add_rock_pool(state, count: int = 3) -> None:
    """Seed the Rock token supply (the fluent builder does not initialize pools)."""
    state.token_pool[TokenType.ROCK] = []
    for i in range(count):
        rock = Token(id=f"rock_pool_{i}", name="Rock", token_type=TokenType.ROCK)
        state.register_entity(rock)
        state.token_pool[TokenType.ROCK].append(rock)


def _hex_disk(radius: int) -> list[tuple[int, int, int]]:
    return [
        (q, r, -q - r)
        for q in range(-radius, radius + 1)
        for r in range(-radius, radius + 1)
        if abs(q + r) <= radius
    ]


def _option_set(run) -> set:
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


# =============================================================================
# Seismic Slam / Seismic Assault / Epicenter: "An enemy hero in radius adjacent
# to terrain, or to a Rock token, discards a card, or is defeated."
# =============================================================================


@pytest.mark.parametrize("card_id", ["seismic_slam", "seismic_assault"])
def test_seismic_forces_discard_on_terrain_adjacent_enemy_hero(card_id: str) -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(2))
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", card_id))
        .blue_hero("hero_arien", at=(1, 0, -1))
        .with_actor("hero_mrak")
        .build()
    )
    # Terrain neighbour makes the interior enemy hero a legal target.
    state.board.tiles[Hex(q=2, r=0, s=-2)].is_terrain = True
    arien = state.get_hero("hero_arien")
    arien.hand = [hero_card("Mrak", "boulder_rush")]

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    assert "hero_arien" in _option_set(run)
    run.choose("hero_arien").expect_input(InputRequestType.SELECT_CARD)
    run.choose("boulder_rush").finish()

    assert len(arien.hand) == 0


@pytest.mark.parametrize("card_id", ["seismic_slam", "seismic_assault", "epicenter"])
def test_seismic_skips_enemy_hero_not_adjacent_to_terrain_or_rock(card_id: str) -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(2))
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", card_id))
        .blue_hero("hero_arien", at=(1, 0, -1))
        .with_actor("hero_mrak")
        .build()
    )
    # No terrain, no rock: the interior enemy hero is not adjacent to either.
    arien = state.get_hero("hero_arien")
    arien.hand = [hero_card("Mrak", "boulder_rush")]

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL")
    run.finish()

    assert len(arien.hand) == 1  # untouched


def test_seismic_defeats_terrain_adjacent_enemy_hero_with_no_cards() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(2))
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "seismic_slam"))
        .blue_hero("hero_arien", at=(1, 0, -1))
        .with_actor("hero_mrak")
        .build()
    )
    state.board.tiles[Hex(q=2, r=0, s=-2)].is_terrain = True
    state.get_hero("hero_arien").hand = []  # no cards -> "or is defeated"

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("hero_arien").finish()

    assert any(
        e.event_type == GameEventType.UNIT_DEFEATED and e.target_id == "hero_arien"
        for e in run.events
    )


def test_epicenter_discards_then_declines_repeat() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(2))
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "epicenter"))
        .blue_hero("hero_arien", at=(1, 0, -1))
        .with_actor("hero_mrak")
        .build()
    )
    state.board.tiles[Hex(q=2, r=0, s=-2)].is_terrain = True
    arien = state.get_hero("hero_arien")
    arien.hand = [hero_card("Mrak", "boulder_rush")]

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("hero_arien").expect_input(InputRequestType.SELECT_CARD)
    run.choose("boulder_rush").expect_input(InputRequestType.SELECT_OPTION)
    run.choose("NO").finish()

    assert len(arien.hand) == 0


def test_epicenter_repeats_on_a_different_target() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(2))
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "epicenter"))
        .blue_hero("hero_arien", at=(1, 0, -1))
        .blue_hero("hero_bain", at=(-1, 0, 1))
        .with_actor("hero_mrak")
        .build()
    )
    # Both enemy heroes sit adjacent to on-map terrain.
    state.board.tiles[Hex(q=2, r=0, s=-2)].is_terrain = True
    state.board.tiles[Hex(q=-2, r=0, s=2)].is_terrain = True
    arien = state.get_hero("hero_arien")
    bain = state.get_hero("hero_bain")
    arien.hand = [hero_card("Mrak", "boulder_rush")]
    bain.hand = [hero_card("Mrak", "boulder_blitz")]

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("hero_arien").expect_input(InputRequestType.SELECT_CARD)
    run.choose("boulder_rush").expect_input(InputRequestType.SELECT_OPTION)
    run.choose("YES").expect_input(InputRequestType.SELECT_UNIT)
    # The first victim is excluded from the repeat.
    assert "hero_arien" not in _option_set(run)
    assert "hero_bain" in _option_set(run)
    run.choose("hero_bain").expect_input(InputRequestType.SELECT_CARD)
    run.choose("boulder_blitz").finish()

    assert len(arien.hand) == 0
    assert len(bain.hand) == 0


# =============================================================================
# Treacherous Ground / Rockslide / Avalanche: "You may move a unit in range 1
# space to a space adjacent to terrain, or a Rock token. [Avalanche: repeat once]"
# =============================================================================


@pytest.mark.parametrize("card_id", ["treacherous_ground", "rockslide"])
def test_rockslide_moves_unit_to_terrain_adjacent_hex(card_id: str) -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero("hero_mrak", at=(-1, 0, 1), current_card=hero_card("Mrak", card_id))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mrak")
        .build()
    )
    state.board.tiles[Hex(q=2, r=0, s=-2)].is_terrain = True

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_HEX)
    dests = _option_set(run)
    assert Hex(q=2, r=-1, s=-1) in dests
    run.choose({"q": 2, "r": -1, "s": -1}).finish()

    assert state.entity_locations.get("blue_minion") == Hex(q=2, r=-1, s=-1)


def test_rockslide_is_optional_and_skippable() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero("hero_mrak", at=(-1, 0, 1), current_card=hero_card("Mrak", "treacherous_ground"))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mrak")
        .build()
    )
    state.board.tiles[Hex(q=2, r=0, s=-2)].is_terrain = True

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.skip().finish()

    assert state.entity_locations.get("blue_minion") == Hex(q=1, r=0, s=-1)


def test_rockslide_cannot_move_self() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero("hero_mrak", at=(-1, 0, 1), current_card=hero_card("Mrak", "treacherous_ground"))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mrak")
        .build()
    )
    state.board.tiles[Hex(q=2, r=0, s=-2)].is_terrain = True

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    assert "hero_mrak" not in _option_set(run)


def test_rockslide_destination_requires_terrain_or_rock_with_no_anchor() -> None:
    # Fully interior minion, no terrain or rock anywhere: no legal destination.
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero("hero_mrak", at=(2, 0, -2), current_card=hero_card("Mrak", "treacherous_ground"))
        .blue_minion("blue_minion", at=(0, 0, 0))
        .with_actor("hero_mrak")
        .build()
    )

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").finish()  # no destination -> no move

    assert state.entity_locations.get("blue_minion") == Hex(q=0, r=0, s=0)


def test_rockslide_destination_can_be_adjacent_to_rock_token() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero("hero_mrak", at=(-2, 0, 2), current_card=hero_card("Mrak", "treacherous_ground"))
        .blue_minion("blue_minion", at=(0, 0, 0))
        .with_actor("hero_mrak")
        .build()
    )
    _place_rock(state, "rock_1", (2, 0, -2))

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_HEX)
    assert _option_set(run) == {Hex(q=1, r=0, s=-1)}
    run.choose({"q": 1, "r": 0, "s": -1}).finish()

    assert state.entity_locations.get("blue_minion") == Hex(q=1, r=0, s=-1)


def test_avalanche_may_repeat_the_move_once() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero("hero_mrak", at=(-1, 0, 1), current_card=hero_card("Mrak", "avalanche"))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mrak")
        .build()
    )
    state.board.tiles[Hex(q=2, r=0, s=-2)].is_terrain = True

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 2, "r": -1, "s": -1}).expect_input(InputRequestType.SELECT_OPTION)
    run.choose("NO").finish()

    assert state.entity_locations.get("blue_minion") == Hex(q=2, r=-1, s=-1)


# =============================================================================
# Stomping Step / Ground Shaker: "Move a unit in radius which is adjacent to
# terrain, or to a Rock token, 1 space. Place a Rock token in the space it
# occupied. [Ground Shaker: May repeat once on a different target.]"
# =============================================================================


def _rock_at(state, q: int, r: int, s: int) -> bool:
    target = Hex(q=q, r=r, s=s)
    return any(
        state.entity_locations.get(str(t.id)) == target
        for t in state.token_pool.get(TokenType.ROCK, [])
    )


def test_stomping_moves_terrain_adjacent_unit_and_drops_rock() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero("hero_mrak", at=(-1, 0, 1), current_card=hero_card("Mrak", "stomping_step"))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mrak")
        .build()
    )
    state.board.tiles[Hex(q=2, r=0, s=-2)].is_terrain = True
    _add_rock_pool(state)

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 1, "r": -1, "s": 0}).finish()

    assert state.entity_locations.get("blue_minion") == Hex(q=1, r=-1, s=0)
    assert _rock_at(state, 1, 0, -1)  # rock dropped in the vacated hex


def test_stomping_requires_a_terrain_or_rock_adjacent_unit() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero("hero_mrak", at=(2, 0, -2), current_card=hero_card("Mrak", "stomping_step"))
        .blue_minion("blue_minion", at=(0, 0, 0))
        .with_actor("hero_mrak")
        .build()
    )

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL")
    run.finish()  # mandatory select has no candidate -> nothing happens

    assert state.entity_locations.get("blue_minion") == Hex(q=0, r=0, s=0)
    assert not _rock_at(state, 0, 0, 0)


def test_ground_shaker_repeats_on_a_different_target() -> None:
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "ground_shaker"))
        .blue_minion("blue_minion_a", at=(1, 0, -1))
        .blue_minion("blue_minion_b", at=(-1, 0, 1))
        .with_actor("hero_mrak")
        .build()
    )
    state.board.tiles[Hex(q=2, r=0, s=-2)].is_terrain = True
    state.board.tiles[Hex(q=-2, r=0, s=2)].is_terrain = True
    _add_rock_pool(state)

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion_a").expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 1, "r": -1, "s": 0}).expect_input(InputRequestType.SELECT_OPTION)
    run.choose("YES").expect_input(InputRequestType.SELECT_UNIT)
    assert "blue_minion_a" not in _option_set(run)
    run.choose("blue_minion_b").expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": -1, "r": 1, "s": 0}).finish()

    assert state.entity_locations.get("blue_minion_a") == Hex(q=1, r=-1, s=0)
    assert state.entity_locations.get("blue_minion_b") == Hex(q=-1, r=1, s=0)
    assert _rock_at(state, 1, 0, -1)
    assert _rock_at(state, -1, 0, 1)


# =============================================================================
# Rolling Stone / Strolling Stone: "Move any number of spaces in a straight
# line, ignoring obstacles, without moving through more than N empty spaces."
# =============================================================================


def test_rolling_stone_rolls_through_obstacle_within_one_empty_space() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=6)
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "rolling_stone"))
        .with_actor("hero_mrak")
        .build()
    )
    state.board.tiles[Hex(q=1, r=0, s=-1)].is_terrain = True  # obstacle, ignored, free

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_HEX)
    dests = _option_set(run)
    assert Hex(q=3, r=0, s=-3) in dests  # interior empties: 1 (just (2,0,-2))
    assert Hex(q=4, r=0, s=-4) not in dests  # interior empties: 2 > budget
    run.choose({"q": 3, "r": 0, "s": -3}).finish()

    assert state.entity_locations.get("hero_mrak") == Hex(q=3, r=0, s=-3)


def test_strolling_stone_allows_two_empty_spaces() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=6)
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "strolling_stone"))
        .with_actor("hero_mrak")
        .build()
    )
    state.board.tiles[Hex(q=1, r=0, s=-1)].is_terrain = True

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_HEX)
    dests = _option_set(run)
    assert Hex(q=4, r=0, s=-4) in dests  # interior empties: 2 == budget
    assert Hex(q=5, r=0, s=-5) not in dests  # interior empties: 3 > budget
    run.choose({"q": 4, "r": 0, "s": -4}).finish()

    assert state.entity_locations.get("hero_mrak") == Hex(q=4, r=0, s=-4)


def test_rolling_stone_is_optional_skip() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=6)
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "rolling_stone"))
        .with_actor("hero_mrak")
        .build()
    )

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_HEX)
    run.skip().finish()

    assert state.entity_locations.get("hero_mrak") == Hex(q=0, r=0, s=0)


# =============================================================================
# Boulder Rush / Blitz / dozer: "Push a token, or an enemy unit, adjacent to you
# 1..N spaces, ignoring obstacles; you may move up to N spaces in the direction
# of the push, ignoring obstacles."
# =============================================================================


def test_boulder_pushes_enemy_and_follows_in_push_direction() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=7)
        .red_hero("hero_mrak", at=(3, 0, -3), current_card=hero_card("Mrak", "boulder_rush"))
        .blue_minion("blue_minion", at=(4, 0, -4))
        .with_actor("hero_mrak")
        .build()
    )

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(2).expect_input(InputRequestType.SELECT_HEX)
    follow = _option_set(run)
    assert Hex(q=5, r=0, s=-5) in follow  # forward, within budget
    assert Hex(q=2, r=0, s=-2) not in follow  # backward is not the push direction
    run.choose({"q": 5, "r": 0, "s": -5}).finish()

    assert state.entity_locations.get("blue_minion") == Hex(q=6, r=0, s=-6)
    assert state.entity_locations.get("hero_mrak") == Hex(q=5, r=0, s=-5)


def test_boulder_follow_move_is_optional() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=7)
        .red_hero("hero_mrak", at=(3, 0, -3), current_card=hero_card("Mrak", "boulder_rush"))
        .blue_minion("blue_minion", at=(4, 0, -4))
        .with_actor("hero_mrak")
        .build()
    )

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(2).expect_input(InputRequestType.SELECT_HEX)
    run.skip().finish()

    assert state.entity_locations.get("blue_minion") == Hex(q=6, r=0, s=-6)
    assert state.entity_locations.get("hero_mrak") == Hex(q=3, r=0, s=-3)  # stayed


def test_boulder_can_push_a_rock_token() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=7)
        .red_hero("hero_mrak", at=(3, 0, -3), current_card=hero_card("Mrak", "boulder_rush"))
        .with_actor("hero_mrak")
        .build()
    )
    _place_rock(state, "rock_1", (4, 0, -4))

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("rock_1").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(2).expect_input(InputRequestType.SELECT_HEX)
    run.skip().finish()

    assert state.entity_locations.get("rock_1") == Hex(q=6, r=0, s=-6)


def test_boulder_cannot_push_friendly_unit() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=7)
        .red_hero("hero_mrak", at=(3, 0, -3), current_card=hero_card("Mrak", "boulder_rush"))
        .red_minion("red_minion", at=(4, 0, -4))
        .with_actor("hero_mrak")
        .build()
    )

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL")
    run.finish()  # only a friendly unit adjacent -> nothing to push

    assert state.entity_locations.get("red_minion") == Hex(q=4, r=0, s=-4)


def test_boulderdozer_allows_push_distance_four() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=8)
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "boulderdozer"))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mrak")
        .build()
    )

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(4).expect_input(InputRequestType.SELECT_HEX)
    run.skip().finish()

    assert state.entity_locations.get("blue_minion") == Hex(q=5, r=0, s=-5)


# =============================================================================
# Stone Grip (Silver): "Place exactly 3 Rock tokens into empty spaces adjacent
# to an enemy hero in range, and as far away from you as possible."
# =============================================================================


def test_stone_grip_places_three_rocks_in_the_farthest_empty_hexes() -> None:
    # Enemy hero at (2,0,-2) has four empty neighbours at distances 3,3,2,1 from
    # Mrak. The three farthest get rocks; the nearest (1,0,-1) never does.
    board = [(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3), (2, 1, -3), (2, -1, -1)]
    state = (
        EffectScenarioBuilder()
        .with_hexes(board)
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "stone_grip"))
        .blue_hero("hero_arien", at=(2, 0, -2))
        .with_actor("hero_mrak")
        .build()
    )
    _add_rock_pool(state)

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("hero_arien").expect_input(InputRequestType.SELECT_HEX)
    # First placement offers only the two farthest (distance 3) hexes.
    assert _option_set(run) == {Hex(q=3, r=0, s=-3), Hex(q=2, r=1, s=-3)}
    # Each single-option placement now prompts as well (no auto-select).
    run.choose({"q": 3, "r": 0, "s": -3}).expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 2, "r": 1, "s": -3}).expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 2, "r": -1, "s": -1}).finish()

    assert _rock_at(state, 3, 0, -3)
    assert _rock_at(state, 2, 1, -3)
    assert _rock_at(state, 2, -1, -1)
    assert not _rock_at(state, 1, 0, -1)  # nearest hex is never used


def test_stone_grip_places_nothing_with_fewer_than_three_empty_hexes() -> None:
    # Enemy hero at (2,0,-2) has only two empty neighbours on this board.
    board = [(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3)]
    state = (
        EffectScenarioBuilder()
        .with_hexes(board)
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "stone_grip"))
        .blue_hero("hero_arien", at=(2, 0, -2))
        .with_actor("hero_mrak")
        .build()
    )
    _add_rock_pool(state)

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("hero_arien").finish()  # exactly 3 or none -> none

    assert not _rock_at(state, 1, 0, -1)
    assert not _rock_at(state, 3, 0, -3)


def test_stone_grip_supply_short_removes_board_rock_before_placing() -> None:
    # A pool rock from an earlier turn sits at (0,1,-1), not adjacent to the
    # target. Free supply is 2 < 3, so one removal is forced — prompted BEFORE
    # any placement, and never offering rocks placed by this batch.
    board = [
        (0, 0, 0),
        (1, 0, -1),
        (2, 0, -2),
        (3, 0, -3),
        (2, 1, -3),
        (2, -1, -1),
        (0, 1, -1),
    ]
    state = (
        EffectScenarioBuilder()
        .with_hexes(board)
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "stone_grip"))
        .blue_hero("hero_arien", at=(2, 0, -2))
        .with_actor("hero_mrak")
        .build()
    )
    _add_rock_pool(state)
    state.place_entity("rock_pool_0", Hex(q=0, r=1, s=-1))

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("hero_arien").expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)  # removal
    assert _option_set(run) == {"rock_pool_0"}
    run.choose("rock_pool_0").expect_input(InputRequestType.SELECT_HEX)
    assert _option_set(run) == {Hex(q=3, r=0, s=-3), Hex(q=2, r=1, s=-3)}
    run.choose({"q": 3, "r": 0, "s": -3}).expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 2, "r": 1, "s": -3}).expect_input(InputRequestType.SELECT_HEX)
    assert _option_set(run) == {Hex(q=2, r=-1, s=-1)}
    run.choose({"q": 2, "r": -1, "s": -1}).finish()

    assert _rock_at(state, 3, 0, -3)
    assert _rock_at(state, 2, 1, -3)
    assert _rock_at(state, 2, -1, -1)
    assert not _rock_at(state, 0, 1, -1)  # the pre-existing rock was recycled


def test_stone_grip_counts_removal_freed_hex_adjacent_to_target() -> None:
    # Only 2 empty hexes adjacent to the target; the 3rd neighbour holds a pool
    # rock from an earlier turn. Free supply is 2 < 3, so the forced removal
    # frees that hex — per the remove-then-place rule, "exactly 3" is possible.
    board = [(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3), (2, 1, -3)]
    state = (
        EffectScenarioBuilder()
        .with_hexes(board)
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "stone_grip"))
        .blue_hero("hero_arien", at=(2, 0, -2))
        .with_actor("hero_mrak")
        .build()
    )
    _add_rock_pool(state)
    state.place_entity("rock_pool_0", Hex(q=3, r=0, s=-3))

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("hero_arien").expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)  # removal
    assert _option_set(run) == {"rock_pool_0"}
    run.choose("rock_pool_0").expect_input(InputRequestType.SELECT_HEX)
    # Post-removal the freed hex is empty again and ties for farthest.
    assert _option_set(run) == {Hex(q=3, r=0, s=-3), Hex(q=2, r=1, s=-3)}
    run.choose({"q": 3, "r": 0, "s": -3}).expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 2, "r": 1, "s": -3}).expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 1, "r": 0, "s": -1}).finish()

    assert _rock_at(state, 3, 0, -3)
    assert _rock_at(state, 2, 1, -3)
    assert _rock_at(state, 1, 0, -1)


def test_stone_grip_skips_when_freed_hex_would_not_be_adjacent() -> None:
    # Two empty hexes adjacent to the target and a board rock whose removal
    # frees a NON-adjacent hex: still impossible -> place nothing, remove
    # nothing, show no prompts.
    board = [(0, 0, 0), (1, 0, -1), (2, 0, -2), (2, 1, -3), (0, 1, -1)]
    state = (
        EffectScenarioBuilder()
        .with_hexes(board)
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "stone_grip"))
        .blue_hero("hero_arien", at=(2, 0, -2))
        .with_actor("hero_mrak")
        .build()
    )
    _add_rock_pool(state)
    state.place_entity("rock_pool_0", Hex(q=0, r=1, s=-1))

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("hero_arien").finish()  # infeasible even with removal -> none

    assert _rock_at(state, 0, 1, -1)  # untouched
    assert not _rock_at(state, 1, 0, -1)
    assert not _rock_at(state, 2, 1, -3)


# =============================================================================
# Fissure (Gold): Attack 4 adjacent; "After the attack: Place a Rock token in
# each of the first three empty spaces in the straight line from you in the
# direction of the attack."
# =============================================================================


def test_fissure_attacks_then_places_rocks_along_the_attack_line() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=6)
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "fissure"))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mrak")
        .build()
    )
    _add_rock_pool(state)

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").finish()

    assert [e for e in run.events if e.event_type == GameEventType.COMBAT_RESOLVED]
    # First empty hex of the +q line is the target's hex if it was defeated,
    # otherwise the hex just past it. Three rocks fill consecutive empties.
    minion_alive = state.entity_locations.get("blue_minion") is not None
    start = 2 if minion_alive else 1
    for q in range(start, start + 3):
        assert _rock_at(state, q, 0, -q)
    placed = sum(
        1
        for t in state.token_pool[TokenType.ROCK]
        if state.entity_locations.get(str(t.id)) is not None
    )
    assert placed == 3


def test_fissure_supply_short_removes_board_rock_before_placing() -> None:
    # A pool rock sits off-line at (0,1,-1); free supply is 2 < 3 line spaces.
    # The shortfall removal is prompted BEFORE any placement (never offering
    # rocks this card just placed), then all three line hexes get rocks.
    board = [(q, 0, -q) for q in range(6)] + [(0, 1, -1)]
    state = (
        EffectScenarioBuilder()
        .with_hexes(board)
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "fissure"))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mrak")
        .build()
    )
    _add_rock_pool(state)
    state.place_entity("rock_pool_0", Hex(q=0, r=1, s=-1))

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)  # removal
    assert _option_set(run) == {"rock_pool_0"}
    run.choose("rock_pool_0").finish()

    # Attack 4 defeats the minion (value 2), so the line starts at q=1.
    assert state.entity_locations.get("blue_minion") is None
    for q in (1, 2, 3):
        assert _rock_at(state, q, 0, -q)
    assert not _rock_at(state, 0, 1, -1)  # the pre-existing rock was recycled


def test_fissure_removed_line_rock_rejoins_the_line() -> None:
    # The only board rock sits ON the attack line at q=2. Removing it for the
    # supply shortfall happens BEFORE the line is evaluated, so its hex counts
    # again among "the first three empty spaces" (remove-then-place order).
    state = (
        EffectScenarioBuilder()
        .line_board(length=6)
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "fissure"))
        .blue_minion("blue_minion", at=(1, 0, -1))
        .with_actor("hero_mrak")
        .build()
    )
    _add_rock_pool(state)
    state.place_entity("rock_pool_0", Hex(q=2, r=0, s=-2))

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("ATTACK").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion").expect_input(InputRequestType.SELECT_UNIT_OR_TOKEN)  # removal
    assert _option_set(run) == {"rock_pool_0"}
    run.choose("rock_pool_0").finish()

    assert state.entity_locations.get("blue_minion") is None
    for q in (1, 2, 3):
        assert _rock_at(state, q, 0, -q)
    assert not _rock_at(state, 4, 0, -4)  # line no longer skips past q=2


# =============================================================================
# Ultimate "Rock and a Hard Place" (passive, level >= 8): "Once per turn, after
# you place one or more Rock tokens adjacent to one or more enemy heroes, each
# of those heroes discards a card, if able." Optional; offered per placement
# batch (Stone Grip = one batch of 3); each hero discards at most one.
# =============================================================================


def _stone_grip_at_level_8():
    board = [(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3), (2, 1, -3), (2, -1, -1)]
    state = (
        EffectScenarioBuilder()
        .with_hexes(board)
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "stone_grip"))
        .blue_hero("hero_arien", at=(2, 0, -2))
        .with_actor("hero_mrak")
        .build()
    )
    mrak = state.get_hero("hero_mrak")
    mrak.level = 8  # ultimate unlocked
    mrak.ultimate_card = hero_card("Mrak", "rock_and_a_hard_place")
    _add_rock_pool(state)
    return state


def test_ultimate_makes_rock_adjacent_hero_discard_exactly_one() -> None:
    state = _stone_grip_at_level_8()
    arien = state.get_hero("hero_arien")
    arien.hand = [hero_card("Mrak", "boulder_rush"), hero_card("Mrak", "boulder_blitz")]

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("hero_arien").expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 3, "r": 0, "s": -3}).expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 2, "r": 1, "s": -3}).expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 2, "r": -1, "s": -1}).expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(1).expect_input(InputRequestType.SELECT_CARD)  # apply ultimate
    run.choose("boulder_rush").finish()

    assert len(arien.hand) == 1  # exactly one discarded, despite 3 adjacent rocks


@pytest.mark.effect_contract
def test_ultimate_does_not_affect_immune_adjacent_enemy_hero() -> None:
    state = _stone_grip_at_level_8()
    EffectManager.create_effect(
        state=state,
        source_id="hero_arien",
        effect_type=EffectType.IMMUNITY_ENEMY_ACTIONS,
        scope=EffectScope(
            shape=Shape.POINT,
            origin_id="hero_arien",
            affects=AffectsFilter.SELF,
        ),
        duration=DurationType.THIS_TURN,
        is_active=True,
    )
    context = {"rock_hex": Hex(q=3, r=0, s=-3)}

    result = OfferRockUltimateStep(rock_hex_keys=["rock_hex"]).resolve(state, context)

    assert result.new_steps == []
    assert "_rock_ult_affected" not in context


def test_ultimate_is_optional_and_can_be_declined() -> None:
    state = _stone_grip_at_level_8()
    arien = state.get_hero("hero_arien")
    arien.hand = [hero_card("Mrak", "boulder_rush")]

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("hero_arien").expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 3, "r": 0, "s": -3}).expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 2, "r": 1, "s": -3}).expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 2, "r": -1, "s": -1}).expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(0).finish()  # decline

    assert len(arien.hand) == 1  # untouched


def test_ultimate_inactive_below_level_8_gives_no_offer() -> None:
    state = _stone_grip_at_level_8()
    state.get_hero("hero_mrak").level = 1  # ultimate locked
    arien = state.get_hero("hero_arien")
    arien.hand = [hero_card("Mrak", "boulder_rush")]

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("hero_arien").expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 3, "r": 0, "s": -3}).expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 2, "r": 1, "s": -3}).expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 2, "r": -1, "s": -1}).finish()  # no ultimate prompt

    assert len(arien.hand) == 1  # untouched


def test_ultimate_if_able_does_nothing_to_empty_handed_hero() -> None:
    state = _stone_grip_at_level_8()
    arien = state.get_hero("hero_arien")
    arien.hand = []  # no cards -> "if able" -> nothing, not defeated

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("hero_arien").expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 3, "r": 0, "s": -3}).expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 2, "r": 1, "s": -3}).expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 2, "r": -1, "s": -1}).expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(1).finish()  # apply, but hero has no cards

    assert state.entity_locations.get("hero_arien") is not None  # not defeated


def test_ultimate_once_per_turn_can_be_saved_for_ground_shaker_repeat() -> None:
    # Ground Shaker places a rock per group. Declining the first offer saves the
    # single use for the repeat's offer.
    state = (
        EffectScenarioBuilder()
        .with_hexes(_hex_disk(3))
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "ground_shaker"))
        .blue_hero("hero_arien", at=(2, 0, -2))
        .blue_hero("hero_bain", at=(-2, 0, 2))
        .blue_minion("blue_minion_a", at=(1, 0, -1))
        .blue_minion("blue_minion_b", at=(-1, 0, 1))
        .with_actor("hero_mrak")
        .build()
    )
    mrak = state.get_hero("hero_mrak")
    mrak.level = 8
    mrak.ultimate_card = hero_card("Mrak", "rock_and_a_hard_place")
    # Terrain that makes each minion selectable, positioned away from the heroes.
    state.board.tiles[Hex(q=1, r=-1, s=0)].is_terrain = True
    state.board.tiles[Hex(q=-1, r=1, s=0)].is_terrain = True
    _add_rock_pool(state)
    arien = state.get_hero("hero_arien")  # near minion_a's vacated hex
    bain = state.get_hero("hero_bain")  # near minion_b's vacated hex
    arien.hand = [hero_card("Mrak", "boulder_rush")]
    bain.hand = [hero_card("Mrak", "boulder_blitz")]

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("SKILL").expect_input(InputRequestType.SELECT_UNIT)
    run.choose("blue_minion_a").expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 0, "r": 1, "s": -1}).expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(0).expect_input(InputRequestType.SELECT_OPTION)  # decline ultimate (save it)
    run.choose("YES").expect_input(InputRequestType.SELECT_UNIT)  # repeat
    run.choose("blue_minion_b").expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 0, "r": -1, "s": 1}).expect_input(InputRequestType.SELECT_NUMBER)
    run.choose(1).expect_input(InputRequestType.SELECT_CARD)  # apply on the second group
    run.choose("boulder_blitz").finish()

    assert len(arien.hand) == 1  # first hero untouched (use was saved)
    assert len(bain.hand) == 0  # second hero discarded


# =============================================================================
# Stone Carapace / Rock Solid: primary Move 4 that activates a this-round
# discard-shield. "This round: If you would discard a card from your hand, you
# may discard this card instead; you may discard this card to perform its
# defense action, as if it was in your hand." Rock Solid also retrieves a card.
# =============================================================================


def _shield_effects(state):
    from goa2.domain.models.effect import EffectType

    return [e for e in state.active_effects if e.effect_type == EffectType.DISCARD_SHIELD]


def test_stone_carapace_moves_and_activates_discard_shield() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=6)
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "stone_carapace"))
        .with_actor("hero_mrak")
        .build()
    )

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("MOVEMENT").expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 3, "r": 0, "s": -3}).finish()

    assert state.entity_locations.get("hero_mrak") == Hex(q=3, r=0, s=-3)
    shields = _shield_effects(state)
    assert len(shields) == 1
    assert shields[0].source_card_id == "stone_carapace"


def test_rock_solid_retrieves_a_card_and_activates_shield() -> None:
    state = (
        EffectScenarioBuilder()
        .line_board(length=6)
        .red_hero("hero_mrak", at=(0, 0, 0), current_card=hero_card("Mrak", "rock_solid"))
        .with_actor("hero_mrak")
        .build()
    )
    mrak = state.get_hero("hero_mrak")
    retrievable = hero_card("Mrak", "seismic_slam")
    mrak.discard_pile = [retrievable]

    run = run_card(state, "hero_mrak")
    run.expect_input(InputRequestType.CHOOSE_ACTION)
    run.choose("MOVEMENT").expect_input(InputRequestType.SELECT_HEX)
    run.choose({"q": 2, "r": 0, "s": -2}).expect_input(InputRequestType.SELECT_CARD)
    run.choose("seismic_slam").finish()

    assert any(c.id == "seismic_slam" for c in mrak.hand)
    assert len(_shield_effects(state)) == 1

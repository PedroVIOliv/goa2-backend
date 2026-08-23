import pytest

from goa2.data.heroes.arien import create_arien
from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardState,
    CardTier,
    GamePhase,
    Hero,
    TeamColor,
)
from goa2.domain.types import HeroID
from goa2.engine.setup import GameSetup


@pytest.fixture
def map_path():
    return "src/goa2/data/maps/forgotten_island.json"


@pytest.fixture
def setup_registry():
    # 1. Register Arien
    HeroRegistry.register(create_arien())

    # 2. Register Dummy Knight
    knight = Hero(
        id=HeroID("hero_knight"),
        name="Knight",
        deck=[
            Card(
                id="k_1",
                name="Slash",
                tier=CardTier.I,
                color=CardColor.RED,
                initiative=5,
                primary_action=ActionType.ATTACK,
                primary_action_value=4,
                effect_id="none",
                effect_text="",
            ),
            Card(
                id="k_2",
                name="Block",
                tier=CardTier.I,
                color=CardColor.BLUE,
                initiative=5,
                primary_action=ActionType.DEFENSE,
                primary_action_value=4,
                effect_id="none",
                effect_text="",
            ),
        ],
        team=TeamColor.BLUE,
    )
    HeroRegistry.register(knight)


def test_full_game_setup(map_path, setup_registry):
    """
    Verifies that create_game correctly initializes the GameState.
    """
    # 1. Create Game with 1v1 (Arien vs Knight)
    red_heroes = ["Arien"]
    blue_heroes = ["Knight"]

    state = GameSetup.create_game(map_path, red_heroes, blue_heroes)

    # 2. Assert Basic State
    assert state.phase == GamePhase.PLANNING
    assert state.round == 1
    assert state.turn == 1
    assert state.active_zone_id == "Mid"

    # 3. Assert Heroes Placed
    red_team = state.teams[TeamColor.RED]
    blue_team = state.teams[TeamColor.BLUE]

    assert len(red_team.heroes) == 1
    assert len(blue_team.heroes) == 1

    red_hero = red_team.heroes[0]
    blue_hero = blue_team.heroes[0]

    assert red_hero.name == "Arien"
    assert blue_hero.name == "Knight"
    assert red_hero.id != blue_hero.id

    # Assert Minions Spawned in Mid
    mid_zone = state.board.zones["Mid"]
    minion_count = 0
    for h in mid_zone.hexes:
        tile = state.board.get_tile(h)
        if tile.occupant_id and "minion" in tile.occupant_id:
            minion_count += 1

    assert minion_count > 0

    # 4. Assert Hand Setup
    # Arien has Tier I and Untiered.
    assert len(red_hero.hand) > 0
    assert len(red_hero.deck) > 0

    for c in red_hero.hand:
        assert c.tier in [CardTier.I, CardTier.UNTIERED]
        assert c.state == CardState.HAND

    # Knight has only Tier I
    assert len(blue_hero.hand) == 2
    assert len(blue_hero.deck) == 2  # Deck acts as master list

    # Verify State Update
    for c in blue_hero.deck:
        assert c.state == CardState.HAND


class TestGameTypeConfig:
    def test_get_game_config_long_4p(self):
        waves, lc = GameSetup.get_game_config("LONG", 4)
        assert waves == 5
        assert lc == 6

    def test_get_game_config_long_5p(self):
        waves, lc = GameSetup.get_game_config("LONG", 5)
        assert waves == 5
        assert lc == 6

    def test_get_game_config_long_6p(self):
        waves, lc = GameSetup.get_game_config("LONG", 6)
        assert waves == 5
        assert lc == 8

    def test_get_game_config_quick_4p(self):
        waves, lc = GameSetup.get_game_config("QUICK", 4)
        assert waves == 3
        assert lc == 4

    def test_get_game_config_quick_5p(self):
        waves, lc = GameSetup.get_game_config("QUICK", 5)
        assert waves == 3
        assert lc == 4

    def test_get_game_config_quick_6p(self):
        waves, lc = GameSetup.get_game_config("QUICK", 6)
        assert waves == 3
        assert lc == 5

    def test_get_game_config_invalid_type(self):
        with pytest.raises(ValueError, match="Invalid game_type"):
            GameSetup.get_game_config("BLITZ", 4)

    def test_get_game_config_uneven_players_uses_upper_life_count(self):
        waves, lc = GameSetup.get_game_config("QUICK", 3)
        assert waves == 3
        assert lc == 4

        waves, lc = GameSetup.get_game_config("LONG", 3)
        assert waves == 5
        assert lc == 6

    def test_get_game_config_unsupported_players_above_max(self):
        with pytest.raises(ValueError, match="Unsupported player count"):
            GameSetup.get_game_config("LONG", 7)


class TestTwoLaneConfig:
    """Two-lane maps: 2 x 7 wave counters; 6 LC (6-8p) / 7 LC (9-10p)."""

    def test_6_players(self):
        assert GameSetup.get_game_config("LONG", 6, lane_count=2) == (7, 6)

    def test_8_players(self):
        assert GameSetup.get_game_config("LONG", 8, lane_count=2) == (7, 6)

    def test_9_players(self):
        assert GameSetup.get_game_config("LONG", 9, lane_count=2) == (7, 7)

    def test_10_players(self):
        assert GameSetup.get_game_config("LONG", 10, lane_count=2) == (7, 7)

    def test_above_10_players_raises(self):
        with pytest.raises(ValueError, match="Unsupported player count"):
            GameSetup.get_game_config("LONG", 11, lane_count=2)

    def test_game_type_does_not_change_two_lane_config(self):
        # The rulebook has no QUICK/LONG split for two-lane maps.
        assert GameSetup.get_game_config("QUICK", 8, lane_count=2) == (
            GameSetup.get_game_config("LONG", 8, lane_count=2)
        )

    def test_game_type_still_validated(self):
        with pytest.raises(ValueError, match="Invalid game_type"):
            GameSetup.get_game_config("BLITZ", 8, lane_count=2)

    def test_small_player_counts_use_next_bracket(self):
        # Below the rulebook minimum (dev/test games): next bracket applies,
        # same as the single-lane uneven-count rule.
        assert GameSetup.get_game_config("LONG", 2, lane_count=2) == (7, 6)

    def test_unsupported_lane_count_raises(self):
        with pytest.raises(ValueError, match="lane count"):
            GameSetup.get_game_config("LONG", 6, lane_count=3)

    def test_lane_count_default_is_single_lane(self):
        assert GameSetup.get_game_config("LONG", 4) == (5, 6)


TWO_LANE_MAP = "src/goa2/data/maps/across_the_river.json"


def _register_dummies(count: int) -> list[str]:
    """Register `count` minimal heroes with globally unique card IDs."""
    names = []
    for i in range(count):
        name = f"Dummy{i + 1}"
        HeroRegistry.register(
            Hero(
                id=HeroID(f"hero_dummy_{i + 1}"),
                name=name,
                deck=[
                    Card(
                        id=f"dummy{i + 1}_slash",
                        name="Slash",
                        tier=CardTier.I,
                        color=CardColor.RED,
                        initiative=5,
                        primary_action=ActionType.ATTACK,
                        primary_action_value=4,
                        effect_id="none",
                        effect_text="",
                    ),
                ],
                team=TeamColor.RED,
            )
        )
        names.append(name)
    return names


class TestTwoLaneGameSetup:
    def test_create_game_uses_two_lane_config(self):
        names = _register_dummies(6)
        state = GameSetup.create_game(TWO_LANE_MAP, names[:3], names[3:])
        assert len(state.board.lanes) == 2
        assert state.wave_counters == {lane_id: 7 for lane_id in state.board.lanes}
        for team in state.teams.values():
            assert team.life_counters == 6

    def _assert_heroes_on_spawns_or_adjacent(self, state):
        # Rulebook: extra heroes (>3 per team) are placed in an empty space
        # adjacent to one of their team's occupied hero spawn points.
        from goa2.domain.models.spawn import SpawnType

        for team in state.teams.values():
            spawn_locs = {
                sp.location
                for sp in state.board.spawn_points
                if sp.type == SpawnType.HERO and sp.team == team.color
            }
            for hero in team.heroes:
                pos = state.get_position(hero.id)
                assert pos is not None, f"{hero.name} was not placed on the board"
                assert pos in spawn_locs or any(n in spawn_locs for n in pos.neighbors()), (
                    f"{hero.name} at {pos} is neither on nor adjacent to a "
                    f"{team.color.value} hero spawn point"
                )

    def test_8_players_extra_heroes_placed_adjacent_to_spawns(self):
        # across_the_river has 3 hero spawn points per team; the 4th hero
        # goes to an empty hex adjacent to an occupied spawn point.
        names = _register_dummies(8)
        state = GameSetup.create_game(TWO_LANE_MAP, names[:4], names[4:])
        assert state.wave_counters == {lane_id: 7 for lane_id in state.board.lanes}
        for team in state.teams.values():
            assert team.life_counters == 6
        self._assert_heroes_on_spawns_or_adjacent(state)

    def test_10_players_extra_heroes_placed_adjacent_to_spawns(self):
        names = _register_dummies(10)
        state = GameSetup.create_game(TWO_LANE_MAP, names[:5], names[5:])
        assert state.wave_counters == {lane_id: 7 for lane_id in state.board.lanes}
        for team in state.teams.values():
            assert team.life_counters == 7
        self._assert_heroes_on_spawns_or_adjacent(state)


class TestQuickGameSetup:
    def test_quick_game_2v2(self, map_path, setup_registry):
        red_heroes = ["Arien"]
        blue_heroes = ["Knight"]

        state = GameSetup.create_game(map_path, red_heroes, blue_heroes, game_type="QUICK")

        assert state.wave_counter == 3
        assert state.teams[TeamColor.RED].life_counters == 3
        assert state.teams[TeamColor.BLUE].life_counters == 3

    def test_long_game_default_2v2(self, map_path, setup_registry):
        red_heroes = ["Arien"]
        blue_heroes = ["Knight"]

        state = GameSetup.create_game(map_path, red_heroes, blue_heroes)

        assert state.wave_counter == 5
        assert state.teams[TeamColor.RED].life_counters == 6
        assert state.teams[TeamColor.BLUE].life_counters == 6

    def test_quick_game_case_insensitive(self, map_path, setup_registry):
        red_heroes = ["Arien"]
        blue_heroes = ["Knight"]

        with pytest.raises(ValueError):
            GameSetup.create_game(map_path, red_heroes, blue_heroes, game_type="quick")


class TestConfiguredBattleZones:
    def _map_with_battle_zones(self, tmp_path, battle_zones: dict) -> str:
        import json
        from pathlib import Path

        data = json.loads(Path("src/goa2/data/maps/forgotten_island.json").read_text())
        data["battle_zones"] = battle_zones
        p = tmp_path / "map.json"
        p.write_text(json.dumps(data))
        return str(p)

    def test_setup_uses_configured_battle_zone(self, setup_registry, tmp_path):
        map_path = self._map_with_battle_zones(tmp_path, {"lane_1": "RedBeach"})
        state = GameSetup.create_game(map_path, ["Arien"], ["Knight"])
        assert state.battle_zones["lane_1"] == "RedBeach"

    def test_setup_defaults_to_lane_center_without_config(self, map_path, setup_registry):
        state = GameSetup.create_game(map_path, ["Arien"], ["Knight"])
        lane = state.board.lanes["lane_1"]
        assert state.battle_zones["lane_1"] == lane[len(lane) // 2]


def test_rogue_definition():
    """
    Verifies the Rogue hero is loaded correctly with the updated 5-card deck.
    """
    from goa2.data.heroes.rogue import create_rogue

    rogue = create_rogue()

    assert len(rogue.deck) == 5
    initiatives = sorted([c.initiative for c in rogue.deck], reverse=True)
    assert initiatives == [8, 7, 6, 5, 4]

    for c in rogue.deck:
        assert c.primary_action == ActionType.SKILL
        assert c.secondary_actions[ActionType.DEFENSE] == 2
        assert c.secondary_actions[ActionType.ATTACK] == 2
        assert c.secondary_actions[ActionType.MOVEMENT] == 2


@pytest.mark.parametrize(
    ("seed", "expected"),
    [(0, TeamColor.BLUE), (1, TeamColor.RED)],
)
def test_tie_breaker_flip_is_seeded_when_not_supplied(map_path, setup_registry, seed, expected):
    state = GameSetup.create_game(map_path, ["Arien"], ["Knight"], seed=seed)
    assert state.tie_breaker_team is expected

    repeated = GameSetup.create_game(map_path, ["Arien"], ["Knight"], seed=seed)
    assert repeated.tie_breaker_team is expected


@pytest.mark.parametrize(
    ("team", "seed"),
    [(TeamColor.RED, 0), (TeamColor.BLUE, 1)],
)
def test_supplied_tie_breaker_team_overrides_the_flip(map_path, setup_registry, team, seed):
    """A draft's coin flip is the match's coin flip, so callers may hand in its result."""
    state = GameSetup.create_game(map_path, ["Arien"], ["Knight"], seed=seed, tie_breaker_team=team)
    assert state.tie_breaker_team is team

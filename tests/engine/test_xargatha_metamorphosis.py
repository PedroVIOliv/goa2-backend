"""Tests for Xargatha's Metamorphosis ultimate effect (aura system)."""

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.tile import Tile
from goa2.domain.models import (
    Team,
    TeamColor,
    Card,
    CardTier,
    CardColor,
    ActionType,
    Hero,
    Minion,
    MinionType,
    StatType,
)
from goa2.domain.hex import Hex
from goa2.engine.stats import get_computed_stat
from goa2.engine.rules import validate_movement_path
from goa2.engine.effects import (
    StatAura,
    MovementAura,
    get_active_aura_effects,
    CardEffectRegistry,
)
from goa2.engine.filters import TeamFilter, RangeFilter

# Ensure xargatha effects are registered
import goa2.scripts.xargatha_effects  # noqa: F401


def _make_ultimate_card(effect_id: str = "metamorphosis") -> Card:
    return Card(
        id="xarg_ultimate",
        name="Metamorphosis",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        primary_action=ActionType.SKILL,
        effect_id=effect_id,
        effect_text="Gain +1 Movement and +1 Initiative for each enemy unit adjacent to you. You may move through obstacles.",
        initiative=0,
        is_facedown=False,
    )


def _make_board_with_hexes(*hexes: Hex) -> Board:
    board = Board()
    for h in hexes:
        board.tiles[h] = Tile(hex=h)
    return board


@pytest.fixture
def metamorphosis_state():
    """Xargatha at center with 2 adjacent enemies, 1 friendly adjacent."""
    center = Hex(q=0, r=0, s=0)
    adj1 = Hex(q=1, r=0, s=-1)
    adj2 = Hex(q=0, r=1, s=-1)
    adj3 = Hex(q=-1, r=1, s=0)
    far = Hex(q=2, r=0, s=-2)

    board = _make_board_with_hexes(center, adj1, adj2, adj3, far)

    xargatha = Hero(
        id="hero_xargatha",
        name="Xargatha",
        team=TeamColor.RED,
        deck=[],
        level=8,
        ultimate_card=_make_ultimate_card(),
    )
    enemy1 = Minion(
        id="enemy_m1", name="EnemyMelee", team=TeamColor.BLUE, type=MinionType.MELEE
    )
    enemy2 = Minion(
        id="enemy_m2", name="EnemyRanged", team=TeamColor.BLUE, type=MinionType.RANGED
    )
    ally = Minion(
        id="ally_m1", name="AllyMelee", team=TeamColor.RED, type=MinionType.MELEE
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(
                color=TeamColor.RED, heroes=[xargatha], minions=[ally]
            ),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[], minions=[enemy1, enemy2]
            ),
        },
        entity_locations={},
        current_actor_id="hero_xargatha",
    )
    state.place_entity("hero_xargatha", center)
    state.place_entity("enemy_m1", adj1)
    state.place_entity("enemy_m2", adj2)
    state.place_entity("ally_m1", adj3)
    return state


class TestMetamorphosisStatAuras:
    def test_movement_bonus_with_adjacent_enemies(self, metamorphosis_state):
        """2 adjacent enemies → +2 Movement."""
        result = get_computed_stat(
            metamorphosis_state, "hero_xargatha", StatType.MOVEMENT, base_value=3
        )
        assert result == 5  # 3 base + 2 enemies

    def test_initiative_bonus_with_adjacent_enemies(self, metamorphosis_state):
        """2 adjacent enemies → +2 Initiative."""
        result = get_computed_stat(
            metamorphosis_state, "hero_xargatha", StatType.INITIATIVE, base_value=0
        )
        assert result == 2  # 0 base + 2 enemies

    def test_no_bonus_at_low_level(self, metamorphosis_state):
        """Level < 8 → ultimate not active, no aura bonus."""
        hero = metamorphosis_state.get_hero("hero_xargatha")
        hero.level = 7
        result = get_computed_stat(
            metamorphosis_state, "hero_xargatha", StatType.MOVEMENT, base_value=3
        )
        assert result == 3  # No bonus

    def test_no_bonus_when_isolated(self):
        """No adjacent enemies → 0 bonus."""
        center = Hex(q=0, r=0, s=0)
        board = _make_board_with_hexes(center)
        xargatha = Hero(
            id="hero_xargatha",
            name="Xargatha",
            team=TeamColor.RED,
            deck=[],
            level=8,
            ultimate_card=_make_ultimate_card(),
        )
        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(
                    color=TeamColor.RED, heroes=[xargatha], minions=[]
                ),
                TeamColor.BLUE: Team(
                    color=TeamColor.BLUE, heroes=[], minions=[]
                ),
            },
            entity_locations={},
            current_actor_id="hero_xargatha",
        )
        state.place_entity("hero_xargatha", center)
        result = get_computed_stat(
            state, "hero_xargatha", StatType.MOVEMENT, base_value=3
        )
        assert result == 3  # No bonus

    def test_friendly_units_dont_count(self, metamorphosis_state):
        """Only enemies contribute to aura count, not friendlies."""
        # ally_m1 is adjacent but friendly — shouldn't count
        # Movement should be 3 + 2 (only the 2 enemies)
        result = get_computed_stat(
            metamorphosis_state, "hero_xargatha", StatType.MOVEMENT, base_value=3
        )
        assert result == 5  # Only 2 enemies count

    def test_non_adjacent_enemies_dont_count(self, metamorphosis_state):
        """Enemies beyond range 1 don't count."""
        far = Hex(q=2, r=0, s=-2)
        enemy_far = Minion(
            id="enemy_far", name="FarEnemy", team=TeamColor.BLUE, type=MinionType.MELEE
        )
        metamorphosis_state.teams[TeamColor.BLUE].minions.append(enemy_far)
        metamorphosis_state.place_entity("enemy_far", far)

        result = get_computed_stat(
            metamorphosis_state, "hero_xargatha", StatType.MOVEMENT, base_value=3
        )
        assert result == 5  # Still only 2 adjacent enemies

    def test_attack_stat_unaffected(self, metamorphosis_state):
        """Metamorphosis only affects MOVEMENT and INITIATIVE, not ATTACK."""
        result = get_computed_stat(
            metamorphosis_state, "hero_xargatha", StatType.ATTACK, base_value=3
        )
        assert result == 3  # No aura bonus for attack


class TestMetamorphosisMovementAura:
    def test_pass_through_obstacles(self):
        """validate_movement_path with pass_through_obstacles=True allows pathing through obstacles."""
        # Layout: start -> obstacle -> end
        start = Hex(q=0, r=0, s=0)
        obstacle_hex = Hex(q=1, r=0, s=-1)
        end = Hex(q=2, r=0, s=-2)

        board = Board()
        board.tiles[start] = Tile(hex=start)
        board.tiles[obstacle_hex] = Tile(hex=obstacle_hex, is_terrain=True)
        board.tiles[end] = Tile(hex=end)

        # Without pass_through: blocked
        assert not validate_movement_path(
            board=board, start=start, end=end, max_steps=2
        )

        # With pass_through: allowed
        assert validate_movement_path(
            board=board,
            start=start,
            end=end,
            max_steps=2,
            pass_through_obstacles=True,
        )

    def test_cannot_land_on_obstacle(self):
        """Even with pass_through_obstacles, cannot land on an obstacle."""
        start = Hex(q=0, r=0, s=0)
        obstacle_hex = Hex(q=1, r=0, s=-1)

        board = Board()
        board.tiles[start] = Tile(hex=start)
        board.tiles[obstacle_hex] = Tile(hex=obstacle_hex, is_terrain=True)

        assert not validate_movement_path(
            board=board,
            start=start,
            end=obstacle_hex,
            max_steps=1,
            pass_through_obstacles=True,
        )

    def test_pass_through_obstacles_with_state(self):
        """Topology-aware pathfinding respects pass_through_obstacles."""
        start = Hex(q=0, r=0, s=0)
        obstacle_hex = Hex(q=1, r=0, s=-1)
        end = Hex(q=2, r=0, s=-2)

        board = _make_board_with_hexes(start, end)
        board.tiles[obstacle_hex] = Tile(hex=obstacle_hex, is_terrain=True)

        hero = Hero(id="h1", name="Hero", team=TeamColor.RED, deck=[])
        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
            },
            entity_locations={},
            current_actor_id="h1",
        )
        state.place_entity("h1", start)

        # Without pass_through: blocked (topology path)
        assert not validate_movement_path(
            board=board, start=start, end=end, max_steps=2,
            state=state, actor_id="h1",
        )

        # With pass_through: allowed (topology path)
        assert validate_movement_path(
            board=board, start=start, end=end, max_steps=2,
            state=state, actor_id="h1",
            pass_through_obstacles=True,
        )


class TestGetActiveAuraEffects:
    def test_returns_ultimate_aura_at_level_8(self, metamorphosis_state):
        hero = metamorphosis_state.get_hero("hero_xargatha")
        results = get_active_aura_effects(metamorphosis_state, hero)
        assert len(results) == 1
        card, effect = results[0]
        assert card.id == "xarg_ultimate"
        assert len(effect.get_stat_auras()) == 2

    def test_returns_empty_below_level_8(self, metamorphosis_state):
        hero = metamorphosis_state.get_hero("hero_xargatha")
        hero.level = 7
        results = get_active_aura_effects(metamorphosis_state, hero)
        assert len(results) == 0

    def test_metamorphosis_effect_registered(self):
        effect = CardEffectRegistry.get("metamorphosis")
        assert effect is not None
        assert len(effect.get_stat_auras()) == 2
        aura = effect.get_movement_aura()
        assert aura is not None
        assert aura.pass_through_obstacles is True

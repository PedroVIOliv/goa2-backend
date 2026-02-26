"""
Tests for Xargatha's adjacency-bonus attack cards:
- Threatening Slash: +1 Attack per other adjacent enemy
- Deadly Swipe: +2 Attack per other adjacent enemy
- Lethal Spin: +3 Attack per other adjacent enemy

All use CountAdjacentEnemiesStep -> AttackSequenceStep(damage_bonus_key=...).
The bonus is computed at resolve time, not build time.
"""

from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Minion,
    MinionType,
    Card,
    CardTier,
    CardColor,
    ActionType,
    StatType,
)
from goa2.domain.hex import Hex
from goa2.engine.effects import CardEffectRegistry
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.steps import ResolveCardStep

# Register xargatha effects
import goa2.scripts.xargatha_effects  # noqa: F401


def make_threatening_slash_card():
    return Card(
        id="threatening_slash",
        name="Threatening Slash",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=7,
        primary_action=ActionType.ATTACK,
        primary_action_value=5,
        effect_id="threatening_slash",
        effect_text="Target a unit adjacent to you. +1 Attack for each other enemy unit adjacent to you.",
        is_facedown=False,
    )


def make_deadly_swipe_card():
    return Card(
        id="deadly_swipe",
        name="Deadly Swipe",
        tier=CardTier.II,
        color=CardColor.RED,
        initiative=8,
        primary_action=ActionType.ATTACK,
        primary_action_value=5,
        item=StatType.INITIATIVE,
        effect_id="deadly_swipe",
        effect_text="Target a unit adjacent to you. +2 Attack for each other enemy unit adjacent to you.",
        is_facedown=False,
    )


def make_lethal_spin_card():
    return Card(
        id="lethal_spin",
        name="Lethal Spin",
        tier=CardTier.III,
        color=CardColor.RED,
        initiative=8,
        primary_action=ActionType.ATTACK,
        primary_action_value=5,
        item=StatType.RADIUS,
        effect_id="lethal_spin",
        effect_text="Target a unit adjacent to you. +3 Attack for each other enemy unit adjacent to you.",
        is_facedown=False,
    )


def _make_state(adjacent_enemy_count: int) -> GameState:
    """
    Create a state with Xargatha at origin and N adjacent enemies.
    """
    adjacent_hexes = [
        Hex(q=1, r=0, s=-1),
        Hex(q=0, r=1, s=-1),
        Hex(q=-1, r=0, s=1),
        Hex(q=0, r=-1, s=1),
        Hex(q=1, r=-1, s=0),
        Hex(q=-1, r=1, s=0),
    ]

    board = Board()
    hexes = {Hex(q=0, r=0, s=0)} | set(adjacent_hexes[:adjacent_enemy_count])
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    xargatha = Hero(
        id="xargatha", name="Xargatha", team=TeamColor.RED, deck=[], level=1
    )

    enemies_heroes = []
    enemies_minions = []
    for i in range(adjacent_enemy_count):
        if i % 2 == 0:
            m = Minion(
                id=f"enemy_{i}",
                name=f"Enemy {i}",
                type=MinionType.MELEE,
                team=TeamColor.BLUE,
            )
            enemies_minions.append(m)
        else:
            h = Hero(
                id=f"enemy_{i}",
                name=f"Enemy {i}",
                team=TeamColor.BLUE,
                deck=[],
                level=1,
            )
            enemies_heroes.append(h)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[xargatha], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE,
                heroes=enemies_heroes,
                minions=enemies_minions,
            ),
        },
    )

    state.place_entity("xargatha", Hex(q=0, r=0, s=0))
    for i in range(adjacent_enemy_count):
        state.place_entity(f"enemy_{i}", adjacent_hexes[i])

    state.current_actor_id = "xargatha"
    return state


# =============================================================================
# Threatening Slash Tests (+1 per adjacent enemy)
# =============================================================================


class TestThreateningSlashEffect:
    def test_registered(self):
        assert CardEffectRegistry.get("threatening_slash") is not None

    def test_returns_count_then_attack(self):
        """Returns CountAdjacentEnemiesStep + AttackSequenceStep."""
        state = _make_state(1)
        xargatha = state.get_hero("xargatha")
        card = make_threatening_slash_card()
        xargatha.current_turn_card = card

        effect = CardEffectRegistry.get("threatening_slash")
        steps = effect.get_steps(state, xargatha, card)

        assert len(steps) == 2
        assert steps[0].__class__.__name__ == "CountAdjacentEnemiesStep"
        assert steps[1].__class__.__name__ == "AttackSequenceStep"

    def test_count_step_config(self):
        """Count step uses multiplier=1, subtract=1 for 'other' enemies."""
        state = _make_state(1)
        xargatha = state.get_hero("xargatha")
        card = make_threatening_slash_card()
        xargatha.current_turn_card = card

        effect = CardEffectRegistry.get("threatening_slash")
        steps = effect.get_steps(state, xargatha, card)

        count_step = steps[0]
        assert count_step.multiplier == 1
        assert count_step.subtract == 1

    def test_attack_reads_bonus_from_context(self):
        """Attack step has damage_bonus_key pointing to context."""
        state = _make_state(1)
        xargatha = state.get_hero("xargatha")
        card = make_threatening_slash_card()
        xargatha.current_turn_card = card

        effect = CardEffectRegistry.get("threatening_slash")
        steps = effect.get_steps(state, xargatha, card)

        attack_step = steps[1]
        assert attack_step.damage == 5  # Base damage
        assert attack_step.damage_bonus_key == "adj_atk_bonus"

    def test_attack_range_is_adjacent(self):
        """Threatening Slash is always range 1."""
        state = _make_state(3)
        xargatha = state.get_hero("xargatha")
        card = make_threatening_slash_card()
        xargatha.current_turn_card = card

        effect = CardEffectRegistry.get("threatening_slash")
        steps = effect.get_steps(state, xargatha, card)

        assert steps[1].range_val == 1

    def test_full_flow_bonus_computed_at_resolve(self):
        """Full execution: bonus is computed dynamically during resolution."""
        state = _make_state(3)
        xargatha = state.get_hero("xargatha")
        card = make_threatening_slash_card()
        xargatha.current_turn_card = card

        step = ResolveCardStep(hero_id="xargatha")
        push_steps(state, [step])

        # 1. CHOOSE_ACTION
        process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        # 2. Count step runs, then SELECT_UNIT for attack target
        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_UNIT"

        # With 3 adjacent enemies, bonus = (3-1)*1 = 2, so damage = 5+2 = 7
        # The bonus is in context now
        assert state.execution_context.get("adj_atk_bonus") == 2

    def test_friendly_units_not_counted(self):
        """Friendly adjacent units should NOT contribute to the bonus."""
        board = Board()
        hexes = {
            Hex(q=0, r=0, s=0),
            Hex(q=1, r=0, s=-1),  # Enemy
            Hex(q=0, r=1, s=-1),  # Friendly
        }
        z1 = Zone(id="z1", hexes=hexes, neighbors=[])
        board.zones = {"z1": z1}
        board.populate_tiles_from_zones()

        xargatha = Hero(
            id="xargatha", name="Xargatha", team=TeamColor.RED, deck=[], level=1
        )
        friendly = Minion(
            id="friendly_minion",
            name="Friendly",
            type=MinionType.MELEE,
            team=TeamColor.RED,
        )
        enemy = Minion(
            id="enemy_0",
            name="Enemy",
            type=MinionType.MELEE,
            team=TeamColor.BLUE,
        )

        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(
                    color=TeamColor.RED, heroes=[xargatha], minions=[friendly]
                ),
                TeamColor.BLUE: Team(
                    color=TeamColor.BLUE, heroes=[], minions=[enemy]
                ),
            },
        )

        state.place_entity("xargatha", Hex(q=0, r=0, s=0))
        state.place_entity("enemy_0", Hex(q=1, r=0, s=-1))
        state.place_entity("friendly_minion", Hex(q=0, r=1, s=-1))
        state.current_actor_id = "xargatha"

        card = make_threatening_slash_card()
        xargatha.current_turn_card = card

        # Run through to check the bonus
        step = ResolveCardStep(hero_id="xargatha")
        push_steps(state, [step])

        process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        process_resolution_stack(state)
        # Only 1 enemy adjacent, subtract 1 -> bonus = 0
        assert state.execution_context.get("adj_atk_bonus") == 0


# =============================================================================
# Deadly Swipe Tests (+2 per adjacent enemy)
# =============================================================================


class TestDeadlySwipeEffect:
    def test_registered(self):
        assert CardEffectRegistry.get("deadly_swipe") is not None

    def test_count_step_uses_multiplier_2(self):
        state = _make_state(1)
        xargatha = state.get_hero("xargatha")
        card = make_deadly_swipe_card()
        xargatha.current_turn_card = card

        effect = CardEffectRegistry.get("deadly_swipe")
        steps = effect.get_steps(state, xargatha, card)

        assert steps[0].multiplier == 2
        assert steps[0].subtract == 1

    def test_full_flow_bonus_with_three_adjacent(self):
        """3 adjacent enemies -> bonus = (3-1)*2 = 4."""
        state = _make_state(3)
        xargatha = state.get_hero("xargatha")
        card = make_deadly_swipe_card()
        xargatha.current_turn_card = card

        step = ResolveCardStep(hero_id="xargatha")
        push_steps(state, [step])

        process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        process_resolution_stack(state)
        assert state.execution_context.get("adj_atk_bonus") == 4

    def test_attack_range_is_adjacent(self):
        state = _make_state(1)
        xargatha = state.get_hero("xargatha")
        card = make_deadly_swipe_card()
        xargatha.current_turn_card = card

        effect = CardEffectRegistry.get("deadly_swipe")
        steps = effect.get_steps(state, xargatha, card)

        assert steps[1].range_val == 1


# =============================================================================
# Lethal Spin Tests (+3 per adjacent enemy)
# =============================================================================


class TestLethalSpinEffect:
    def test_registered(self):
        assert CardEffectRegistry.get("lethal_spin") is not None

    def test_count_step_uses_multiplier_3(self):
        state = _make_state(1)
        xargatha = state.get_hero("xargatha")
        card = make_lethal_spin_card()
        xargatha.current_turn_card = card

        effect = CardEffectRegistry.get("lethal_spin")
        steps = effect.get_steps(state, xargatha, card)

        assert steps[0].multiplier == 3
        assert steps[0].subtract == 1

    def test_full_flow_bonus_with_three_adjacent(self):
        """3 adjacent enemies -> bonus = (3-1)*3 = 6."""
        state = _make_state(3)
        xargatha = state.get_hero("xargatha")
        card = make_lethal_spin_card()
        xargatha.current_turn_card = card

        step = ResolveCardStep(hero_id="xargatha")
        push_steps(state, [step])

        process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        process_resolution_stack(state)
        assert state.execution_context.get("adj_atk_bonus") == 6

    def test_full_flow_bonus_with_six_adjacent(self):
        """6 adjacent enemies -> bonus = (6-1)*3 = 15."""
        state = _make_state(6)
        xargatha = state.get_hero("xargatha")
        card = make_lethal_spin_card()
        xargatha.current_turn_card = card

        step = ResolveCardStep(hero_id="xargatha")
        push_steps(state, [step])

        process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        process_resolution_stack(state)
        assert state.execution_context.get("adj_atk_bonus") == 15

    def test_attack_range_is_adjacent(self):
        state = _make_state(1)
        xargatha = state.get_hero("xargatha")
        card = make_lethal_spin_card()
        xargatha.current_turn_card = card

        effect = CardEffectRegistry.get("lethal_spin")
        steps = effect.get_steps(state, xargatha, card)

        assert steps[1].range_val == 1

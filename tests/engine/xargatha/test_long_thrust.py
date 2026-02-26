"""
Tests for Xargatha's range-bonus attack cards:
- Long Thrust: +1 Range per adjacent enemy
- Rapid Thrusts: +1 Range per adjacent enemy + repeat on different hero

Both use CountAdjacentEnemiesStep -> AttackSequenceStep(range_bonus_key=...).
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
from goa2.engine.steps import ResolveCardStep
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.effects import CardEffectRegistry

# Register xargatha effects
import goa2.scripts.xargatha_effects  # noqa: F401


def make_long_thrust_card():
    return Card(
        id="long_thrust",
        name="Long Thrust",
        tier=CardTier.II,
        color=CardColor.RED,
        initiative=8,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        is_ranged=True,
        range_value=1,
        item=StatType.DEFENSE,
        effect_id="long_thrust",
        effect_text="Target a unit in range. +1 Range for each enemy unit adjacent to you.",
        is_facedown=False,
    )


def make_rapid_thrusts_card():
    return Card(
        id="rapid_thrusts",
        name="Rapid Thrusts",
        tier=CardTier.III,
        color=CardColor.RED,
        initiative=8,
        primary_action=ActionType.ATTACK,
        primary_action_value=4,
        is_ranged=True,
        range_value=1,
        item=StatType.MOVEMENT,
        effect_id="rapid_thrusts",
        effect_text="Target a unit in range. +1 Range for each enemy unit adjacent to you. May repeat once on a different enemy hero.",
        is_facedown=False,
    )


def _make_range_state(
    adjacent_enemy_count: int, distant_enemies: bool = False
) -> GameState:
    """
    Create a state with Xargatha at origin, N adjacent enemies,
    and optionally enemies at range 2 for targeting.
    """
    adjacent_hexes = [
        Hex(q=1, r=0, s=-1),
        Hex(q=0, r=1, s=-1),
        Hex(q=-1, r=0, s=1),
        Hex(q=0, r=-1, s=1),
        Hex(q=1, r=-1, s=0),
        Hex(q=-1, r=1, s=0),
    ]
    distant_hexes = [
        Hex(q=2, r=0, s=-2),
        Hex(q=0, r=2, s=-2),
    ]

    board = Board()
    hexes = {Hex(q=0, r=0, s=0)} | set(adjacent_hexes[:adjacent_enemy_count])
    if distant_enemies:
        hexes |= set(distant_hexes)
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    xargatha = Hero(
        id="xargatha", name="Xargatha", team=TeamColor.RED, deck=[], level=1
    )

    enemies_heroes = []
    enemies_minions = []

    for i in range(adjacent_enemy_count):
        m = Minion(
            id=f"adj_enemy_{i}",
            name=f"Adj Enemy {i}",
            type=MinionType.MELEE,
            team=TeamColor.BLUE,
        )
        enemies_minions.append(m)

    if distant_enemies:
        for label in ["distant_hero_a", "distant_hero_b"]:
            h = Hero(id=label, name=label, team=TeamColor.BLUE, deck=[], level=1)
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
        state.place_entity(f"adj_enemy_{i}", adjacent_hexes[i])

    if distant_enemies:
        state.place_entity("distant_hero_a", distant_hexes[0])
        state.place_entity("distant_hero_b", distant_hexes[1])

    state.current_actor_id = "xargatha"
    return state


# =============================================================================
# Long Thrust Tests
# =============================================================================


class TestLongThrustEffect:
    def test_registered(self):
        assert CardEffectRegistry.get("long_thrust") is not None

    def test_returns_count_then_attack(self):
        """Long Thrust: CountAdjacentEnemiesStep + AttackSequenceStep."""
        state = _make_range_state(1)
        xargatha = state.get_hero("xargatha")
        card = make_long_thrust_card()
        xargatha.current_turn_card = card

        effect = CardEffectRegistry.get("long_thrust")
        steps = effect.get_steps(state, xargatha, card)

        assert len(steps) == 2
        assert steps[0].__class__.__name__ == "CountAdjacentEnemiesStep"
        assert steps[1].__class__.__name__ == "AttackSequenceStep"

    def test_count_step_no_subtract(self):
        """Long Thrust counts ALL adjacent enemies (no subtract for target)."""
        state = _make_range_state(1)
        xargatha = state.get_hero("xargatha")
        card = make_long_thrust_card()
        xargatha.current_turn_card = card

        effect = CardEffectRegistry.get("long_thrust")
        steps = effect.get_steps(state, xargatha, card)

        assert steps[0].subtract == 0
        assert steps[0].multiplier == 1

    def test_attack_reads_range_bonus_from_context(self):
        """Attack step has range_bonus_key pointing to context."""
        state = _make_range_state(1)
        xargatha = state.get_hero("xargatha")
        card = make_long_thrust_card()
        xargatha.current_turn_card = card

        effect = CardEffectRegistry.get("long_thrust")
        steps = effect.get_steps(state, xargatha, card)

        attack_step = steps[1]
        assert attack_step.range_val == 1  # Base range
        assert attack_step.range_bonus_key == "adj_rng_bonus"
        assert attack_step.damage == 3

    def test_full_flow_range_bonus_with_three_adjacent(self):
        """3 adjacent enemies -> range bonus = 3, total range = 1+3 = 4."""
        state = _make_range_state(3, distant_enemies=True)
        xargatha = state.get_hero("xargatha")
        card = make_long_thrust_card()
        xargatha.current_turn_card = card

        step = ResolveCardStep(hero_id="xargatha")
        push_steps(state, [step])

        process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_UNIT"
        assert state.execution_context.get("adj_rng_bonus") == 3

    def test_full_flow_range_bonus_zero_adjacent(self):
        """0 adjacent enemies -> range bonus = 0, total range = 1."""
        state = _make_range_state(0, distant_enemies=True)
        xargatha = state.get_hero("xargatha")
        card = make_long_thrust_card()
        xargatha.current_turn_card = card

        step = ResolveCardStep(hero_id="xargatha")
        push_steps(state, [step])

        process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        process_resolution_stack(state)
        assert state.execution_context.get("adj_rng_bonus") == 0


# =============================================================================
# Rapid Thrusts Tests
# =============================================================================


class TestRapidThrustsEffect:
    def test_registered(self):
        assert CardEffectRegistry.get("rapid_thrusts") is not None

    def test_returns_count_attack_repeat(self):
        """Rapid Thrusts: Count + Attack + MayRepeat."""
        state = _make_range_state(1)
        xargatha = state.get_hero("xargatha")
        card = make_rapid_thrusts_card()
        xargatha.current_turn_card = card

        effect = CardEffectRegistry.get("rapid_thrusts")
        steps = effect.get_steps(state, xargatha, card)

        assert len(steps) == 3
        assert steps[0].__class__.__name__ == "CountAdjacentEnemiesStep"
        assert steps[1].__class__.__name__ == "AttackSequenceStep"
        assert steps[2].__class__.__name__ == "MayRepeatOnceStep"

    def test_repeat_recounts_adjacent_enemies(self):
        """Repeat template starts with CountAdjacentEnemiesStep."""
        state = _make_range_state(1, distant_enemies=True)
        xargatha = state.get_hero("xargatha")
        card = make_rapid_thrusts_card()
        xargatha.current_turn_card = card

        effect = CardEffectRegistry.get("rapid_thrusts")
        steps = effect.get_steps(state, xargatha, card)

        repeat_step = steps[2]
        repeat_template = repeat_step.steps_template

        # First step in repeat should recount
        assert repeat_template[0].__class__.__name__ == "CountAdjacentEnemiesStep"
        # Then attack with target_filters
        assert repeat_template[1].__class__.__name__ == "AttackSequenceStep"

    def test_repeat_attack_uses_range_bonus_key(self):
        """Both main and repeat attacks read range from context."""
        state = _make_range_state(1, distant_enemies=True)
        xargatha = state.get_hero("xargatha")
        card = make_rapid_thrusts_card()
        xargatha.current_turn_card = card

        effect = CardEffectRegistry.get("rapid_thrusts")
        steps = effect.get_steps(state, xargatha, card)

        main_attack = steps[1]
        repeat_attack = steps[2].steps_template[1]

        assert main_attack.range_bonus_key == "adj_rng_bonus"
        assert repeat_attack.range_bonus_key == "adj_rng_bonus"

    def test_repeat_targets_heroes_only(self):
        """Repeat attack should only target enemy heroes."""
        state = _make_range_state(1, distant_enemies=True)
        xargatha = state.get_hero("xargatha")
        card = make_rapid_thrusts_card()
        xargatha.current_turn_card = card

        effect = CardEffectRegistry.get("rapid_thrusts")
        steps = effect.get_steps(state, xargatha, card)

        repeat_attack = steps[2].steps_template[1]

        has_hero_filter = any(
            f.__class__.__name__ == "UnitTypeFilter" and f.unit_type == "HERO"
            for f in repeat_attack.target_filters
        )
        assert has_hero_filter

    def test_repeat_excludes_first_target(self):
        """Repeat attack must exclude the first target."""
        state = _make_range_state(1, distant_enemies=True)
        xargatha = state.get_hero("xargatha")
        card = make_rapid_thrusts_card()
        xargatha.current_turn_card = card

        effect = CardEffectRegistry.get("rapid_thrusts")
        steps = effect.get_steps(state, xargatha, card)

        repeat_attack = steps[2].steps_template[1]

        has_exclude_filter = any(
            f.__class__.__name__ == "ExcludeIdentityFilter"
            for f in repeat_attack.target_filters
        )
        assert has_exclude_filter

    def test_full_flow_attack_then_repeat(self):
        """Full execution: attack adjacent minion, repeat on distant hero."""
        state = _make_range_state(2, distant_enemies=True)
        xargatha = state.get_hero("xargatha")
        card = make_rapid_thrusts_card()
        xargatha.current_turn_card = card

        step = ResolveCardStep(hero_id="xargatha")
        push_steps(state, [step])

        # 1. CHOOSE_ACTION -> ATTACK
        process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        # 2. Count step runs, then SELECT_UNIT for first target
        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_UNIT"
        assert state.execution_context.get("adj_rng_bonus") == 2
        state.execution_stack[-1].pending_input = {"selection": "adj_enemy_0"}

        # 3. SELECT_OPTION -> repeat? YES
        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_OPTION"
        state.execution_stack[-1].pending_input = {"selection": "YES"}

        # 4. Recount runs, then SELECT_UNIT for repeat target (heroes only)
        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_UNIT"
        # After killing adj_enemy_0, only 1 adjacent enemy left -> bonus = 1
        assert state.execution_context.get("adj_rng_bonus") == 1
        state.execution_stack[-1].pending_input = {"selection": "distant_hero_a"}

        # 5. SELECT_CARD_OR_PASS -> reaction
        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_CARD_OR_PASS"
        state.execution_stack[-1].pending_input = {"selection": "PASS"}

        # 6. Done
        req = process_resolution_stack(state)
        assert req is None

    def test_full_flow_decline_repeat(self):
        """Full execution: attack, then decline repeat."""
        state = _make_range_state(1, distant_enemies=True)
        xargatha = state.get_hero("xargatha")
        card = make_rapid_thrusts_card()
        xargatha.current_turn_card = card

        step = ResolveCardStep(hero_id="xargatha")
        push_steps(state, [step])

        # 1. CHOOSE_ACTION
        process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        # 2. Count + SELECT_UNIT -> first target
        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_UNIT"
        state.execution_stack[-1].pending_input = {"selection": "distant_hero_a"}

        # 3. SELECT_CARD_OR_PASS -> reaction
        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_CARD_OR_PASS"
        state.execution_stack[-1].pending_input = {"selection": "PASS"}

        # 4. SELECT_OPTION -> decline repeat
        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_OPTION"
        state.execution_stack[-1].pending_input = {"selection": "NO"}

        # 5. Done
        req = process_resolution_stack(state)
        assert req is None

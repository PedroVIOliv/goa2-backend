"""
Tests for Xargatha's Cleave card effect.

Card text: "Target a unit adjacent to you. After the attack: May repeat
once on a different enemy hero. (You may repeat even if the original
target was a minion.)"
"""

import pytest
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
)
from goa2.domain.hex import Hex
from goa2.engine.steps import ResolveCardStep
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.effects import CardEffectRegistry

# Register xargatha effects
import goa2.scripts.xargatha_effects  # noqa: F401


def make_cleave_card():
    return Card(
        id="cleave",
        name="Cleave",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=11,
        primary_action=ActionType.ATTACK,
        primary_action_value=4,
        effect_id="cleave",
        effect_text="Target a unit adjacent to you. After the attack: May repeat once on a different enemy hero.",
        is_facedown=False,
    )


@pytest.fixture
def cleave_state():
    """
    Board setup:
    - (0,0,0): Xargatha
    - (1,0,-1): Enemy minion (adjacent)
    - (0,1,-1): Enemy hero A (adjacent)
    - (-1,0,1): Enemy hero B (adjacent)
    """
    board = Board()
    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=0, s=-1),
        Hex(q=0, r=1, s=-1),
        Hex(q=-1, r=0, s=1),
    }
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    xargatha = Hero(
        id="xargatha", name="Xargatha", team=TeamColor.RED, deck=[], level=1
    )
    xargatha.current_turn_card = make_cleave_card()

    enemy_minion = Minion(
        id="enemy_minion", name="Minion", type=MinionType.MELEE, team=TeamColor.BLUE
    )
    enemy_hero_a = Hero(
        id="enemy_hero_a", name="Hero A", team=TeamColor.BLUE, deck=[], level=1
    )
    enemy_hero_b = Hero(
        id="enemy_hero_b", name="Hero B", team=TeamColor.BLUE, deck=[], level=1
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[xargatha], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE,
                heroes=[enemy_hero_a, enemy_hero_b],
                minions=[enemy_minion],
            ),
        },
    )

    state.place_entity("xargatha", Hex(q=0, r=0, s=0))
    state.place_entity("enemy_minion", Hex(q=1, r=0, s=-1))
    state.place_entity("enemy_hero_a", Hex(q=0, r=1, s=-1))
    state.place_entity("enemy_hero_b", Hex(q=-1, r=0, s=1))

    state.current_actor_id = "xargatha"
    return state


class TestCleaveEffect:
    def test_cleave_registered(self):
        effect = CardEffectRegistry.get("cleave")
        assert effect is not None

    def test_cleave_returns_correct_steps(self, cleave_state):
        effect = CardEffectRegistry.get("cleave")
        xargatha = cleave_state.get_hero("xargatha")
        card = make_cleave_card()

        steps = effect.get_steps(cleave_state, xargatha, card)

        assert len(steps) == 2
        assert steps[0].__class__.__name__ == "AttackSequenceStep"
        assert steps[1].__class__.__name__ == "MayRepeatOnceStep"

    def test_cleave_attack_is_adjacent(self, cleave_state):
        """Cleave attack range is 1 (adjacent only)."""
        effect = CardEffectRegistry.get("cleave")
        xargatha = cleave_state.get_hero("xargatha")
        card = make_cleave_card()

        steps = effect.get_steps(cleave_state, xargatha, card)
        assert steps[0].range_val == 1

    def test_cleave_repeat_targets_heroes_only(self, cleave_state):
        """The repeat attack must target only heroes."""
        effect = CardEffectRegistry.get("cleave")
        xargatha = cleave_state.get_hero("xargatha")
        card = make_cleave_card()

        steps = effect.get_steps(cleave_state, xargatha, card)
        repeat_step = steps[1]
        repeat_attack = repeat_step.steps_template[0]

        has_hero_filter = any(
            f.__class__.__name__ == "UnitTypeFilter" and f.unit_type == "HERO"
            for f in repeat_attack.target_filters
        )
        assert has_hero_filter, "Repeat must only target heroes"

    def test_cleave_full_flow_attack_minion_then_repeat_on_hero(self, cleave_state):
        """Attack a minion, then repeat on an enemy hero."""
        step = ResolveCardStep(hero_id="xargatha")
        push_steps(cleave_state, [step])

        # 1. CHOOSE_ACTION -> ATTACK
        process_resolution_stack(cleave_state)
        cleave_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        # 2. SELECT_UNIT -> attack minion
        req = process_resolution_stack(cleave_state)
        assert req["type"] == "SELECT_UNIT"
        cleave_state.execution_stack[-1].pending_input = {"selection": "enemy_minion"}

        # 3. SELECT_OPTION -> repeat? YES
        req = process_resolution_stack(cleave_state)
        assert req["type"] == "SELECT_OPTION"
        cleave_state.execution_stack[-1].pending_input = {"selection": "YES"}

        # 4. SELECT_UNIT -> repeat attack target (heroes only)
        req = process_resolution_stack(cleave_state)
        assert req["type"] == "SELECT_UNIT"
        assert "enemy_hero_a" in req["valid_options"] or "enemy_hero_b" in req["valid_options"]
        cleave_state.execution_stack[-1].pending_input = {"selection": "enemy_hero_a"}

        # 5. SELECT_CARD_OR_PASS -> reaction
        req = process_resolution_stack(cleave_state)
        assert req["type"] == "SELECT_CARD_OR_PASS"
        cleave_state.execution_stack[-1].pending_input = {"selection": "PASS"}

        # 6. Finish
        req = process_resolution_stack(cleave_state)
        assert req is None

    def test_cleave_skip_repeat(self, cleave_state):
        """Can decline the repeat."""
        step = ResolveCardStep(hero_id="xargatha")
        push_steps(cleave_state, [step])

        # 1. CHOOSE_ACTION -> ATTACK
        process_resolution_stack(cleave_state)
        cleave_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        # 2. SELECT_UNIT -> attack hero A
        req = process_resolution_stack(cleave_state)
        cleave_state.execution_stack[-1].pending_input = {"selection": "enemy_hero_a"}

        # 3. SELECT_CARD_OR_PASS -> reaction
        req = process_resolution_stack(cleave_state)
        assert req["type"] == "SELECT_CARD_OR_PASS"
        cleave_state.execution_stack[-1].pending_input = {"selection": "PASS"}

        # 4. SELECT_OPTION -> decline repeat
        req = process_resolution_stack(cleave_state)
        assert req["type"] == "SELECT_OPTION"
        cleave_state.execution_stack[-1].pending_input = {"selection": "NO"}

        # 5. Finish
        req = process_resolution_stack(cleave_state)
        assert req is None

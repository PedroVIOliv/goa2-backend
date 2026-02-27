"""
Tests for Xargatha's Siren's Call card effect.

Card text: "Target an enemy unit not adjacent to you and in range;
if able, move the target up to 3 spaces to a space adjacent to you."
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


def make_sirens_call_card():
    return Card(
        id="sirens_call",
        name="Siren's Call",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=10,
        primary_action=ActionType.ATTACK,
        primary_action_value=0,
        is_ranged=True,
        range_value=3,
        effect_id="sirens_call",
        effect_text="Target an enemy unit not adjacent to you and in range; if able, move the target up to 3 spaces to a space adjacent to you.",
        is_facedown=False,
    )


def _make_sirens_call_state() -> GameState:
    """
    Board setup:
    - (0,0,0): Xargatha
    - (0,2,-2): Distant enemy (not adjacent, range 2)
    - (1,0,-1): Adjacent hex (valid destination)
    - (0,1,-1): Adjacent hex (valid destination)
    - (-1,0,1): Adjacent hex (valid destination)
    """
    board = Board()
    hexes = {
        Hex(q=0, r=0, s=0),
        Hex(q=0, r=2, s=-2),
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
    xargatha.current_turn_card = make_sirens_call_card()

    distant_enemy = Hero(
        id="distant_enemy", name="Distant Enemy", team=TeamColor.BLUE, deck=[], level=1
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[xargatha], minions=[]),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE, heroes=[distant_enemy], minions=[]
            ),
        },
    )

    state.place_entity("xargatha", Hex(q=0, r=0, s=0))
    state.place_entity("distant_enemy", Hex(q=0, r=2, s=-2))

    state.current_actor_id = "xargatha"
    return state


@pytest.fixture
def sirens_call_state():
    return _make_sirens_call_state()


class TestSirensCallEffect:
    def test_registered(self):
        effect = CardEffectRegistry.get("sirens_call")
        assert effect is not None

    def test_returns_correct_steps(self, sirens_call_state):
        effect = CardEffectRegistry.get("sirens_call")
        xargatha = sirens_call_state.get_hero("xargatha")
        card = make_sirens_call_card()

        steps = effect.get_steps(sirens_call_state, xargatha, card)

        assert len(steps) == 3
        assert steps[0].__class__.__name__ == "SelectStep"
        assert steps[1].__class__.__name__ == "SelectStep"
        assert steps[2].__class__.__name__ == "MoveUnitStep"

    def test_target_selection_filters(self, sirens_call_state):
        effect = CardEffectRegistry.get("sirens_call")
        xargatha = sirens_call_state.get_hero("xargatha")
        card = make_sirens_call_card()

        steps = effect.get_steps(sirens_call_state, xargatha, card)
        target_step = steps[0]

        filter_classes = [f.__class__.__name__ for f in target_step.filters]
        assert "TeamFilter" in filter_classes
        assert "RangeFilter" in filter_classes
        assert "ForcedMovementByEnemyFilter" in filter_classes
        assert target_step.is_mandatory is True

    def test_target_selection_not_adjacent(self, sirens_call_state):
        effect = CardEffectRegistry.get("sirens_call")
        xargatha = sirens_call_state.get_hero("xargatha")
        card = make_sirens_call_card()

        steps = effect.get_steps(sirens_call_state, xargatha, card)
        target_step = steps[0]

        range_filter = [
            f for f in target_step.filters if f.__class__.__name__ == "RangeFilter"
        ][0]
        assert range_filter.min_range == 2

    def test_target_selection_in_range(self, sirens_call_state):
        effect = CardEffectRegistry.get("sirens_call")
        xargatha = sirens_call_state.get_hero("xargatha")
        card = make_sirens_call_card()

        steps = effect.get_steps(sirens_call_state, xargatha, card)
        target_step = steps[0]

        range_filter = [
            f for f in target_step.filters if f.__class__.__name__ == "RangeFilter"
        ][0]
        assert range_filter.max_range is not None

    def test_destination_filters(self, sirens_call_state):
        effect = CardEffectRegistry.get("sirens_call")
        xargatha = sirens_call_state.get_hero("xargatha")
        card = make_sirens_call_card()

        steps = effect.get_steps(sirens_call_state, xargatha, card)
        dest_step = steps[1]

        filter_classes = [f.__class__.__name__ for f in dest_step.filters]
        assert "RangeFilter" in filter_classes
        assert "ObstacleFilter" in filter_classes
        assert "MovementPathFilter" in filter_classes
        assert dest_step.is_mandatory is False

    def test_destination_adjacent_to_caster(self, sirens_call_state):
        effect = CardEffectRegistry.get("sirens_call")
        xargatha = sirens_call_state.get_hero("xargatha")
        card = make_sirens_call_card()

        steps = effect.get_steps(sirens_call_state, xargatha, card)
        dest_step = steps[1]

        range_filter = [
            f for f in dest_step.filters if f.__class__.__name__ == "RangeFilter"
        ][0]
        assert range_filter.max_range == 1

    def test_destination_reachable(self, sirens_call_state):
        effect = CardEffectRegistry.get("sirens_call")
        xargatha = sirens_call_state.get_hero("xargatha")
        card = make_sirens_call_card()

        steps = effect.get_steps(sirens_call_state, xargatha, card)
        dest_step = steps[1]

        path_filter = [
            f for f in dest_step.filters if f.__class__.__name__ == "MovementPathFilter"
        ][0]
        assert path_filter.range_val == 3
        assert path_filter.unit_key == "sirens_call_target"

    def test_move_step_config(self, sirens_call_state):
        effect = CardEffectRegistry.get("sirens_call")
        xargatha = sirens_call_state.get_hero("xargatha")
        card = make_sirens_call_card()

        steps = effect.get_steps(sirens_call_state, xargatha, card)
        move_step = steps[2]

        assert move_step.unit_key == "sirens_call_target"
        assert move_step.destination_key == "sirens_call_dest"
        assert move_step.range_val == 3
        assert move_step.is_movement_action is False
        assert move_step.active_if_key == "sirens_call_dest"

    def test_full_flow_select_and_move(self, sirens_call_state):
        step = ResolveCardStep(hero_id="xargatha")
        push_steps(sirens_call_state, [step])

        # 1. CHOOSE_ACTION -> ATTACK
        process_resolution_stack(sirens_call_state)
        sirens_call_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        # 2. SELECT_UNIT -> target distant enemy
        req = process_resolution_stack(sirens_call_state)
        assert req["type"] == "SELECT_UNIT"
        sirens_call_state.execution_stack[-1].pending_input = {
            "selection": "distant_enemy"
        }

        # 3. SELECT_HEX -> select destination adjacent to Xargatha
        req = process_resolution_stack(sirens_call_state)
        assert req["type"] == "SELECT_HEX"
        sirens_call_state.execution_stack[-1].pending_input = {
            "selection": {"q": 1, "r": 0, "s": -1}
        }

        # 4. Done (movement completes)
        req = process_resolution_stack(sirens_call_state)
        assert req is None

        # Verify unit moved
        assert sirens_call_state.entity_locations["distant_enemy"] == Hex(
            q=1, r=0, s=-1
        )

    def test_full_flow_skip_destination(self, sirens_call_state):
        step = ResolveCardStep(hero_id="xargatha")
        push_steps(sirens_call_state, [step])

        # 1. CHOOSE_ACTION -> ATTACK
        process_resolution_stack(sirens_call_state)
        sirens_call_state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        # 2. SELECT_UNIT -> target distant enemy
        req = process_resolution_stack(sirens_call_state)
        assert req["type"] == "SELECT_UNIT"
        sirens_call_state.execution_stack[-1].pending_input = {
            "selection": "distant_enemy"
        }

        # 3. SELECT_HEX -> SKIP (if unable)
        req = process_resolution_stack(sirens_call_state)
        assert req["type"] == "SELECT_HEX"
        sirens_call_state.execution_stack[-1].pending_input = {"selection": "SKIP"}

        # 4. Done (movement step skipped)
        req = process_resolution_stack(sirens_call_state)
        assert req is None

        # Verify unit did not move
        assert sirens_call_state.entity_locations["distant_enemy"] == Hex(
            q=0, r=2, s=-2
        )

    def test_full_flow_no_valid_destination(self):
        board = Board()
        hexes = {
            Hex(q=0, r=0, s=0),
            Hex(q=0, r=4, s=-4),
        }
        z1 = Zone(id="z1", hexes=hexes, neighbors=[])
        board.zones = {"z1": z1}
        board.populate_tiles_from_zones()

        xargatha = Hero(
            id="xargatha", name="Xargatha", team=TeamColor.RED, deck=[], level=1
        )
        xargatha.current_turn_card = make_sirens_call_card()

        distant_enemy = Hero(
            id="distant_enemy",
            name="Distant Enemy",
            team=TeamColor.BLUE,
            deck=[],
            level=1,
        )

        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[xargatha], minions=[]),
                TeamColor.BLUE: Team(
                    color=TeamColor.BLUE, heroes=[distant_enemy], minions=[]
                ),
            },
        )

        state.place_entity("xargatha", Hex(q=0, r=0, s=0))
        state.place_entity("distant_enemy", Hex(q=0, r=4, s=-4))
        state.current_actor_id = "xargatha"

        step = ResolveCardStep(hero_id="xargatha")
        push_steps(state, [step])

        # 1. CHOOSE_ACTION -> ATTACK
        process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        # 2. Mandatory selection fails (no enemy in range) -> action aborts
        req = process_resolution_stack(state)
        assert req is None

        # Verify unit did not move
        assert state.entity_locations["distant_enemy"] == Hex(q=0, r=4, s=-4)

    def test_full_flow_movement_path_validation(self):
        board = Board()
        hexes = {
            Hex(q=0, r=0, s=0),
            Hex(q=0, r=2, s=-2),
            Hex(q=0, r=1, s=-1),
            Hex(q=1, r=0, s=-1),
        }
        z1 = Zone(id="z1", hexes=hexes, neighbors=[])
        board.zones = {"z1": z1}
        board.populate_tiles_from_zones()

        xargatha = Hero(
            id="xargatha", name="Xargatha", team=TeamColor.RED, deck=[], level=1
        )
        xargatha.current_turn_card = make_sirens_call_card()

        distant_enemy = Hero(
            id="distant_enemy",
            name="Distant Enemy",
            team=TeamColor.BLUE,
            deck=[],
            level=1,
        )

        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[xargatha], minions=[]),
                TeamColor.BLUE: Team(
                    color=TeamColor.BLUE, heroes=[distant_enemy], minions=[]
                ),
            },
        )

        state.place_entity("xargatha", Hex(q=0, r=0, s=0))
        state.place_entity("distant_enemy", Hex(q=0, r=2, s=-2))
        state.current_actor_id = "xargatha"

        step = ResolveCardStep(hero_id="xargatha")
        push_steps(state, [step])

        # 1. CHOOSE_ACTION -> ATTACK
        process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

        # 2. SELECT_UNIT -> target distant enemy
        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_UNIT"
        state.execution_stack[-1].pending_input = {"selection": "distant_enemy"}

        # 3. SELECT_HEX -> select adjacent hex (distance 2 from target, within range 3)
        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_HEX"
        state.execution_stack[-1].pending_input = {
            "selection": {"q": 0, "r": 1, "s": -1}
        }

        # 4. Done
        req = process_resolution_stack(state)
        assert req is None

        # Verify unit moved
        assert state.entity_locations["distant_enemy"] == Hex(q=0, r=1, s=-1)

    def test_full_flow_forced_movement_not_action(self, sirens_call_state):
        effect = CardEffectRegistry.get("sirens_call")
        xargatha = sirens_call_state.get_hero("xargatha")
        card = make_sirens_call_card()

        steps = effect.get_steps(sirens_call_state, xargatha, card)
        move_step = steps[2]

        assert move_step.is_movement_action is False

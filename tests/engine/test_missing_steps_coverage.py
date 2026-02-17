import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Card,
    CardTier,
    CardColor,
    ActionType,
)
from goa2.domain.types import HeroID
from goa2.engine.steps import ResolveCardStep, ResolveCardTextStep
from goa2.engine.handler import process_resolution_stack, push_steps


@pytest.fixture
def fallback_state():
    # Card with unknown effect_id to trigger fallbacks
    hero = Hero(id=HeroID("A"), name="Alpha", team=TeamColor.RED, deck=[])

    # We'll re-assign the card in specific tests
    state = GameState(
        board=Board(),
        teams={TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[])},
    )
    state.move_unit(hero.id, Hex(q=0, r=0, s=0))
    return state


def test_resolve_card_text_fallback_movement(fallback_state):
    hero = fallback_state.get_hero("A")
    hero.current_turn_card = Card(
        id="c1",
        name="Move",
        tier=CardTier.I,
        initiative=10,
        color=CardColor.RED,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=3,
        effect_id="non_existent_effect",
        effect_text="Move 3",
        is_facedown=False,
    )

    step = ResolveCardTextStep(card_id="c1", hero_id="A")
    push_steps(fallback_state, [step])

    # ResolveCardTextStep should find no effect, print warning, and spawn MoveUnitStep
    process_resolution_stack(fallback_state)

    # Verify stack now has MoveUnitStep (or it ran and finished with error)
    # MoveUnitStep will finish because target_hex isn't in context.
    assert len(fallback_state.execution_stack) == 0


def test_resolve_card_text_fallback_skill(fallback_state):
    hero = fallback_state.get_hero("A")
    hero.current_turn_card = Card(
        id="c1",
        name="Skill",
        tier=CardTier.I,
        initiative=10,
        color=CardColor.BLUE,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        effect_id="non_existent_effect",
        effect_text="Skill text",
        is_facedown=False,
    )

    step = ResolveCardTextStep(card_id="c1", hero_id="A")
    push_steps(fallback_state, [step])

    process_resolution_stack(fallback_state)
    # Should spawn LogMessageStep and finish
    assert len(fallback_state.execution_stack) == 0


def test_choose_secondary_hold(fallback_state):
    hero = fallback_state.get_hero("A")
    hero.current_turn_card = Card(
        id="c1",
        name="HoldTest",
        tier=CardTier.I,
        initiative=10,
        color=CardColor.GREEN,
        primary_action=ActionType.ATTACK,
        primary_action_value=4,
        secondary_actions={ActionType.HOLD: 0},
        effect_id="e",
        effect_text="t",
        is_facedown=False,
    )

    step = ResolveCardStep(hero_id="A")
    push_steps(fallback_state, [step])

    # 1. To prompt
    process_resolution_stack(fallback_state)

    # 2. Input: HOLD
    fallback_state.execution_stack[-1].pending_input = {"selection": "HOLD"}

    # 3. Resolve choice -> Spawns LogMessageStep -> runs LogMessageStep
    process_resolution_stack(fallback_state)

    assert len(fallback_state.execution_stack) == 0


def test_choose_secondary_clear(fallback_state):
    hero = fallback_state.get_hero("A")
    hero.current_turn_card = Card(
        id="c1",
        name="ClearTest",
        tier=CardTier.I,
        initiative=10,
        color=CardColor.RED,
        primary_action=ActionType.ATTACK,
        primary_action_value=4,
        secondary_actions={ActionType.CLEAR: 0},
        effect_id="e",
        effect_text="t",
        is_facedown=False,
    )

    step = ResolveCardStep(hero_id="A")
    push_steps(fallback_state, [step])

    process_resolution_stack(fallback_state)
    fallback_state.execution_stack[-1].pending_input = {"selection": "CLEAR"}
    process_resolution_stack(fallback_state)

    assert len(fallback_state.execution_stack) == 0


def test_resolve_card_text_hero_not_found(fallback_state):
    # Testing Line 794
    step = ResolveCardTextStep(card_id="none", hero_id="wrong_id")
    push_steps(fallback_state, [step])
    process_resolution_stack(fallback_state)
    assert len(fallback_state.execution_stack) == 0


def test_resolve_card_text_fallback_defense(fallback_state):
    hero = fallback_state.get_hero("A")
    hero.current_turn_card = Card(
        id="c1",
        name="Def",
        tier=CardTier.I,
        initiative=10,
        color=CardColor.BLUE,
        primary_action=ActionType.DEFENSE,
        primary_action_value=5,
        effect_id="non_existent_effect",
        effect_text="Def 5",
        is_facedown=False,
    )

    step = ResolveCardTextStep(card_id="c1", hero_id="A")
    push_steps(fallback_state, [step])
    process_resolution_stack(fallback_state)
    assert len(fallback_state.execution_stack) == 0


def test_fast_travel_not_available_no_loc(fallback_state):
    # Testing: off-board hero skips action entirely (no card resolution)
    hero = fallback_state.get_hero("A")
    hero.current_turn_card = Card(
        id="c1",
        name="Move",
        tier=CardTier.I,
        initiative=10,
        color=CardColor.RED,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=3,
        secondary_actions={},  # Validator will add FAST_TRAVEL
        effect_id="e",
        effect_text="t",
        is_facedown=False,
    )
    # Remove hero from board — off-board heroes skip their action
    fallback_state.remove_unit("A")
    step = ResolveCardStep(hero_id="A")
    push_steps(fallback_state, [step])
    req = process_resolution_stack(fallback_state)

    # Off-board hero skips action, no input request
    assert req is None


def test_choose_secondary_defense_active(fallback_state):
    # DEFENSE cannot be chosen as an active action on your turn.
    # It can only be used during the reaction window when defending.
    # This test verifies that DEFENSE is filtered out of available options.
    hero = fallback_state.get_hero("A")
    hero.current_turn_card = Card(
        id="c1",
        name="DefTest",
        tier=CardTier.I,
        initiative=10,
        color=CardColor.BLUE,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={ActionType.DEFENSE: 5, ActionType.MOVEMENT: 2},
        effect_id="e",
        effect_text="t",
        is_facedown=False,
    )

    step = ResolveCardStep(hero_id="A")
    push_steps(fallback_state, [step])
    req = process_resolution_stack(fallback_state)

    # DEFENSE should NOT be in the options
    opts = [o["id"] for o in req["options"]]
    assert "DEFENSE" not in opts
    # But other secondary actions should be available
    assert "MOVEMENT" in opts


def test_resolve_card_hero_not_found(fallback_state):
    # Testing Line 835
    step = ResolveCardStep(hero_id="wrong_id")
    push_steps(fallback_state, [step])
    process_resolution_stack(fallback_state)
    assert len(fallback_state.execution_stack) == 0

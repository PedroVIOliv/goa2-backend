import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, Card, CardTier, CardColor, ActionType, Hero
from goa2.domain.types import HeroID, CardID
from goa2.domain.hex import Hex
from goa2.engine.steps import (
    StepResult, GameStep, LogMessageStep, SelectTargetStep, 
    ReactionWindowStep, ResolveCombatStep, AttackSequenceStep,
    MoveUnitStep, DamageStep
)
from goa2.engine.handler import process_resolution_stack, push_steps

# --- Fixtures ---

@pytest.fixture
def empty_state():
    return GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[])
        },
        current_actor_id="hero_red"
    )

@pytest.fixture
def combat_state(empty_state):
    # Setup Red Attacker
    attacker = Hero(name="Red Hero", id=HeroID("hero_red"), deck=[])
    empty_state.teams[TeamColor.RED].heroes.append(attacker)
    
    # Setup Blue Defender with Defense Cards
    def_card = Card(
        id=CardID("def_card_1"), 
        name="Shield", 
        tier=CardTier.I, 
        color=CardColor.BLUE, 
        initiative=1, 
        primary_action=ActionType.DEFENSE, 
        primary_action_value=5,
        effect_id="e1", effect_text="e1", is_facedown=False
    )
    # Ensure it's in hand
    defender = Hero(name="Blue Hero", id=HeroID("hero_blue"), deck=[def_card])
    defender.hand.append(def_card)
    
    empty_state.teams[TeamColor.BLUE].heroes.append(defender)
    
    return empty_state

# --- Tests ---

def test_select_target_flow(empty_state):
    step = SelectTargetStep(prompt="Choose", output_key="target_id")
    push_steps(empty_state, [step])
    
    # Pass 1: Request
    req = process_resolution_stack(empty_state)
    assert req is not None
    assert req["type"] == "SELECT_UNIT"
    
    # Pass 2: Provide Input
    empty_state.execution_stack[-1].pending_input = {"selected_id": "target_1"}
    req = process_resolution_stack(empty_state)
    
    assert req is None # Done
    assert empty_state.execution_context["target_id"] == "target_1"


def test_reaction_window_validation(combat_state):
    # Target Blue Hero
    combat_state.execution_context["target_id"] = "hero_blue"
    
    step = ReactionWindowStep(target_player_key="target_id")
    push_steps(combat_state, [step])
    
    # Pass 1: Request Input
    req = process_resolution_stack(combat_state)
    assert req["type"] == "SELECT_CARD_OR_PASS"
    assert "def_card_1" in req["options"]
    assert "PASS" in req["options"]
    
    # Pass 2: Select Invalid Card (Mocking frontend bypass)
    # This assumes strict validation, but our demo step currently warns & proceeds or crashes depending on impl.
    # Let's test valid input first.
    
    combat_state.execution_stack[-1].pending_input = {"selected_card_id": "def_card_1"}
    process_resolution_stack(combat_state)
    
    assert combat_state.execution_context["defense_value"] == 5

def test_combat_resolution_block(combat_state):
    # Defense 5 vs Attack 3 -> Blocked
    combat_state.execution_context["defense_value"] = 5
    combat_state.execution_context["victim_id"] = "hero_blue"
    
    step = ResolveCombatStep(damage=3, target_key="victim_id")
    push_steps(combat_state, [step])
    
    process_resolution_stack(combat_state)
    # Since we don't have "is_dead" logic fully wired to remove from team, check Logs?
    # Or mock print. Step currently just prints. 
    # Real test would check state change.
    # For now, we assert it runs without error.

def test_combat_resolution_hit(combat_state):
    # Defense 0 vs Attack 3 -> Hit
    combat_state.execution_context["defense_value"] = 0
    combat_state.execution_context["victim_id"] = "hero_blue"
    
    step = ResolveCombatStep(damage=3, target_key="victim_id")
    push_steps(combat_state, [step])
    
    process_resolution_stack(combat_state)
    # Again, verifying side effects requires mock or inspecting stdout capsys.
    
def test_attack_sequence_expansion(combat_state):
    # Check that the Macro step expands into 3 steps
    step = AttackSequenceStep(damage=3, range_val=1)
    push_steps(combat_state, [step])
    
    # Run once to expand
    process_resolution_stack(combat_state)
    
    # Now stack should have SelectTargetStep at top
    current = combat_state.execution_stack[-1]
    assert isinstance(current, SelectTargetStep)

# --- New Error Handling Tests ---

def test_move_unit_error_handling(empty_state):
    # No actor
    step = MoveUnitStep(unit_id=None, destination_key="dest")
    empty_state.current_actor_id = None
    res = step.resolve(empty_state, {"dest": Hex(q=0,r=0,s=0)})
    assert res.is_finished # Should finish with error log
    
    # No destination
    step2 = MoveUnitStep(unit_id="h1", destination_key="missing_key")
    res2 = step2.resolve(empty_state, {})
    assert res2.is_finished

def test_damage_error_handling(empty_state):
    step = DamageStep(amount=1, target_key="missing")
    res = step.resolve(empty_state, {})
    assert res.is_finished # Finishes with log

def test_log_message(empty_state):
    step = LogMessageStep(message="Hello {name}")
    res = step.resolve(empty_state, {"name": "World"})
    assert res.is_finished
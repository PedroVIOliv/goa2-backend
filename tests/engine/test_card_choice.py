import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, Hero, Card, CardTier, CardColor, ActionType
from goa2.domain.types import HeroID
from goa2.engine.steps import ResolveCardStep
from goa2.engine.handler import process_resolution_stack, push_steps

def create_test_hero(id_str, team, card_actions):
    primary_action, primary_val, secondary_actions = card_actions
    
    card = Card(
        id=f"c_{id_str}",
        name="Test Card",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=10,
        primary_action=primary_action,
        primary_action_value=primary_val,
        secondary_actions=secondary_actions,
        effect_id="test_eff",
        effect_text="Do something cool",
        is_facedown=False
    )
    
    hero = Hero(id=HeroID(id_str), name=id_str, team=team, deck=[])
    hero.current_turn_card = card
    return hero

@pytest.fixture
def choice_state():
    # Hero has Primary: ATTACK 4
    # Secondary: MOVEMENT 2, HOLD 0
    hero = create_test_hero("A", TeamColor.RED, (
        ActionType.ATTACK, 4, 
        {ActionType.MOVEMENT: 2, ActionType.HOLD: 0}
    ))
    
    state = GameState(
        board=Board(),
        teams={TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[])}
    )
    state.move_unit(hero.id, Hex(q=0, r=0, s=0))
    return state

def test_resolve_card_prompts_for_choice(choice_state):
    """Verify engine pauses and asks for choice."""
    step = ResolveCardStep(hero_id="A")
    push_steps(choice_state, [step])
    
    req = process_resolution_stack(choice_state)
    
    assert req is not None
    assert req["type"] == "CHOOSE_ACTION"
    assert req["player_id"] == "A"
    
    # Check Options
    opts = req["options"]
    ids = [o["id"] for o in opts]
    assert "ATTACK" in ids
    assert "MOVEMENT" in ids
    assert "HOLD" in ids
    
    # Verify Primary Text
    prim = next(o for o in opts if o["id"] == "ATTACK")
    assert prim["type"] == ActionType.ATTACK
    assert prim["value"] == 4

def test_choose_secondary_movement(choice_state):
    """Verify choosing Secondary spawns MoveUnitStep."""
    step = ResolveCardStep(hero_id="A")
    push_steps(choice_state, [step])
    
    # 1. Run to prompt
    process_resolution_stack(choice_state)
    
    # 2. Provide Input: Secondary Move
    choice_state.execution_stack[-1].pending_input = {"choice_id": "MOVEMENT"}
    
    # 3. Run again
    # The ResolveCardStep should finish and spawn MoveUnitStep
    # process_resolution_stack returns None if step finishes without new input
    # But MoveUnitStep might fail immediately if no destination set (it expects context),
    # or it prints error and finishes. 
    # MoveUnitStep resolve -> returns is_finished=True (and prints error "No destination").
    # So process_resolution_stack should empty the stack.
    
    req = process_resolution_stack(choice_state)
    assert req is None # Stack emptied
    
    # We can't easily check "what step ran" without mocking, 
    # but we can check if the stack is empty, meaning the new step ran and finished.
    assert len(choice_state.execution_stack) == 0

def test_choose_primary_script(choice_state):
    """Verify choosing Primary spawns ResolveCardTextStep."""
    step = ResolveCardStep(hero_id="A")
    push_steps(choice_state, [step])
    
    process_resolution_stack(choice_state)
    
    # Input: Primary
    choice_state.execution_stack[-1].pending_input = {"choice_id": "ATTACK"}
    
    req = process_resolution_stack(choice_state)
    assert req is None
    
    # In a real test we'd capture stdout or check if script had side effects.
    # For now, ensuring it runs without error (stack empty) is good.

def test_resolve_card_no_primary():
    """Test a card that is facedown (no primary available)."""
    hero = create_test_hero("B", TeamColor.BLUE, (
        ActionType.SKILL, None, 
        {ActionType.HOLD: 0}
    ))
    hero.current_turn_card.is_facedown = True
    
    state = GameState(
        board=Board(),
        teams={TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[hero], minions=[])}
    )
    state.move_unit(hero.id, Hex(q=0, r=0, s=0))

    step = ResolveCardStep(hero_id="B")
    push_steps(state, [step])
    
    req = process_resolution_stack(state)
    opts = req["options"]
    
    # Should be no SKILL option (it is facedown)
    assert not any(o["id"] == "SKILL" for o in opts)
    assert any(o["id"] == "HOLD" for o in opts)

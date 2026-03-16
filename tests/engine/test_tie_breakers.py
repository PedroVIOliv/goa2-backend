import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, Hero, Card, CardTier, CardColor, ActionType
from goa2.domain.types import HeroID
from goa2.engine.steps import ResolveTieBreakerStep
from goa2.engine.handler import process_resolution_stack, push_steps

def _filler_cards():
    """Return dummy hand cards so heroes aren't auto-passed for empty hands."""
    return [Card(id=f"filler_{i}", name=f"Filler {i}", tier=CardTier.I, color=CardColor.RED,
                 initiative=1, primary_action=ActionType.SKILL, primary_action_value=None,
                 effect_id="e", effect_text="t") for i in range(3)]

@pytest.fixture
def complex_tie_state():
    hero_a = Hero(id=HeroID("A"), name="Alpha", team=TeamColor.RED, deck=[], hand=_filler_cards())
    hero_b = Hero(id=HeroID("B"), name="Bravo", team=TeamColor.BLUE, deck=[], hand=_filler_cards())
    hero_c = Hero(id=HeroID("C"), name="Charlie", team=TeamColor.BLUE, deck=[], hand=_filler_cards())
    hero_d = Hero(id=HeroID("D"), name="Delta", team=TeamColor.RED, deck=[], hand=_filler_cards())
    
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero_a, hero_d], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[hero_b, hero_c], minions=[])
        },
        tie_breaker_team=TeamColor.RED
    )
    
    fake_card = Card(id="c1", name="C", tier=CardTier.I, color=CardColor.RED, initiative=10, primary_action=ActionType.SKILL, primary_action_value=None, effect_id="e", effect_text="t", is_facedown=False)
    
    # Assign cards to heroes so ResolveCardStep works
    hero_a.current_turn_card = fake_card
    hero_b.current_turn_card = fake_card
    hero_c.current_turn_card = fake_card
    hero_d.current_turn_card = fake_card

    # Place heroes on board
    state.move_unit(hero_a.id, Hex(q=0, r=0, s=0))
    state.move_unit(hero_b.id, Hex(q=1, r=0, s=-1))
    state.move_unit(hero_c.id, Hex(q=0, r=1, s=-1))
    state.move_unit(hero_d.id, Hex(q=-1, r=1, s=0))

    return state

def test_complex_tie_resolution_flow(complex_tie_state):
    # --- Round 1: [A, B, C, D] ---
    step1 = ResolveTieBreakerStep(tied_hero_ids=["A", "B", "C", "D"])
    push_steps(complex_tie_state, [step1])
    
    # Pass 1: Red Choice [A, D]
    req = process_resolution_stack(complex_tie_state)
    assert req["type"] == "CHOOSE_ACTOR"
    assert req["team"] == TeamColor.RED
    
    # Simulate Red choosing A
    complex_tie_state.execution_stack[-1].pending_input = {"selection": "A"}
    
    # Pass 2: A is winner. Spawns ResolveCardStep(A).
    req = process_resolution_stack(complex_tie_state)
    assert req["type"] == "CHOOSE_ACTION"
    assert req["player_id"] == "A"
    
    # Simulate Card Choice (Hold)
    complex_tie_state.execution_stack[-1].pending_input = {"selection": "HOLD"}
    
    # Pass 3: A finishes. Hits ConfirmResolutionStep.
    req = process_resolution_stack(complex_tie_state)
    assert req["type"] == "CHOOSE_ACTION"
    assert req["player_id"] == "A"
    complex_tie_state.execution_stack[-1].pending_input = {"selection": "CONFIRM"}
    req = process_resolution_stack(complex_tie_state)
    assert req is None

    # Verify Coin
    assert complex_tie_state.tie_breaker_team == TeamColor.BLUE
    
    # --- Round 2: Re-evaluate [B, C, D] ---
    step2 = ResolveTieBreakerStep(tied_hero_ids=["B", "C", "D"])
    push_steps(complex_tie_state, [step2])
    
    # Pass 4: Blue Choice [B, C]
    req = process_resolution_stack(complex_tie_state)
    assert req["type"] == "CHOOSE_ACTOR"
    assert req["team"] == TeamColor.BLUE
    
    # Simulate Blue choosing B
    complex_tie_state.execution_stack[-1].pending_input = {"selection": "B"}
    
    # Pass 5: B Card Choice
    req = process_resolution_stack(complex_tie_state)
    assert req["type"] == "CHOOSE_ACTION"
    
    complex_tie_state.execution_stack[-1].pending_input = {"selection": "HOLD"}

    req = process_resolution_stack(complex_tie_state)
    assert req["type"] == "CHOOSE_ACTION"
    complex_tie_state.execution_stack[-1].pending_input = {"selection": "CONFIRM"}
    req = process_resolution_stack(complex_tie_state)
    assert req is None

    assert complex_tie_state.tie_breaker_team == TeamColor.RED

    # --- Round 3: Re-evaluate [C, D] ---
    step3 = ResolveTieBreakerStep(tied_hero_ids=["C", "D"])
    push_steps(complex_tie_state, [step3])
    
    # Pass 6: Red Choice [D] -> Auto-select?
    # Logic: Red (favored) has D. Blue has C.
    # Tied different teams. Red wins.
    # Red has [D]. Only 1 candidate.
    # So D wins automatically.
    # Returns ResolveCardStep(D).
    
    req = process_resolution_stack(complex_tie_state)
    assert req["type"] == "CHOOSE_ACTION"
    assert req["player_id"] == "D"
    
    complex_tie_state.execution_stack[-1].pending_input = {"selection": "HOLD"}

    req = process_resolution_stack(complex_tie_state)
    assert req["type"] == "CHOOSE_ACTION"
    complex_tie_state.execution_stack[-1].pending_input = {"selection": "CONFIRM"}
    req = process_resolution_stack(complex_tie_state)
    assert req is None

    assert complex_tie_state.tie_breaker_team == TeamColor.BLUE

    # --- Round 4: Re-evaluate [C] ---
    step4 = ResolveTieBreakerStep(tied_hero_ids=["C"])
    push_steps(complex_tie_state, [step4])
    
    # C wins auto. ResolveCardStep(C).
    req = process_resolution_stack(complex_tie_state)
    assert req["type"] == "CHOOSE_ACTION"
    assert req["player_id"] == "C"
    
    complex_tie_state.execution_stack[-1].pending_input = {"selection": "HOLD"}

    req = process_resolution_stack(complex_tie_state)
    assert req["type"] == "CHOOSE_ACTION"
    complex_tie_state.execution_stack[-1].pending_input = {"selection": "CONFIRM"}
    req = process_resolution_stack(complex_tie_state)
    assert req is None
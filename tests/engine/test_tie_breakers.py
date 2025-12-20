import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, Hero, Card, CardTier, CardColor, ActionType
from goa2.domain.types import HeroID, CardID
from goa2.engine.steps import ResolveTieBreakerStep
from goa2.engine.handler import process_resolution_stack, push_steps

@pytest.fixture
def complex_tie_state():
    """
    Setup:
    - Red Team: Hero A, Hero D
    - Blue Team: Hero B, Hero C
    - Tie Breaker Coin: RED
    """
    hero_a = Hero(id=HeroID("A"), name="Alpha", team=TeamColor.RED, deck=[])
    hero_b = Hero(id=HeroID("B"), name="Bravo", team=TeamColor.BLUE, deck=[])
    hero_c = Hero(id=HeroID("C"), name="Charlie", team=TeamColor.BLUE, deck=[])
    hero_d = Hero(id=HeroID("D"), name="Delta", team=TeamColor.RED, deck=[])
    
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero_a, hero_d], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[hero_b, hero_c], minions=[])
        },
        tie_breaker_team=TeamColor.RED
    )
    
    # Store "cards" in context as the engine expects
    # (HeroID, Card)
    fake_card = Card(id="c1", name="C", tier=CardTier.I, color=CardColor.RED, initiative=10, primary_action=ActionType.SKILL, effect_id="e", effect_text="t", is_facedown=False)
    state.execution_context["tied_cards"] = [
        ("A", fake_card), ("B", fake_card), ("C", fake_card), ("D", fake_card)
    ]
    
    return state

def test_complex_tie_resolution_flow(complex_tie_state):
    """
    Scenario: A, B, C, D tied.
    1. Red is favored. Red has [A, D]. Red must choose.
    2. Red chooses A. A acts. Coin flips to BLUE.
    3. Blue is favored. Blue has [B, C]. Blue must choose.
    4. Blue chooses B. B acts. Coin flips to RED.
    5. Red is favored. Red has [D]. Red acts auto. Coin flips to BLUE.
    6. Blue acts [C] auto.
    """
    step = ResolveTieBreakerStep(tied_hero_ids=["A", "B", "C", "D"])
    push_steps(complex_tie_state, [step])
    
    # --- Pass 1: Red Choice [A, D] ---
    req = process_resolution_stack(complex_tie_state)
    assert req["type"] == "CHOOSE_ACTOR"
    assert req["team"] == TeamColor.RED
    assert set(req["player_ids"]) == {"A", "D"}
    
    # Simulate Red choosing A
    complex_tie_state.execution_stack[-1].pending_input = {"selected_hero_id": "A"}
    
    # --- Pass 2: A resolves, next is Blue Choice [B, C] ---
    # Note: process_resolution_stack will pop TieBreaker, push [ActionA, TieBreaker(B,C,D)]
    # It will then execute ActionA (LogMessage) and hit the next TieBreaker.
    req = process_resolution_stack(complex_tie_state)
    
    assert complex_tie_state.tie_breaker_team == TeamColor.BLUE # Coin flipped
    assert req["type"] == "CHOOSE_ACTOR"
    assert req["team"] == TeamColor.BLUE
    assert set(req["player_ids"]) == {"B", "C"}
    
    # Simulate Blue choosing B
    complex_tie_state.execution_stack[-1].pending_input = {"selected_hero_id": "B"}
    
    # --- Pass 3: B resolves, next is Red Choice [D] (Auto) ---
    # Since only D remains for Red, it acts auto. 
    # Then only C remains for Blue, it acts auto.
    # The loop should finish.
    req = process_resolution_stack(complex_tie_state)
    
    assert req is None # All resolved
    assert complex_tie_state.tie_breaker_team == TeamColor.BLUE # Flipped twice (R->B, B->R, R->B)

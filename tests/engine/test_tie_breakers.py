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
    3. Loop re-evaluates: [B, C, D] tied. Blue favored.
    4. Blue chooses B. B acts. Coin flips to RED.
    5. Loop re-evaluates: [C, D] tied. Red favored.
    6. Red acts [D] auto (only one Red). Coin flips to BLUE.
    7. Loop re-evaluates: [C] left. Acts auto.
    """
    
    # --- Round 1: [A, B, C, D] ---
    step1 = ResolveTieBreakerStep(tied_hero_ids=["A", "B", "C", "D"])
    push_steps(complex_tie_state, [step1])
    
    # Pass 1: Red Choice [A, D]
    req = process_resolution_stack(complex_tie_state)
    assert req["type"] == "CHOOSE_ACTOR"
    assert req["team"] == TeamColor.RED
    assert set(req["player_ids"]) == {"A", "D"}
    
    # Simulate Red choosing A
    complex_tie_state.execution_stack[-1].pending_input = {"selected_hero_id": "A"}
    
    # Pass 2: A resolves. Stack empties.
    req = process_resolution_stack(complex_tie_state)
    assert req is None
    
    # Verify State Change
    assert complex_tie_state.tie_breaker_team == TeamColor.BLUE # Coin flipped
    assert complex_tie_state.current_actor_id is None # Cleared after turn
    
    # --- Round 2: Re-evaluate [B, C, D] ---
    # In real engine, phases.py would trigger this. We simulate it.
    step2 = ResolveTieBreakerStep(tied_hero_ids=["B", "C", "D"])
    push_steps(complex_tie_state, [step2])
    
    # Pass 3: Blue Choice [B, C]
    req = process_resolution_stack(complex_tie_state)
    assert req["type"] == "CHOOSE_ACTOR"
    assert req["team"] == TeamColor.BLUE
    assert set(req["player_ids"]) == {"B", "C"}
    
    # Simulate Blue choosing B
    complex_tie_state.execution_stack[-1].pending_input = {"selected_hero_id": "B"}
    
    # Pass 4: B resolves.
    req = process_resolution_stack(complex_tie_state)
    assert req is None
    
    # Verify State Change
    assert complex_tie_state.tie_breaker_team == TeamColor.RED # Flipped back
    assert complex_tie_state.current_actor_id is None
    
    # --- Round 3: Re-evaluate [C, D] ---
    step3 = ResolveTieBreakerStep(tied_hero_ids=["C", "D"])
    push_steps(complex_tie_state, [step3])
    
    # Pass 5: Red Choice [D] -> Auto-select because D is only Red option in {D, C} group?
    # Logic: Tied [C, D]. Teams: Red=[D], Blue=[C].
    # Favored: Red.
    # Red has candidates [D]. Only 1. So D wins automatically.
    # Does coin flip? Yes, different teams were tied.
    
    req = process_resolution_stack(complex_tie_state)
    assert req is None # Auto-resolved D
    
    assert complex_tie_state.tie_breaker_team == TeamColor.BLUE
    assert complex_tie_state.current_actor_id is None

    # --- Round 4: Re-evaluate [C] ---
    # Just C left. Not a tie. But if we passed it to TieStep, it handles 1 item gracefully.
    step4 = ResolveTieBreakerStep(tied_hero_ids=["C"])
    push_steps(complex_tie_state, [step4])
    
    req = process_resolution_stack(complex_tie_state)
    assert req is None
    assert complex_tie_state.current_actor_id is None

from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, GamePhase, CardState, CardColor
from goa2.engine.phases import resolve_next_action
from goa2.engine.handler import process_resolution_stack

def test_turn_increment():
    """Verify Turn 1 -> Turn 2 transition."""
    state = GameState(
        board=Board(),
        teams={TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[])},
        turn=1,
        phase=GamePhase.RESOLUTION
    )
    
    # Simulate empty resolution queue (all acted)
    state.unresolved_hero_ids = []
    
    # Trigger Logic
    resolve_next_action(state)
    
    assert state.turn == 2
    assert state.phase == GamePhase.PLANNING

def test_round_end_transition():
    """Verify Turn 4 -> End Phase -> Round 2."""
    state = GameState(
        board=Board(),
        teams={TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[])},
        turn=4,
        round=1,
        phase=GamePhase.RESOLUTION
    )
    
    state.unresolved_hero_ids = []
    
    # Trigger Logic -> Should hit end_turn -> start_end_phase -> push EndPhaseStep
    resolve_next_action(state)
    
    # Run stack to execute EndPhaseStep
    process_resolution_stack(state)
    
    assert state.round == 2
    assert state.turn == 1
    assert state.phase == GamePhase.PLANNING

def test_planning_to_revelation():
    """Verify Planning -> Revelation transition with facedown/faceup logic."""
    from goa2.domain.models import Hero, Card, CardTier, ActionType
    from goa2.engine.phases import commit_card
    
    # 1. Setup
    c1 = Card(id="c1", name="C1", tier=CardTier.I, color=CardColor.RED, initiative=10, primary_action=ActionType.ATTACK, primary_action_value=2, effect_id="e", effect_text="t")
    c2 = Card(id="c2", name="C2", tier=CardTier.I, color=CardColor.BLUE, initiative=5, primary_action=ActionType.SKILL, primary_action_value=None, effect_id="e", effect_text="t")
    
    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, deck=[c1], hand=[c1])
    h2 = Hero(id="h2", name="H2", team=TeamColor.BLUE, deck=[c2], hand=[c2])
    
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[h2], minions=[])
        },
        phase=GamePhase.PLANNING
    )
    
    # 2. H1 Commits
    commit_card(state, "h1", c1)
    assert c1.is_facedown == True
    assert c1.state == CardState.UNRESOLVED
    assert state.phase == GamePhase.PLANNING
    
    # 3. H2 Commits -> Triggers Revelation
    commit_card(state, "h2", c2)
    
    # Revelation happens immediately because all players committed
    assert state.phase == GamePhase.RESOLUTION # Transitioned through REVELATION automatically
    assert c1.is_facedown == False
    assert c2.is_facedown == False
    
    # Verify Unresolved pool
    # H1 has initiative 10, H2 has 5. 
    # H1 should have been popped from unresolved and set as current actor
    assert state.current_actor_id == "h1"
    assert "h1" not in state.unresolved_hero_ids
    assert "h2" in state.unresolved_hero_ids
    
    # Verify initiative calculation
    # Since they are revealed, effective initiative should be > 0
    assert h1.get_effective_initiative() == 10
    assert h2.get_effective_initiative() == 5

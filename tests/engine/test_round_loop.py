import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, GamePhase, Hero
from goa2.domain.types import HeroID
from goa2.engine.phases import resolve_next_action, end_turn
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

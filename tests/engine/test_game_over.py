import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, GamePhase, Hero
from goa2.engine.steps import (
    DefeatUnitStep,
    TriggerGameOverStep,
    LanePushStep,
    SpendAdditionalLifeCounterStep,
)
from goa2.engine.handler import process_resolution_stack
from goa2.domain.types import HeroID

@pytest.fixture
def game_state():
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[], life_counters=1),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[], life_counters=5)
        }
    )
    # Add a hero to kill
    hero = Hero(id=HeroID("hero_victim"), name="Victim", deck=[], team=TeamColor.RED)
    state.register_entity(hero, "hero")
    return state

def test_annihilation_trigger(game_state):
    """
    Verify that killing a hero when life_counters=1 triggers Game Over.
    """
    # 1. Setup Step
    step = DefeatUnitStep(victim_id="hero_victim")
    
    # 2. Run Step Logic
    context = {}
    result = step.resolve(game_state, context)
    
    # 3. Check Result: Should spawn TriggerGameOverStep
    # Note: DefeatUnitStep spawns [RemoveUnit, CheckLanePush, TriggerGameOver] potentially
    # Wait, in the code:
    # if life == 0: return StepResult(..., new_steps=[TriggerGameOverStep])
    # ELSE return standard defeat steps.
    
    assert result.is_finished is True
    assert len(result.new_steps) == 2
    from goa2.engine.steps import RemoveUnitStep
    assert isinstance(result.new_steps[0], RemoveUnitStep)
    assert isinstance(result.new_steps[1], TriggerGameOverStep)
    assert result.new_steps[1].condition == "ANNIHILATION"
    assert result.new_steps[1].winner == TeamColor.BLUE

def test_game_over_state_transition(game_state):
    """
    Verify TriggerGameOverStep correctly mutates state and clears stack.
    """
    step = TriggerGameOverStep(winner=TeamColor.BLUE, condition="TEST")
    
    # Pollute stack to verify clearing
    game_state.execution_stack.append("junk")
    
    step.resolve(game_state, {})
    
    assert game_state.phase == GamePhase.GAME_OVER
    assert game_state.winner == TeamColor.BLUE
    assert game_state.victory_condition == "TEST"
    assert len(game_state.execution_stack) == 0

def test_handler_stops_on_game_over(game_state):
    """
    Verify handler.py refuses to run if phase is GAME_OVER.
    """
    game_state.phase = GamePhase.GAME_OVER
    game_state.execution_stack.append(TriggerGameOverStep(winner=TeamColor.RED, condition="FAIL"))
    
    # Should return None immediately and NOT print "Game Over" again
    res = process_resolution_stack(game_state)
    assert res is None

def test_last_push_victory(game_state):
    """
    Verify that LanePushStep triggers Last Push Victory when wave_counter hits 0.
    """
    game_state.wave_counter = 1
    step = LanePushStep(losing_team=TeamColor.RED)
    
    result = step.resolve(game_state, {})
    
    assert game_state.wave_counter == 0
    assert len(result.new_steps) == 1
    assert isinstance(result.new_steps[0], TriggerGameOverStep)
    assert result.new_steps[0].condition == "LAST_PUSH"
    assert result.new_steps[0].winner == TeamColor.BLUE

def test_lane_push_throne_victory(game_state):
    """
    Verify that LanePushStep triggers Lane Push Victory when Throne is reached.
    """
    # Setup board with a lane where RED Base is adjacent to current zone
    game_state.board.lane = ["RedBase", "Mid", "BlueBase"]
    game_state.active_zone_id = "Mid"
    
    step = LanePushStep(losing_team=TeamColor.RED)
    
    # Mocking get_push_target_zone_id is hard, let's just run it
    # get_push_target_zone_id("Mid", RED) -> idx 1 - 1 = 0 ("RedBase") -> new_idx < 0? No.
    # Wait, get_push_target_zone_id logic:
    # if losing_team == TeamColor.RED: new_idx = idx - 1; if new_idx < 0: return None, True
    
    game_state.active_zone_id = "RedBase"
    result = step.resolve(game_state, {})
    
    assert len(result.new_steps) == 1
    assert isinstance(result.new_steps[0], TriggerGameOverStep)
    assert result.new_steps[0].condition == "LANE_PUSH"
    assert result.new_steps[0].winner == TeamColor.BLUE


def test_spend_additional_life_counter_triggers_annihilation(game_state):
    step = SpendAdditionalLifeCounterStep(victim_key="victim_id", amount=1)

    result = step.resolve(game_state, {"victim_id": "hero_victim"})

    assert game_state.teams[TeamColor.RED].life_counters == 0
    assert len(result.new_steps) == 1
    assert isinstance(result.new_steps[0], TriggerGameOverStep)
    assert result.new_steps[0].condition == "ANNIHILATION"
    assert result.new_steps[0].winner == TeamColor.BLUE

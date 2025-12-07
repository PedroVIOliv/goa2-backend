import pytest
from goa2.domain.state import GameState
from goa2.engine.phases import GamePhase, ResolutionStep
from goa2.domain.types import HeroID, CardID
from goa2.engine.command import Command
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, Hero, Card, CardTier, CardColor, ActionType

# Helper for minimal setup
@pytest.fixture
def minimal_state():
    b = Board()
    t = Team(color=TeamColor.RED)
    return GameState(board=b, teams={TeamColor.RED: t})

class SampleCommand(Command):
    """A dummy command to test execution."""
    def execute(self, state: GameState) -> GameState:
        state.round += 1
        return state

def test_state_init(minimal_state):
    s = minimal_state
    assert s.phase == GamePhase.SETUP
    assert s.resolution_step == ResolutionStep.NONE
    assert s.round == 1
    assert TeamColor.RED in s.teams

def test_command_execution(minimal_state):
    s = minimal_state
    cmd = SampleCommand()
    
    # Execute
    new_s = cmd.execute(s)
    
    # Verify mutation
    assert new_s.round == 2
    assert new_s is s # Confirming mutation pattern if that's what we want, or at least returned reference

def test_state_serialization(minimal_state):
    s = minimal_state
    # Add some nested data
    c = Card(id="c", name="S", tier=CardTier.UNTIERED, color=CardColor.GOLD, initiative=1, primary_action=ActionType.ATTACK, effect_id="e", effect_text="t")
    h = Hero(id="h", name="K", team=TeamColor.RED, deck=[], hand=[c])
    s.teams[TeamColor.RED].heroes.append(h)
    
    # Serialize
    json_str = s.model_dump_json()
    assert "teams" in json_str
    assert "HERO" not in json_str # Just checking random strings, but ensuring it dumps
    
    # Deserialize
    restored = GameState.model_validate_json(json_str)
    assert restored.round == s.round
    assert restored.teams[TeamColor.RED].heroes[0].id == "h"
    assert restored.teams[TeamColor.RED].heroes[0].hand[0].name == "S"
    assert restored.teams[TeamColor.RED].heroes[0].hand[0].name == "S"

import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, MinionType, Hero
from goa2.domain.factory import EntityFactory
from goa2.domain.types import HeroID

@pytest.fixture
def reg_state():
    return GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[])
        }
    )

def test_register_minion_auto_sorts_to_team(reg_state):
    """
    Ensures that calling register_entity with collection_type='minion'
    automatically appends the minion to the correct team's roster.
    """
    m_red = EntityFactory.create_minion(reg_state, TeamColor.RED, MinionType.MELEE)
    m_blue = EntityFactory.create_minion(reg_state, TeamColor.BLUE, MinionType.RANGED)
    
    # Register RED minion
    reg_state.register_entity(m_red, "minion")
    assert len(reg_state.teams[TeamColor.RED].minions) == 1
    assert reg_state.teams[TeamColor.RED].minions[0].id == m_red.id
    assert len(reg_state.teams[TeamColor.BLUE].minions) == 0
    
    # Register BLUE minion
    reg_state.register_entity(m_blue, "minion")
    assert len(reg_state.teams[TeamColor.BLUE].minions) == 1
    assert reg_state.teams[TeamColor.BLUE].minions[0].id == m_blue.id

def test_register_hero_auto_sorts_to_team(reg_state):
    """
    Ensures heroes are sorted into the team.heroes list.
    """
    hero = Hero(
        id=HeroID("hero_test"), 
        name="Test Hero", 
        deck=[], 
        team=TeamColor.RED
    )
    
    reg_state.register_entity(hero, "hero")
    
    assert len(reg_state.teams[TeamColor.RED].heroes) == 1
    assert reg_state.teams[TeamColor.RED].heroes[0].id == "hero_test"
    
    # Also verify global lookup works
    assert reg_state.get_hero("hero_test") is not None

def test_register_invalid_team_raises_error(reg_state):
    """
    Trying to register a unit to a team that doesn't exist in the state 
    should raise an error.
    """
    # Create a minion but hack its team to be invalid/missing from state
    # We use a dummy string that isn't a key in reg_state.teams
    m_rogue = EntityFactory.create_minion(reg_state, TeamColor.RED, MinionType.MELEE)
    m_rogue.team = "PURPLE" # Doesn't exist
    
    with pytest.raises(ValueError, match="Invalid or missing team"):
        reg_state.register_entity(m_rogue, "minion")

def test_register_token_goes_to_misc(reg_state):
    """
    Tokens should go to misc_entities, not teams.
    """
    token = EntityFactory.create_token(reg_state, "Trap")
    reg_state.register_entity(token, "token")
    
    assert token.id in reg_state.misc_entities
    assert reg_state.get_entity(token.id) is not None

def test_duplicate_registration_raises_error(reg_state):
    """
    Registering an entity with an ID that already exists (even if different object)
    should fail.
    """
    token = EntityFactory.create_token(reg_state, "Trap")
    reg_state.register_entity(token, "token")
    
    # Try registering exact same object again
    with pytest.raises(ValueError, match="ID Collision"):
        reg_state.register_entity(token, "token")
        
    # Try registering different object with same ID
    imposter = EntityFactory.create_token(reg_state, "Imposter")
    imposter.id = token.id # Hack ID to match
    
    with pytest.raises(ValueError, match="ID Collision"):
        reg_state.register_entity(imposter, "token")

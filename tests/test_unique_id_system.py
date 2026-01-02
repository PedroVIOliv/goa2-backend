import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, MinionType
from goa2.domain.factory import EntityFactory

def test_unique_id_generation():
    """
    Verifies that the State generates monotonic unique IDs
    and the Factory uses them correctly.
    """
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[])
        }
    )
    
    # 1. Check Initial State
    assert state.next_entity_id == 1
    
    # 2. Generate IDs via State directly
    id1 = state.create_entity_id("test")
    id2 = state.create_entity_id("test")
    
    assert id1 == "test_1"
    assert id2 == "test_2"
    assert state.next_entity_id == 3
    
    # 3. Use Factory to create Minions
    m1 = EntityFactory.create_minion(state, TeamColor.RED, MinionType.MELEE)
    m2 = EntityFactory.create_minion(state, TeamColor.BLUE, MinionType.RANGED)
    
    assert m1.id == "minion_3"
    assert m2.id == "minion_4"
    assert m1.name == "RED MELEE Minion"
    
    # 4. Use Factory to create Token
    t1 = EntityFactory.create_token(state, "Trap")
    assert t1.id == "token_5"
    assert t1.name == "Trap"

def test_id_collision_prevention():
    """
    Verifies that register_entity throws an error on duplicate IDs.
    """
    state = GameState(
        board=Board(),
        teams={}
    )
    
    # Manually insert an entity
    existing_token = EntityFactory.create_token(state, "Existing")
    state.register_entity(existing_token, "token")
    
    # Attempt to register same entity again
    with pytest.raises(ValueError, match="ID Collision"):
        state.register_entity(existing_token, "token")
        
    # Attempt to register a new entity with the same ID (simulated collision)
    collision_token = EntityFactory.create_token(state, "Imposter")
    collision_token.id = existing_token.id # Force ID match
    
    with pytest.raises(ValueError, match="ID Collision"):
        state.register_entity(collision_token, "token")

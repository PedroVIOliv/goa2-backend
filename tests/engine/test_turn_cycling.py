import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, Hero, Card, CardTier, CardColor, ActionType
from goa2.domain.types import HeroID
from goa2.engine.phases import start_resolution_phase
from goa2.engine.handler import process_resolution_stack

def create_hero(id_str, team, initiative):
    card = Card(
        id=f"card_{id_str}",
        name=f"Card {id_str}",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=initiative,
        primary_action=ActionType.SKILL,
        effect_id="e",
        effect_text="t",
        is_facedown=False
    )
    hero = Hero(id=HeroID(id_str), name=id_str, team=team, deck=[])
    hero.current_turn_card = card
    return hero

def test_automatic_turn_cycling():
    hero_a = create_hero("A", TeamColor.RED, 20)
    hero_b = create_hero("B", TeamColor.BLUE, 10)
    hero_c = create_hero("C", TeamColor.RED, 5)

    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero_a, hero_c], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[hero_b], minions=[])
        }
    )
    
    # Setup unresolved pool manually as if Revelation phase just ended
    state.unresolved_hero_ids = ["A", "B", "C"]
    
    # Start Resolution
    # This should prime the stack with A's steps
    start_resolution_phase(state)
    
    # Run the engine
    # Since these cards have no complex steps (phases.py just pushes Log + Finalize), 
    # it should run straight through A -> B -> C -> End.
    process_resolution_stack(state)
    
    # Verification
    
    # 1. All heroes should be out of the unresolved pool
    assert len(state.unresolved_hero_ids) == 0, "Not all heroes resolved!"
    
    # 2. All cards should be in resolved slots (implied by empty current_turn_card)
    assert hero_a.current_turn_card is None
    assert hero_b.current_turn_card is None
    assert hero_c.current_turn_card is None
    
    # 3. Check resolved pile
    assert len(hero_a.played_cards) == 1
    assert len(hero_b.played_cards) == 1
    assert len(hero_c.played_cards) == 1
    
    print("Test passed: Automatic cycling worked for A -> B -> C.")

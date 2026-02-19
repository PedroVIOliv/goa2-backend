from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, Hero, Card, CardTier, CardColor, ActionType
from goa2.domain.types import HeroID
from goa2.engine.phases import start_resolution_phase
from goa2.engine.handler import process_resolution_stack

def _filler_cards():
    """Return dummy hand cards so heroes aren't auto-passed for empty hands."""
    return [Card(
        id=f"filler_{i}", name=f"Filler {i}", tier=CardTier.I, color=CardColor.RED,
        initiative=1, primary_action=ActionType.SKILL, primary_action_value=None,
        effect_id="e", effect_text="t",
    ) for i in range(3)]

def create_hero(id_str, team, initiative):
    # Return JUST the hero, card assignment happens on state object
    hero = Hero(id=HeroID(id_str), name=id_str, team=team, deck=[], hand=_filler_cards())
    return hero

def create_card(id_str, initiative):
    return Card(
        id=f"card_{id_str}",
        name=f"Card {id_str}",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=initiative,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        secondary_actions={ActionType.HOLD: 0},
        effect_id="e",
        effect_text="t",
        is_facedown=False
    )

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
    
    # Assign Cards to State Heroes
    state.get_hero("A").current_turn_card = create_card("A", 20)
    state.get_hero("B").current_turn_card = create_card("B", 10)
    state.get_hero("C").current_turn_card = create_card("C", 5)
    
    # Place heroes on board
    state.move_unit(hero_a.id, Hex(q=0, r=0, s=0))
    state.move_unit(hero_b.id, Hex(q=1, r=0, s=-1))
    state.move_unit(hero_c.id, Hex(q=0, r=1, s=-1))

    # Setup unresolved pool
    state.unresolved_hero_ids = ["A", "B", "C"]
    
    # Start Resolution - Picks A
    start_resolution_phase(state)
    
    # --- Turn A ---
    # 1. Process until Input (ResolveCardStep)
    req = process_resolution_stack(state)
    assert req["type"] == "CHOOSE_ACTION"
    assert req["player_id"] == "A"
    
    # 2. Provide Input (Secondary Hold)
    state.execution_stack[-1].pending_input = {"selection": "HOLD"}
    
    # 3. Process until Next Input (B)
    req = process_resolution_stack(state)
    
    # Should automatically cycle A -> Finalize -> FindNext -> B -> ResolveCardStep
    assert req is not None
    assert req["type"] == "CHOOSE_ACTION"
    assert req["player_id"] == "B"
    
    # --- Turn B ---
    state.execution_stack[-1].pending_input = {"selection": "HOLD"}
    req = process_resolution_stack(state)
    
    assert req is not None
    assert req["type"] == "CHOOSE_ACTION"
    assert req["player_id"] == "C"
    
    # --- Turn C ---
    state.execution_stack[-1].pending_input = {"selection": "HOLD"}
    req = process_resolution_stack(state)
    
    # --- End ---
    assert req is None # Finished
    
    # Verification
    assert len(state.unresolved_hero_ids) == 0
    assert state.get_hero("A").current_turn_card is None
    assert state.get_hero("B").current_turn_card is None
    assert state.get_hero("C").current_turn_card is None
    assert len(state.get_hero("A").played_cards) == 1
    
    print("Test passed: Automatic cycling worked for A -> B -> C.")

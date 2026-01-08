import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Card, CardTier, CardColor, ActionType, Hero, Minion, MinionType
from goa2.domain.types import HeroID, CardID
from goa2.domain.hex import Hex
from goa2.engine.steps import (
    LogMessageStep, SelectStep, 
    ReactionWindowStep, ResolveCombatStep, AttackSequenceStep,
    MoveUnitStep
)
from goa2.engine.handler import process_resolution_stack, push_steps

# --- Fixtures ---

@pytest.fixture
def empty_state():
    board = Board()
    hero_red = Hero(id='hero_red', name='Red Hero', team=TeamColor.RED, deck=[])
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero_red], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[])
        },
        current_actor_id="hero_red"
    )
    actor_hex = Hex(q=2, r=0, s=-2)
    board.tiles[actor_hex] = board.get_tile(actor_hex)
    state.place_entity('hero_red', actor_hex)
    return state

@pytest.fixture
def populated_state():
    h1 = Hero(id="h1", name="Hero1", team=TeamColor.RED, deck=[])
    m1 = Minion(id="m1", name="Minion1", type=MinionType.MELEE, team=TeamColor.RED)
    
    # Create Board with necessary tiles
    start_hex = Hex(q=0, r=0, s=0)
    target_hex = Hex(q=1, r=0, s=-1)
    
    board = Board()
    board.tiles[start_hex] = Tile(hex=start_hex)
    board.tiles[target_hex] = Tile(hex=target_hex)
    
    # Use Unified Placement
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[m1]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[])
        },
        entity_locations={}
    )
    state.place_entity("h1", start_hex)
    return state

@pytest.fixture
def combat_state(empty_state):
    # Setup Red Attacker
    attacker = Hero(name="Red Hero", id=HeroID("hero_red"), team=TeamColor.RED, deck=[])
    empty_state.teams[TeamColor.RED].heroes.append(attacker)
    
    # Setup Blue Defender with Defense Cards
    def_card = Card(
        id=CardID("def_card_1"), 
        name="Shield", 
        tier=CardTier.I, 
        color=CardColor.BLUE, 
        initiative=1, 
        primary_action=ActionType.DEFENSE, 
        primary_action_value=5,
        effect_id="e1", effect_text="e1", is_facedown=False
    )
    # Ensure it's in hand
    defender = Hero(name="Blue Hero", id=HeroID("hero_blue"), team=TeamColor.BLUE, deck=[def_card])
    defender.hand.append(def_card)
    
    empty_state.teams[TeamColor.BLUE].heroes.append(defender)
    
    return empty_state

# --- Tests ---

def test_select_target_flow(empty_state):
    # SelectStep requires at least 1 candidate to not auto-finish with "No candidates"
    # So we must spoof a unit location
    empty_state.place_entity("target_1", Hex(q=0, r=0, s=0))
    # Note: SelectStep now filters for actual units. We need to add target_1 to a team or mock get_unit.
    # We'll use a real unit ID "hero_red" which exists in empty_state default (no, default has empty heroes)
    
    # Add a mock hero so filtering passes
    hero = Hero(id="target_1", name="Target", team=TeamColor.BLUE, deck=[])
    empty_state.teams[TeamColor.BLUE].heroes.append(hero)
    
    step = SelectStep(target_type="UNIT", prompt="Choose", output_key="target_id")
    push_steps(empty_state, [step])
    
    # Pass 1: Request
    req = process_resolution_stack(empty_state)
    assert req is not None
    assert req["type"] == "SELECT_UNIT"
    
    # Pass 2: Provide Input
    empty_state.execution_stack[-1].pending_input = {"selection": "target_1"}
    req = process_resolution_stack(empty_state)
    
    assert req is None # Done
    assert empty_state.execution_context["target_id"] == "target_1"


def test_reaction_window_validation(combat_state):
    # Target Blue Hero
    combat_state.execution_context["target_id"] = "hero_blue"
    
    step = ReactionWindowStep(target_player_key="target_id")
    push_steps(combat_state, [step])
    
    # Pass 1: Request Input
    req = process_resolution_stack(combat_state)
    assert req["type"] == "SELECT_CARD_OR_PASS"
    assert "def_card_1" in req["options"]
    assert "PASS" in req["options"]
    
    # Pass 2: Select Invalid Card
    combat_state.execution_stack[-1].pending_input = {"selected_card_id": "def_card_1"}
    process_resolution_stack(combat_state)
    
    assert combat_state.execution_context["defense_value"] == 5

def test_combat_resolution_block(combat_state):
    # Defense 5 vs Attack 3 -> Blocked
    combat_state.execution_context["defense_value"] = 5
    combat_state.execution_context["victim_id"] = "hero_blue"
    
    step = ResolveCombatStep(damage=3, target_key="victim_id")
    push_steps(combat_state, [step])
    
    process_resolution_stack(combat_state)

def test_combat_resolution_hit(combat_state):
    # Defense 0 vs Attack 3 -> Hit
    combat_state.execution_context["defense_value"] = 0
    combat_state.execution_context["victim_id"] = "hero_blue"
    
    step = ResolveCombatStep(damage=3, target_key="victim_id")
    push_steps(combat_state, [step])
    
    process_resolution_stack(combat_state)
    
def test_attack_sequence_expansion(combat_state):
    # Add an enemy so SelectStep pauses for input
    # combat_state has Red Hero (current actor). Add Blue Hero in Range 1.
    target_hex = Hex(q=1, r=0, s=-1)
    combat_state.place_entity("hero_blue", target_hex)
    combat_state.place_entity("hero_red", Hex(q=0, r=0, s=0))
    
    # Check that the Macro step expands into 3 steps
    step = AttackSequenceStep(damage=3, range_val=1)
    push_steps(combat_state, [step])
    
    # Run once to expand
    process_resolution_stack(combat_state)
    
    # Now stack should have SelectStep at top waiting for input
    current = combat_state.execution_stack[-1]
    assert isinstance(current, SelectStep)

# --- Pathfinding Tests ---

def test_move_unit_pathfinding(populated_state):
    # Valid Move: 1 step
    populated_state.execution_context["target_hex"] = Hex(q=1, r=0, s=-1)
    step = MoveUnitStep(unit_id="h1", range_val=1)
    
    res = step.resolve(populated_state, populated_state.execution_context)
    assert res.is_finished
    assert populated_state.entity_locations["h1"] == Hex(q=1, r=0, s=-1)

def test_move_unit_invalid_path(populated_state):
    # Invalid Move: 5 steps away, range 1
    populated_state.execution_context["target_hex"] = Hex(q=5, r=0, s=-5)
    step = MoveUnitStep(unit_id="h1", range_val=1)
    
    start_loc = populated_state.entity_locations["h1"]
    res = step.resolve(populated_state, populated_state.execution_context)
    
    assert res.is_finished
    # Should NOT have moved
    assert populated_state.entity_locations["h1"] == start_loc

# --- Error Handling Tests ---

def test_move_unit_error_handling(empty_state):
    # No actor
    step = MoveUnitStep(unit_id=None, destination_key="dest")
    empty_state.current_actor_id = None
    res = step.resolve(empty_state, {"dest": Hex(q=0,r=0,s=0)})
    assert res.is_finished
    
    # No destination
    step2 = MoveUnitStep(unit_id="h1", destination_key="missing_key")
    res2 = step2.resolve(empty_state, {})
    assert res2.is_finished

def test_log_message(empty_state):
    step = LogMessageStep(message="Hello {name}")
    res = step.resolve(empty_state, {"name": "World"})
    assert res.is_finished

# --- Reaction Window Minion Tests ---

def test_reaction_window_minion_skip(combat_state):
    # Setup: Add a Minion to Blue Team
    m1 = Minion(id="minion_blue", name="Blue Minion", type=MinionType.MELEE, team=TeamColor.BLUE)
    combat_state.teams[TeamColor.BLUE].minions.append(m1)
    
    # Target the Minion
    combat_state.execution_context["target_id"] = "minion_blue"
    
    step = ReactionWindowStep(target_player_key="target_id")
    push_steps(combat_state, [step])
    
    # Run stack
    req = process_resolution_stack(combat_state)
    
    # Assertions
    assert req is None  # Should not request input
    assert combat_state.execution_context.get("defense_value") == 0 # Defense forced to 0
    assert not combat_state.execution_stack # Stack should be empty

def test_reaction_window_hero_prompt(combat_state):
    # Target Blue Hero (who has cards, from fixture)
    combat_state.execution_context["target_id"] = "hero_blue"
    
    step = ReactionWindowStep(target_player_key="target_id")
    push_steps(combat_state, [step])
    
    # Run stack
    req = process_resolution_stack(combat_state)
    
    # Assertions
    assert req is not None
    assert req["type"] == "SELECT_CARD_OR_PASS"
    assert req["player_id"] == "hero_blue"
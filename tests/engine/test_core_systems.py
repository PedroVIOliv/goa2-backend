import pytest
from goa2.domain.state import GameState
from goa2.domain.models import TeamColor, Hero, Card, ActionType, CardTier, CardColor, CardState, GamePhase, Team
from goa2.domain.hex import Hex
from goa2.engine import phases, rules
from goa2.domain.board import Board, Tile

def create_empty_state():
    """Helper to create a valid empty GameState."""
    board = Board(hexes={}, zones={}, tiles={})
    teams = {
        TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
        TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[])
    }
    return GameState(board=board, teams=teams)

# -----------------------------------------------------------------------------
# 1. Test Phases (Turn Structure)
# -----------------------------------------------------------------------------

def test_phases_commit_and_revelation():
    """Test the card commitment and revelation flow."""
    # Setup State with 2 Heroes
    state = create_empty_state()
    
    # Mock Heroes
    h1 = Hero(id="h1", name="Hero1", team=TeamColor.RED, deck=[])
    h2 = Hero(id="h2", name="Hero2", team=TeamColor.BLUE, deck=[])
    state.teams[TeamColor.RED].heroes.append(h1)
    state.teams[TeamColor.BLUE].heroes.append(h2)
    
    # Mock Cards
    c1 = Card(id="c1", name="C1", color=CardColor.RED, primary_action=ActionType.ATTACK, initiative=10, tier=CardTier.I, effect_id="e1", effect_text="Test")
    c2 = Card(id="c2", name="C2", color=CardColor.BLUE, primary_action=ActionType.SKILL, initiative=20, tier=CardTier.I, effect_id="e2", effect_text="Test")
    
    # 1. Planning Phase
    state.phase = GamePhase.PLANNING
    phases.commit_card(state, "h1", c1)
    
    assert state.pending_inputs["h1"] == c1
    assert state.phase == GamePhase.PLANNING # Not done yet
    
    # 2. Commit second card -> Trigger Revelation
    phases.commit_card(state, "h2", c2)
    
    assert state.phase == GamePhase.RESOLUTION # Should auto-transition through Revelation to Resolution
    
    # process_next_in_queue is called automatically, so 1 card is already popped
    assert len(state.resolution_queue) == 1 
    assert state.current_actor_id == "h2" # Highest init (20) went first
    
    # The remaining card in queue should be h1
    assert state.resolution_queue[0][0] == "h1"

def test_phases_process_queue_tie_handling():
    """Test that ties are detected and handled."""
    state = create_empty_state()
    state.phase = GamePhase.RESOLUTION
    
    c1 = Card(id="c1", name="C1", color=CardColor.RED, primary_action=ActionType.ATTACK, initiative=10, tier=CardTier.I, effect_id="e1", effect_text="Test")
    c2 = Card(id="c2", name="C2", color=CardColor.BLUE, primary_action=ActionType.SKILL, initiative=10, tier=CardTier.I, effect_id="e2", effect_text="Test")
    
    # Manually populate queue with a tie
    state.resolution_queue = [("h1", c1), ("h2", c2)]
    
    phases.process_next_in_queue(state)
    
    # Should have pushed a ResolveTieBreakerStep
    assert len(state.execution_stack) > 0
    step = state.execution_stack[-1]
    assert step.type == "resolve_tie_breaker"
    assert set(step.tied_hero_ids) == {"h1", "h2"}

# -----------------------------------------------------------------------------
# 2. Test Rules (Physics & Targeting)
# -----------------------------------------------------------------------------

def test_rules_validate_target_geometry():
    """Test straight line and range validation."""
    state = create_empty_state()
    # No map needed for pure geometry if unit_locations set
    h1 = Hero(id="h1", name="A", team=TeamColor.RED, deck=[])
    h2 = Hero(id="h2", name="B", team=TeamColor.BLUE, deck=[])
    
    state.unit_locations["h1"] = Hex(q=0, r=0, s=0)
    
    # Case 1: Adjacent (Valid)
    state.unit_locations["h2"] = Hex(q=1, r=-1, s=0) 
    assert rules.validate_target(h1, h2, ActionType.ATTACK, state, range_val=1) is True
    
    # Case 2: Out of Range
    state.unit_locations["h2"] = Hex(q=2, r=-2, s=0)
    assert rules.validate_target(h1, h2, ActionType.ATTACK, state, range_val=1) is False
    
    # Case 3: Straight Line Requirement
    state.unit_locations["h2"] = Hex(q=2, r=-2, s=0) # Is straight line
    assert rules.validate_target(h1, h2, ActionType.ATTACK, state, range_val=3, requires_straight_line=True) is True
    
    state.unit_locations["h2"] = Hex(q=1, r=1, s=-2) # Not straight line from 0,0,0
    assert rules.validate_target(h1, h2, ActionType.ATTACK, state, range_val=3, requires_straight_line=True) is False

def test_rules_validate_movement_obstacles():
    """Test movement validation against obstacles."""
    state = create_empty_state()
    # Setup board with obstacle at 1, -1, 0
    obs_hex = Hex(q=1, r=-1, s=0)
    state.board.tiles[obs_hex] = Tile(q=1, r=-1, s=0, is_terrain=True, hex=obs_hex)
    
    # Setup Unit at 0,0,0
    state.unit_locations["u1"] = Hex(q=0, r=0, s=0)
    
    # Try to move TO obstacle
    assert rules.validate_movement_path(state.board, state.unit_locations, Hex(q=0, r=0, s=0), obs_hex, 1) is False
    
    # Try to move THROUGH obstacle to 2, -2, 0
    target = Hex(q=2, r=-2, s=0)
    # BFS should fail if range is tight. 
    # Path: 0,0,0 -> 1,-1,0 (Blocked) -> 2,-2,0. 
    # Alternative path: 0,0,0 -> 0,-1,1 -> 1,-2,1 -> 2,-2,0 (Length 3). 
    # If Max Steps = 2, should fail.
    assert rules.validate_movement_path(state.board, state.unit_locations, Hex(q=0, r=0, s=0), target, 2) is False

# -----------------------------------------------------------------------------
# 3. Test Hex Math
# -----------------------------------------------------------------------------

def test_hex_advanced_geometry():
    """Test complex hex methods (ring, line_to, direction)."""
    center = Hex(q=0, r=0, s=0)
    
    # Ring
    ring_1 = center.ring(1)
    assert len(ring_1) == 6
    assert Hex(q=1, r=-1, s=0) in ring_1
    
    # Line To
    target = Hex(q=3, r=-3, s=0)
    line = center.line_to(target)
    assert len(line) == 3
    assert line[-1] == target
    assert line[0] == Hex(q=1, r=-1, s=0)
    
    # Line To (Invalid)
    with pytest.raises(ValueError):
        center.line_to(Hex(q=1, r=-2, s=1))
        
    # Direction To
    d_idx = center.direction_to(Hex(q=2, r=-2, s=0)) # E (1, -1, 0) is index 1?
    # Vectors: 0:NE(1,0,-1), 1:E(1,-1,0)
    assert d_idx == 1 
    
    assert center.direction_to(Hex(q=5, r=5, s=-10)) is None # Not straight
    assert center.direction_to(center) is None
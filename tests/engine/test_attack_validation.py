import pytest
from goa2.domain.state import GameState
from goa2.domain.models import TeamColor, Hero, Minion, Team, ActionType, MinionType, Card, CardTier, CardColor
from goa2.domain.hex import Hex
from goa2.domain.board import Board, Tile, Zone
from goa2.engine import rules
from goa2.engine.steps import ResolveCardStep, SelectStep
from goa2.engine.handler import process_resolution_stack, push_steps

@pytest.fixture
def base_state():
    """Helper to create a standard test state."""
    board = Board()
    # Add some tiles
    for q in range(-3, 4):
        for r in range(-3, 4):
            s = -q - r
            # Only keep hexes within range for a typical board
            if abs(s) <= 3:
                h = Hex(q=q, r=r, s=s)
                board.tiles[h] = Tile(hex=h)
            
    teams = {
        TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
        TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[])
    }
    state = GameState(board=board, teams=teams, entity_locations={})
    state.active_zone_id = "z1"
    board.zones["z1"] = Zone(id="z1", label="Zone 1", hexes=list(board.tiles.keys()))
    
    return state

def test_basic_attack_valid(base_state):
    """Test standard attack within range."""
    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, deck=[])
    m1 = Minion(id="m1", name="M1", type=MinionType.MELEE, team=TeamColor.BLUE)
    
    base_state.teams[TeamColor.RED].heroes.append(h1)
    base_state.teams[TeamColor.BLUE].minions.append(m1)
    
    base_state.place_entity("h1", Hex(q=0, r=0, s=0))
    base_state.place_entity("m1", Hex(q=1, r=0, s=-1)) # distance 1
    
    assert rules.validate_attack_target(
        attacker_pos=Hex(q=0, r=0, s=0),
        target_pos=Hex(q=1, r=0, s=-1),
        range_val=1,
        state=base_state,
        attacker=h1,
        target=m1
    ) is True

def test_attack_out_of_range(base_state):
    """Test attack fails when target is beyond range_val."""
    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, deck=[])
    m1 = Minion(id="m1", name="M1", type=MinionType.MELEE, team=TeamColor.BLUE)
    
    base_state.place_entity("h1", Hex(q=0, r=0, s=0))
    base_state.place_entity("m1", Hex(q=2, r=0, s=-2)) # distance 2
    
    assert rules.validate_attack_target(
        attacker_pos=Hex(q=0, r=0, s=0),
        target_pos=Hex(q=2, r=0, s=-2),
        range_val=1,
        state=base_state,
        attacker=h1,
        target=m1
    ) is False

def test_attack_immune_target(base_state):
    """Test attack fails when target is a Heavy with protection."""
    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, deck=[])
    heavy = Minion(id="heavy", name="Heavy", type=MinionType.HEAVY, team=TeamColor.BLUE)
    m2 = Minion(id="m2", name="M2", type=MinionType.MELEE, team=TeamColor.BLUE)
    
    base_state.teams[TeamColor.RED].heroes.append(h1)
    base_state.teams[TeamColor.BLUE].minions.extend([heavy, m2])
    
    base_state.place_entity("h1", Hex(q=0, r=0, s=0))
    base_state.place_entity("heavy", Hex(q=1, r=0, s=-1))
    base_state.place_entity("m2", Hex(q=2, r=0, s=-2)) # Another friendly minion in the same zone
    
    # Verify immunity check separately
    assert rules.is_immune(heavy, base_state) is True
    
    assert rules.validate_attack_target(
        attacker_pos=Hex(q=0, r=0, s=0),
        target_pos=Hex(q=1, r=0, s=-1),
        range_val=1,
        state=base_state,
        attacker=h1,
        target=heavy
    ) is False

def test_attack_straight_line_required(base_state):
    """Test straight line requirement."""
    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, deck=[])
    m1 = Minion(id="m1", name="M1", type=MinionType.MELEE, team=TeamColor.BLUE)
    
    base_state.place_entity("h1", Hex(q=0, r=0, s=0))
    
    # Case 1: Straight line (Valid)
    pos_straight = Hex(q=2, r=0, s=-2)
    base_state.place_entity("m1", pos_straight)
    assert rules.validate_attack_target(
        attacker_pos=Hex(q=0, r=0, s=0),
        target_pos=pos_straight,
        range_val=3,
        requires_straight_line=True,
        state=base_state,
        attacker=h1,
        target=m1
    ) is True
    
    # Case 2: Not a straight line (Invalid)
    pos_not_straight = Hex(q=2, r=-1, s=-1) # distance 2, but not straight
    base_state.place_entity("m1", pos_not_straight)
    assert rules.validate_attack_target(
        attacker_pos=Hex(q=0, r=0, s=0),
        target_pos=pos_not_straight,
        range_val=3,
        requires_straight_line=True,
        state=base_state,
        attacker=h1,
        target=m1
    ) is False

def test_attack_legacy_fallback(base_state):
    """Test fallback when state/attacker/target are missing."""
    # Note: validate_attack_target NO LONGER ACCEPTS unit_locations map.
    # It relies on positional args purely for geometry if state is missing.
    
    # Valid range
    assert rules.validate_attack_target(
        attacker_pos=Hex(q=0, r=0, s=0),
        target_pos=Hex(q=1, r=0, s=-1),
        range_val=1
    ) is True
    
    # Out of range
    assert rules.validate_attack_target(
        attacker_pos=Hex(q=0, r=0, s=0),
        target_pos=Hex(q=2, r=0, s=-2),
        range_val=1
    ) is False

def test_attack_missing_locations(base_state):
    """Test failure when units missing from entity_locations."""
    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, deck=[])
    m1 = Minion(id="m1", name="M1", type=MinionType.MELEE, team=TeamColor.BLUE)
    
    # h1 is NOT in entity_locations
    base_state.place_entity("m1", Hex(q=1, r=0, s=-1))
    
    assert rules.validate_attack_target(
        attacker_pos=Hex(q=0, r=0, s=0),
        target_pos=Hex(q=1, r=0, s=-1),
        range_val=5,
        state=base_state,
        attacker=h1,
        target=m1
    ) is False

def test_secondary_attack_respects_immunity(base_state):
    """
    Test that when a player chooses a Secondary Attack, 
    the resulting SelectStep respects immunity (hiding immune heavies).
    """
    # 1. Setup Hero with Card (Secondary Attack 3)
    card = Card(
        id="c1", name="Test Card", tier=CardTier.I, color=CardColor.RED,
        initiative=10, primary_action=ActionType.SKILL, primary_action_value=None,
        secondary_actions={ActionType.ATTACK: 3}, range_value=1,
        effect_id="e1", effect_text="e1", is_facedown=False
    )
    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, deck=[])
    h1.current_turn_card = card
    base_state.teams[TeamColor.RED].heroes.append(h1)
    base_state.current_actor_id = "h1"

    # 2. Setup targets: Heavy (Immune) and Melee (Not Immune)
    heavy = Minion(id="heavy", name="Heavy", type=MinionType.HEAVY, team=TeamColor.BLUE)
    melee = Minion(id="melee", name="Melee", type=MinionType.MELEE, team=TeamColor.BLUE)
    base_state.teams[TeamColor.BLUE].minions.extend([heavy, melee])
    
    # Place units using place_entity (Corrects SelectStep finding them)
    base_state.place_entity("h1", Hex(q=0, r=0, s=0))
    base_state.place_entity("heavy", Hex(q=1, r=0, s=-1))
    base_state.place_entity("melee", Hex(q=1, r=-1, s=0))
    
    # Add one more minion to ensure Heavy is immune (Rule 3.2)
    m_supp = Minion(id="m_supp", name="Support", type=MinionType.MELEE, team=TeamColor.BLUE)
    base_state.teams[TeamColor.BLUE].minions.append(m_supp)
    base_state.place_entity("m_supp", Hex(q=2, r=0, s=-2))
    
    # 3. Start ResolveCardStep
    step = ResolveCardStep(hero_id="h1")
    push_steps(base_state, [step])
    
    # 4. CHOOSE_ACTION prompt
    req = process_resolution_stack(base_state)
    assert req["type"] == "CHOOSE_ACTION"
    
    # 5. Select Secondary ATTACK
    base_state.execution_stack[-1].pending_input = {"choice_id": "ATTACK"}
    
    # 6. Next step should be SelectStep (from AttackSequenceStep expansion)
    req2 = process_resolution_stack(base_state)
    
    # If SelectStep finds candidates, it prompts SELECT_UNIT.
    # If it finds NO candidates (because logic was broken), it returns None (abort).
    assert req2 is not None
    assert req2["type"] == "SELECT_UNIT"
    
    # 7. VERIFY: 'heavy' is filtered out, 'melee' is valid
    valid = req2["valid_options"]
    assert "melee" in valid
    assert "heavy" not in valid # SHOULD BE IMMUNE

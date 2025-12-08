import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone, SpawnPoint, SpawnType
from goa2.domain.models import TeamColor, Team, Minion, MinionType, Token, Card, Hero, CardTier, CardColor, ActionType, CardState
from goa2.domain.hex import Hex
from goa2.domain.types import UnitID, BoardEntityID, HeroID
from goa2.engine.mechanics import perform_lane_push, run_end_phase, spawn_minion_wave
from goa2.engine.phases import GamePhase

@pytest.fixture
def extended_state():
    # Setup board
    z1 = Zone(id="z1", hexes={Hex(q=0,r=0,s=0)})
    z2 = Zone(id="z2", hexes={Hex(q=1,r=-1,s=0)})
    
    board = Board(
        zones={"z1": z1, "z2": z2},
        lane=["z1", "z2"],
        spawn_points=[
            SpawnPoint(location=Hex(q=1,r=-1,s=0), team=TeamColor.RED, type=SpawnType.MINION, minion_type=MinionType.MELEE)
        ]
    )
    board.populate_tiles_from_zones()
    
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED),
            TeamColor.BLUE: Team(color=TeamColor.BLUE)
        },
        active_zone_id="z2",
        wave_counter=1 # Critical for Game Over test
    )
    return state

def test_lane_push_game_over(extended_state):
    # Setup: Wave Counter is 1. Push triggers. Should hit 0 -> Game Over check.
    # Note: perform_lane_push currently prints "GAME OVER". 
    # To verify properly, we might check if it returns early or effectively stops state changes if needed.
    # Or ideally logic should raise Event or set State.winner.
    # For now, we verify wave counter reaches 0.
    
    # Needs a losing condition (Red has 0, Blue > 0)
    m_blue = Minion(id=UnitID("b1"), type=MinionType.MELEE, team=TeamColor.BLUE, name="B")
    extended_state.teams[TeamColor.BLUE].minions.append(m_blue)
    extended_state.unit_locations[m_blue.id] = Hex(q=1,r=-1,s=0) # In z2
    
    perform_lane_push(extended_state)
    
    assert extended_state.wave_counter == 0
    # And logic checked <= 0.
    
    # Also Check Base Destruction logic
    # If we are at index 0 (z1) and Red loses (Push to -1)
    extended_state.active_zone_id = "z1"
    extended_state.wave_counter = 5 # Reset wave
    
    # Red has 0 in z1, Blue has 1 in z1
    extended_state.unit_locations[m_blue.id] = Hex(q=0,r=0,s=0)
    
    perform_lane_push(extended_state)
    
    # Should print BASE DESTROYED and return (not crash)
    # New zone should NOT update if valid check works, or handled.
    # Code says: if new_idx < 0: return.
    # So active_zone_id remains "z1".
    assert extended_state.active_zone_id == "z1"

def test_token_persistence_vs_stomp(extended_state):
    # Scenario: Token in Active Zone. Lane Push happens.
    # 1. Token Persistence: Token in non-spawn hex SHOULD stay.
    non_spawn_hex = Hex(q=2, r=-2, s=0) # Not in spawn points list
    # Cheat: Add this hex to zone z2 so it's valid context
    extended_state.board.zones["z2"].hexes.add(non_spawn_hex)
    extended_state.board.tiles[non_spawn_hex] = extended_state.board.tiles[Hex(q=1,r=-1,s=0)].model_copy(update={"hex": non_spawn_hex}) 
    
    extended_state.board.tiles[non_spawn_hex].occupant_id = BoardEntityID("token_keep")
    
    # 2. Token Stomp: Token in Spawn Point hex SHOULD be removed.
    spawn_hex = Hex(q=1, r=-1, s=0) # Is a Red Spawn Point
    extended_state.board.tiles[spawn_hex].occupant_id = BoardEntityID("token_stomp")
    
    # Trigger Push into z2?
    # Wait, "spawn_minion_wave" is called for the NEW zone.
    # We need to transition INTO z2.
    # Current active: z1.
    # Lane: [z1, z2].
    # We want to push from z1 -> z2.
    # Who loses implies direction. 
    # Red Base is z1. Blue Base is z2 (logic wise).
    # If index 0 (z1) checks out... 
    # If Blue loses in z1 -> Push to z2.
    
    extended_state.active_zone_id = "z1"
    # Blue has 0 in z1. Red has 1.
    m_red = Minion(id=UnitID("r1"), type=MinionType.MELEE, team=TeamColor.RED, name="R")
    extended_state.teams[TeamColor.RED].minions.append(m_red)
    extended_state.unit_locations[m_red.id] = Hex(q=0,r=0,s=0)
    
    extended_state.wave_counter = 5
    # Execute Push
    perform_lane_push(extended_state)
    
    # Check Active Zone is now z2
    assert extended_state.active_zone_id == "z2"
    
    # Check Token Persistence (Non-Spawn)
    assert extended_state.board.tiles[non_spawn_hex].occupant_id == "token_keep"
    
    # Check Token Stomp (Spawn)
    # Should now be occupied by a MINION (UnitID), not "token_stomp"
    occ_id = extended_state.board.tiles[spawn_hex].occupant_id
    assert occ_id != "token_stomp"
    assert occ_id is not None
    # Confirm it is the spawned minion
    assert occ_id in extended_state.unit_locations

def test_card_retrieval(extended_state):
    # Setup Hero with cards in Discard
    hero = Hero(id=HeroID("h1"), name="Hero", deck=[])
    c1 = Card(
        id="c1", 
        name="C1", 
        tier=CardTier.I, 
        color=CardColor.RED, 
        initiative=10, 
        primary_action=ActionType.ATTACK, 
        effect_id="e1", 
        effect_text="t",
        state=CardState.DISCARD
    )
    c2 = Card(
        id="c2", 
        name="C2", 
        tier=CardTier.UNTIERED, 
        color=CardColor.GOLD, 
        initiative=99,
        primary_action=ActionType.SKILL,
        effect_id="e2",
        effect_text="t",
        state=CardState.HAND # Already in hand
    )
    hero.deck = [c1, c2]
    hero.discard_pile = [c1]
    hero.hand = [c2]
    
    extended_state.teams[TeamColor.RED].heroes.append(hero)
    
    # Run End Phase
    run_end_phase(extended_state)
    
    # Verify
    assert len(hero.hand) == 2
    assert c1 in hero.hand
    assert c2 in hero.hand
    assert c1.state == CardState.HAND
    assert len(hero.discard_pile) == 0

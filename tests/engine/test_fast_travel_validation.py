
import pytest
from goa2.domain.state import GameState, InputRequest, InputRequestType
from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, Hero, Card, CardTier, CardColor, ActionType, Minion
from goa2.engine.actions import PerformMovementCommand, PlayCardCommand, ResolveNextCommand, ChooseActionCommand
from goa2.domain.types import HeroID, CardID, UnitID
from goa2.engine.phases import GamePhase


@pytest.fixture
def ft_validation_state():
    # 1. Setup Board with 3 Zones
    # Zone 1: Start (0,0,0)
    # Zone 2: Far Target (10,0,-10) - Non-adjacent coordinate-wise
    # Zone 3: Enemy Zone (5,0,-5)
    
    b = Board()
    
    h_start = Hex(q=0, r=0, s=0)
    h_same_zone_dest = Hex(q=0, r=1, s=-1) # Dist 1
    
    h_far = Hex(q=10, r=0, s=-10) # Dist 10
    
    h_enemy = Hex(q=5, r=0, s=-5)
    
    z1 = Zone(id="z_start", hexes={h_start, h_same_zone_dest}, neighbors=["z_adj"])
    z2 = Zone(id="z_far", hexes={h_far}) # z_far is NOT neighbor of z_start
    z3 = Zone(id="z_enemy", hexes={h_enemy})
    z4 = Zone(id="z_adj", hexes={Hex(q=0, r=-1, s=1)}, neighbors=["z_start"]) # Adjacent Zone
    
    b.zones = {
        "z_start": z1,
        "z_far": z2,
        "z_enemy": z3,
        "z_adj": z4
    }
    b.populate_tiles_from_zones()
    
    # 2. Setup Hero
    c_ft = Card(
        id=CardID("c_ft"), name="Teleport", tier=CardTier.UNTIERED, color=CardColor.GOLD,
        initiative=10, primary_action=ActionType.FAST_TRAVEL, secondary_actions={},
        effect_id="e", effect_text="FT"
    )
    
    hero = Hero(id=HeroID("h1"), name="Traveler", team=TeamColor.RED, deck=[], hand=[c_ft])
    
    state = GameState(board=b, teams={TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero])}, phase=GamePhase.PLANNING)
    state.unit_locations[UnitID("h1")] = h_start
    if h_start in b.tiles:
        b.tiles[h_start].occupant_id = "h1"
        
    return state, hero, h_far, h_same_zone_dest, h_enemy, z4.hexes.pop()

def test_ft_non_adjacent_fail(ft_validation_state):
    """
    Invalid: Fast Travel to non-adjacent zone (simulated by far distance AND no neighbor link).
    """
    state, hero, h_far, _, _, _ = ft_validation_state
    
    # Setup Input Stack for Move
    # We manually push the stack to simulate being in the middle of Action
    # ResolveNext -> Choose Action -> ...
    
    # Let's mock the Resolution Queue
    state.phase = GamePhase.RESOLUTION
    state.resolution_queue = [(HeroID("h1"), hero.hand[0])]
    
    # Set up the Movement Request
    req = InputRequest(
        id="req1", 
        player_id=HeroID("h1"), 
        request_type=InputRequestType.FAST_TRAVEL_DESTINATION,
    )
    state.input_stack.append(req)
    
    # EXECUTE
    # Now using dedicated command
    from goa2.engine.actions import PerformFastTravelCommand
    cmd = PerformFastTravelCommand(target_hex=h_far)
    
    # Expectation: Should FAIL because z_far is not a neighbor of z_start
    with pytest.raises(ValueError, match="Destination not adjacent"):
        cmd.execute(state)

def test_ft_adjacent_success(ft_validation_state):
    """
    Valid: Fast Travel to Adjacent Zone.
    """
    state, hero, _, _, _, h_adj = ft_validation_state
    
    state.phase = GamePhase.RESOLUTION
    state.resolution_queue = [(HeroID("h1"), hero.hand[0])]
    
    req = InputRequest(
        id="req1", 
        player_id=HeroID("h1"), 
        request_type=InputRequestType.FAST_TRAVEL_DESTINATION,
    )
    state.input_stack.append(req)
    
    from goa2.engine.actions import PerformFastTravelCommand
    cmd = PerformFastTravelCommand(target_hex=h_adj)
    
    cmd.execute(state)
    assert state.unit_locations[UnitID("h1")] == h_adj

def test_ft_same_zone_success(ft_validation_state):
    """
    Valid: Fast Travel to same zone (User correction).
    """
    state, hero, _, h_same_zone_dest, _, _ = ft_validation_state
    
    state.phase = GamePhase.RESOLUTION
    state.resolution_queue = [(HeroID("h1"), hero.hand[0])]
    
    req = InputRequest(
        id="req1", 
        player_id=HeroID("h1"), 
        request_type=InputRequestType.FAST_TRAVEL_DESTINATION,
    )
    state.input_stack.append(req)
    
    # Now using dedicated command
    from goa2.engine.actions import PerformFastTravelCommand
    cmd = PerformFastTravelCommand(target_hex=h_same_zone_dest)
    
    # Expectation: Should SUCCEED now
    cmd.execute(state)
    
    assert state.unit_locations[UnitID("h1")] == h_same_zone_dest

def test_ft_enemy_in_dest_fail(ft_validation_state):
    """
    Invalid: Enemies in Destination Zone.
    """
    state, hero, _, _, h_enemy, _ = ft_validation_state
    
    # Place Enemy in z_enemy
    enemy_hero = Hero(id=HeroID("h_bad"), name="Baddie", team=TeamColor.BLUE, deck=[], hand=[])
    state.teams[TeamColor.BLUE] = Team(color=TeamColor.BLUE, heroes=[enemy_hero])
    state.unit_locations[UnitID("h_bad")] = h_enemy
    if h_enemy in state.board.tiles:
        state.board.tiles[h_enemy].occupant_id = "h_bad"
        
    # Prepare FT
    state.phase = GamePhase.RESOLUTION
    state.resolution_queue = [(HeroID("h1"), hero.hand[0])]
    
    req = InputRequest(
        id="req1", 
        player_id=HeroID("h1"), 
        request_type=InputRequestType.FAST_TRAVEL_DESTINATION,
    )
    state.input_stack.append(req)
    
    # Hex in z_enemy (occupied by enemy, but let's try to move to another hex in that zone strictly?)
    # Since z_enemy only has 1 hex which is occupied, we also hit "Target Occupied".
    # Need zone with empty hex.
    
    # Update Zone 3 to have 2 hexes
    h_enemy_empty = Hex(q=5, r=1, s=-6)
    state.board.zones["z_enemy"].hexes.add(h_enemy_empty)
    state.board.populate_tiles_from_zones()
    
    # Now using dedicated command
    from goa2.engine.actions import PerformFastTravelCommand
    cmd = PerformFastTravelCommand(target_hex=h_enemy_empty)
    
    with pytest.raises(ValueError, match="Enemies in Dest Zone"):
        cmd.execute(state)


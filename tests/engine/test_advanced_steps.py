import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType
from goa2.domain.hex import Hex
from goa2.engine.steps import PlaceUnitStep, SwapUnitsStep, PushUnitStep, RespawnHeroStep, RespawnMinionStep
from goa2.domain.models.spawn import SpawnPoint, SpawnType

@pytest.fixture
def base_state():
    board = Board()
    for q in range(-5, 6):
        for r in range(-5, 6):
            try:
                h = Hex(q=q, r=r, s=-q-r)
                board.tiles[h] = Tile(hex=h)
            except ValueError:
                continue
                
    h1 = Hero(id="h1", name="Hero1", team=TeamColor.RED, deck=[])
    h2 = Hero(id="h2", name="Hero2", team=TeamColor.BLUE, deck=[])
    
    # Add Minions for Respawn test
    m1 = Minion(id="m1", name="RedMelee1", type=MinionType.MELEE, team=TeamColor.RED)
    
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[m1]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[h2], minions=[])
        },
        entity_locations={}
    )
    # Sync board tiles
    state.place_entity("h1", Hex(q=0, r=0, s=0))
    state.place_entity("h2", Hex(q=1, r=0, s=-1))
    
    return state

def test_place_unit_step(base_state):
    dest = Hex(q=2, r=0, s=-2)
    step = PlaceUnitStep(unit_id="h1", destination_key="dest")
    context = {"dest": dest}
    
    res = step.resolve(base_state, context)
    assert res.is_finished
    assert base_state.entity_locations["h1"] == dest
    assert base_state.board.get_tile(dest).occupant_id == "h1"
    assert base_state.board.get_tile(Hex(q=0, r=0, s=0)).occupant_id is None

def test_place_unit_occupied(base_state):
    # Occupy the target
    dest = Hex(q=1, r=0, s=-1) # Occupied by h2
    
    step = PlaceUnitStep(unit_id="h1", destination_key="dest")
    context = {"dest": dest}
    
    res = step.resolve(base_state, context)
    assert res.is_finished
    
    # Assert h1 did NOT move
    assert base_state.entity_locations["h1"] == Hex(q=0, r=0, s=0)
    # Assert h2 is still there
    assert base_state.board.get_tile(dest).occupant_id == "h2"

def test_swap_units_step(base_state):
    loc1 = Hex(q=0, r=0, s=0)
    loc2 = Hex(q=1, r=0, s=-1)
    
    step = SwapUnitsStep(unit_a_id="h1", unit_b_id="h2")
    res = step.resolve(base_state, {})
    
    assert res.is_finished
    assert base_state.entity_locations["h1"] == loc2
    assert base_state.entity_locations["h2"] == loc1
    assert base_state.board.get_tile(loc1).occupant_id == "h2"
    assert base_state.board.get_tile(loc2).occupant_id == "h1"

def test_respawn_minion_occupied(base_state):
    # Setup Active Zone
    base_state.active_zone_id = "test_zone"
    zone_hexes = [Hex(q=0, r=0, s=0), Hex(q=1, r=0, s=-1)]
    base_state.board.zones["test_zone"] = Zone(id="test_zone", name="Test", hexes=zone_hexes)
    
    # Occupy the spawn hex with h1 (already there from fixture)
    spawn_hex = Hex(q=0, r=0, s=0) 
    base_state.board.get_tile(spawn_hex).zone_id = "test_zone"

    # Define Spawn Point
    base_state.board.get_tile(spawn_hex).spawn_point = SpawnPoint(
        location=spawn_hex, team=TeamColor.RED, type=SpawnType.MINION, minion_type=MinionType.MELEE
    )
    
    # Attempt Respawn
    step = RespawnMinionStep(team=TeamColor.RED, minion_type=MinionType.MELEE)
    step.pending_input = {"selection": {"q": 0, "r": 0, "s": 0}}
    
    res = step.resolve(base_state, {})
    
    # Should finish but NOT move the minion
    assert res.is_finished
    assert "m1" not in base_state.entity_locations
    assert base_state.board.get_tile(spawn_hex).occupant_id == "h1"

def test_push_unit_step_basic(base_state):
    # h1 at (0,0,0), h2 at (1,0,-1)
    step = PushUnitStep(target_id="h2", source_hex=Hex(q=0, r=0, s=0), distance=1)
    res = step.resolve(base_state, {})
    
    assert res.is_finished
    assert base_state.entity_locations["h2"] == Hex(q=2, r=0, s=-2)

def test_push_unit_blocked_by_obstacle(base_state):
    # Place obstacle at (2,0,-2)
    base_state.board.get_tile(Hex(q=2, r=0, s=-2)).is_terrain = True
    
    step = PushUnitStep(target_id="h2", source_hex=Hex(q=0, r=0, s=0), distance=2)
    res = step.resolve(base_state, {})
    
    assert res.is_finished
    assert base_state.entity_locations["h2"] == Hex(q=1, r=0, s=-1)

def test_push_unit_blocked_by_unit(base_state):
    # Place h3 at (2,0,-2)
    h3 = Hero(id="h3", name="Hero3", team=TeamColor.BLUE, deck=[])
    base_state.teams[TeamColor.BLUE].heroes.append(h3)
    base_state.place_entity("h3", Hex(q=2, r=0, s=-2))
    
    step = PushUnitStep(target_id="h2", source_hex=Hex(q=0, r=0, s=0), distance=2)
    res = step.resolve(base_state, {})
    
    assert res.is_finished
    assert base_state.entity_locations["h2"] == Hex(q=1, r=0, s=-1)

def test_respawn_hero_step(base_state):
    base_state.remove_unit("h1")
    spawn_hex = Hex(q=-3, r=0, s=3)
    sp = SpawnPoint(location=spawn_hex, team=TeamColor.RED, type=SpawnType.HERO)
    base_state.board.get_tile(spawn_hex).spawn_point = sp
    base_state.board.spawn_points.append(sp)

    step = RespawnHeroStep(hero_id="h1")
    res = step.resolve(base_state, {})
    assert res.requires_input

    step.pending_input = {"selection": {"q": -3, "r": 0, "s": 3}}
    res = step.resolve(base_state, {})
    assert res.is_finished
    assert base_state.entity_locations["h1"] == spawn_hex

def test_respawn_minion_step(base_state):
    base_state.active_zone_id = "test_zone"
    zone_hexes = [Hex(q=0, r=0, s=0), Hex(q=1, r=0, s=-1), Hex(q=2, r=0, s=-2)]
    base_state.board.zones["test_zone"] = Zone(id="test_zone", name="Test", hexes=zone_hexes)
    
    for h in zone_hexes:
        base_state.board.get_tile(h).zone_id = "test_zone"
        
    spawn_hex = Hex(q=2, r=0, s=-2)
    base_state.board.get_tile(spawn_hex).spawn_point = SpawnPoint(
        location=spawn_hex, team=TeamColor.RED, type=SpawnType.MINION, minion_type=MinionType.MELEE
    )
    
    step = RespawnMinionStep(team=TeamColor.RED, minion_type=MinionType.MELEE)
    res = step.resolve(base_state, {})
    assert res.requires_input
    
    step.pending_input = {"selection": {"q": 2, "r": 0, "s": -2}}
    res = step.resolve(base_state, {})
    assert res.is_finished
    assert base_state.entity_locations["m1"] == spawn_hex
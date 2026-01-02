from goa2.domain.hex import Hex
from goa2.domain.board import Board, Tile
from goa2.engine.map_loader import load_map
from goa2.engine import rules
import json
import os

def test_terrain_outside_zone():
    """Verify that terrain hexes are added to the board even if they don't belong to a zone."""
    # Create a dummy map JSON
    map_data = {
        "zone_definitions": [
            {"id": "zone1", "label": "Zone 1"}
        ],
        "hex_map": [
            {"q": 0, "r": 0, "s": 0, "zone_id": "zone1", "tags": []},
            {"q": 1, "r": 0, "s": -1, "tags": ["Terrain"]} # NO zone_id
        ]
    }
    
    file_path = "temp_map.json"
    with open(file_path, "w") as f:
        json.dump(map_data, f)
        
    try:
        board = load_map(file_path)
        
        # Hex (0,0,0) should be in zone1
        h0 = Hex(q=0, r=0, s=0)
        assert board.get_tile(h0).zone_id == "zone1"
        assert board.get_tile(h0).is_terrain is False
        
        # Hex (1,0,-1) should be terrain and have NO zone
        h1 = Hex(q=1, r=0, s=-1)
        tile1 = board.get_tile(h1)
        assert tile1 is not None
        assert tile1.is_terrain is True
        assert tile1.zone_id is None
        
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

def test_missing_hex_is_terrain():
    """Verify that any hex not on the board is treated as terrain."""
    board = Board(tiles={
        Hex(q=0, r=0, s=0): Tile(hex=Hex(q=0, r=0, s=0))
    })
    
    # Existing hex
    h_on = Hex(q=0, r=0, s=0)
    assert board.is_on_map(h_on) is True
    assert board.get_tile(h_on).is_terrain is False
    assert board.get_tile(h_on).is_obstacle is False
    
    # Missing hex
    h_off = Hex(q=1, r=0, s=-1)
    assert board.is_on_map(h_off) is False
    
    tile_off = board.get_tile(h_off)
    assert tile_off is not None
    assert tile_off.is_terrain is True
    assert tile_off.is_obstacle is True
    
def test_movement_blocked_by_void():
    """Verify that movement pathfinding respects the virtual terrain (void)."""
    # Small 1-tile map
    board = Board(tiles={
        Hex(q=0, r=0, s=0): Tile(hex=Hex(q=0, r=0, s=0))
    })
    # NOTE: unit_locations is no longer needed by validate_movement_path directly
    # unit_locations = {"u1": Hex(q=0, r=0, s=0)}
    
    # Try to move to a neighbor (which is off-map)
    neighbor = Hex(q=1, r=0, s=-1)
    # Even if range is 1, it should fail because the neighbor is virtual terrain (obstacle)
    assert rules.validate_movement_path(
        board=board, 
        start=Hex(q=0, r=0, s=0), 
        end=neighbor, 
        max_steps=1
    ) is False

def test_get_neighbors_includes_void():
    """Verify that get_neighbors returns all 6 neighbors now."""
    board = Board(tiles={
        Hex(q=0, r=0, s=0): Tile(hex=Hex(q=0, r=0, s=0))
    })
    h = Hex(q=0, r=0, s=0)
    neighbors = board.get_neighbors(h)
    
    assert len(neighbors) == 6
    for n in neighbors:
        # All neighbors in this case are off-map, so they should be terrain
        assert board.is_on_map(n) is False
        assert board.get_tile(n).is_terrain is True

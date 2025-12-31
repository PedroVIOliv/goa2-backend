import json
from typing import Dict, List, Set, Tuple

from goa2.domain.board import Board, Zone
from goa2.domain.tile import Tile
from goa2.domain.hex import Hex
from goa2.domain.models import TeamColor

def load_map(file_path: str) -> Board:
    """
    Loads a map from a JSON file.
    
    Structure Expected:
    {
        "zone_definitions": [ {"id": "...", "label": "...", "color": "..."} ],
        "hex_map": [ {"q": 1, "r": 2, "s": -3, "zone_id": "...", "tags": []} ]
    }
    """
    with open(file_path, 'r') as f:
        data = json.load(f)
        
    zones: Dict[str, Zone] = {}
    
    # 1. Provide Zones
    for z_def in data.get("zone_definitions", []):
        z_id = z_def["id"]
        label = z_def.get("label")
        zones[z_id] = Zone(id=z_id, label=label, hexes=set())
        
    # 2. Populate Hexes
    # We also track tags if needed later (Obstacles, Spawns)
    # But for now, we just fill the zones.
    found_zone_ids = set()
    
    for h_def in data.get("hex_map", []):
        q = h_def["q"]
        r = h_def["r"]
        s = h_def["s"]
        z_id = h_def.get("zone_id")
        
        h = Hex(q=q, r=r, s=s)
        
        if z_id and z_id in zones:
            zones[z_id].hexes.add(h)
            found_zone_ids.add(z_id)
            
        tags = h_def.get("tags", [])
        for tag in tags:
            # 1. Terrain / Obstacles
            if tag == "Terrain":
                # Add to obstacles (will be added to board later)
                # We need to collect them first or add to a list
                pass # Handled in loop creation? No we need lists.
                
    # We need to accumulate obstacles and spawns
    obstacles: Set[Hex] = set()
    spawn_points: List[SpawnPoint] = []
    
    from goa2.domain.board import SpawnPoint, SpawnType
    from goa2.domain.models import MinionType
    
    for h_def in data.get("hex_map", []):
        q = h_def["q"]
        r = h_def["r"]
        s = h_def["s"]
        z_id = h_def.get("zone_id")
        tags = h_def.get("tags", [])
        
        h = Hex(q=q, r=r, s=s)
        
        # Populate Zones
        if z_id and z_id in zones:
            zones[z_id].hexes.add(h)
            
        # Process Tags
        if "Terrain" in tags:
            obstacles.add(h)
            
        # Spawn Points
        # Format expectation: "{Color}{Type}Spawn" e.g. "RedHeavySpawn", "BlueMeleeSpawn"
        # Or just "Spawn" for Generic? 
        # Checking JSON: "BlueHeavySpawn", "RedHeavySpawn"
        
        for tag in tags:
            if "Spawn" in tag:
                # Naive cleanup: assumes "ColorTypeSpawn"
                # TODO: refine regex or string parsing if names get complex
                lower_tag = tag.lower()
                
                team = None
                if "red" in lower_tag: team = TeamColor.RED
                if "blue" in lower_tag: team = TeamColor.BLUE
                
                spawn_type = SpawnType.MINION # Default
                m_type = None
                
                if "hero" in lower_tag:
                    spawn_type = SpawnType.HERO
                else:
                    # Minion Logic
                    if "heavy" in lower_tag: m_type = MinionType.HEAVY
                    if "melee" in lower_tag: m_type = MinionType.MELEE
                    if "ranged" in lower_tag: m_type = MinionType.RANGED
                
                if team:
                    spawn_points.append(SpawnPoint(
                        location=h, 
                        team=team, 
                        type=spawn_type,
                        minion_type=m_type 
                    ))

    # 3. Create Board
    # We remove 'obstacles' arg as it is no longer in Board model
    board = Board(
        zones=zones,
        # obstacles=obstacles, # REMOVED
        spawn_points=spawn_points
    )
    board.populate_tiles_from_zones()
    
    # 3.1 Apply Obstacles to Tiles
    for h_obs in obstacles:
        if h_obs not in board.tiles:
            # Create a tile for terrain even if it has no zone
            board.tiles[h_obs] = Tile(hex=h_obs, is_terrain=True)
        else:
            board.tiles[h_obs].is_terrain = True
    
    # 3b. Calculate Zone Neighbors (Geometric Adjacency)
    # We iterate all hexes in the board (via Tiles or Zones)
    # For each hex, check neighbors. If neighbor hex is in a different zone, link them.
    
    for h, tile in board.tiles.items():
        current_zone_id = tile.zone_id
        if not current_zone_id: continue
        
        current_zone = zones[current_zone_id]
        
        for neighbor_hex in board.get_neighbors(h):
            neighbor_tile = board.get_tile(neighbor_hex)
            if not neighbor_tile: continue # redundant due to get_neighbors
            
            neighbor_zone_id = neighbor_tile.zone_id
            if neighbor_zone_id and neighbor_zone_id != current_zone_id:
                    # Found a connection
                    if neighbor_zone_id not in current_zone.neighbors:
                        current_zone.neighbors.append(neighbor_zone_id)
                        
                    # Bi-directional consistency (optional, but good)
                    neighbor_zone = zones[neighbor_zone_id]
                    if current_zone_id not in neighbor_zone.neighbors:
                        neighbor_zone.neighbors.append(current_zone_id)
    
    # 4. Infer Lane
    # Heuristic: Look for Zones with specific labels and order them?
    # Or order them by Q coordinate of centroid?
    # Labels: RedBase, RedBeach, Mid, BlueBeach, BlueBase, Zone 1?
    # Standard Lane: RedBase -> ... -> BlueBase
    # Let's find known labels.
    
    ordered_labels = ["RedBase", "RedBeach", "Mid", "BlueBeach", "BlueBase"]
    lane_ids = []
    
    # Map label -> id
    label_to_id = {z.label: z.id for z in zones.values() if z.label}
    
    for label in ordered_labels:
        if label in label_to_id:
            lane_ids.append(label_to_id[label])
            
    if len(lane_ids) >= 3:
        board.lane = lane_ids
        print(f"[MapLoader] Inferred Lane: {ordered_labels}")
    else:
        print(f"[MapLoader] Could not infer minimal lane (RedBase->Mid->BlueBase). Found: {list(label_to_id.keys())}")
        # Fallback: Sort by Q?
        # TODO: Implement robust sorting if labels missing.
        
    return board

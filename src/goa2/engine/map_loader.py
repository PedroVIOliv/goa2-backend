import json
from typing import Dict, List, Set, TYPE_CHECKING

from goa2.domain.board import Board, Zone
from goa2.domain.tile import Tile
from goa2.domain.hex import Hex
from goa2.domain.models import TeamColor

if TYPE_CHECKING:
    pass


def load_map(file_path: str) -> Board:
    """
    Loads a map from a JSON file.

    Structure Expected:
    {
        "zone_definitions": [ {"id": "...", "label": "...", "color": "..."} ],
        "hex_map": [ {"q": 1, "r": 2, "s": -3, "zone_id": "...", "tags": []} ]
    }
    """
    with open(file_path, "r") as f:
        data = json.load(f)

    zones: Dict[str, Zone] = {}

    for z_def in data.get("zone_definitions", []):
        z_id = z_def["id"]
        label = z_def.get("label")
        zones[z_id] = Zone(id=z_id, label=label, hexes=set())

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

    from goa2.domain.models.spawn import SpawnPoint, SpawnType
    from goa2.domain.models.enums import MinionType

    obstacles: Set[Hex] = set()
    spawn_points: List[SpawnPoint] = []

    for h_def in data.get("hex_map", []):
        q = h_def["q"]
        r = h_def["r"]
        s = h_def["s"]
        z_id = h_def.get("zone_id")
        tags = h_def.get("tags", [])

        h = Hex(q=q, r=r, s=s)

        if z_id and z_id in zones:
            zones[z_id].hexes.add(h)

        if "Terrain" in tags:
            obstacles.add(h)

        for tag in tags:
            if "Spawn" in tag:
                lower_tag = tag.lower()

                team = None
                if "red" in lower_tag:
                    team = TeamColor.RED
                if "blue" in lower_tag:
                    team = TeamColor.BLUE

                spawn_type = SpawnType.MINION
                m_type = None

                if "hero" in lower_tag:
                    spawn_type = SpawnType.HERO
                else:
                    if "heavy" in lower_tag:
                        m_type = MinionType.HEAVY
                    if "melee" in lower_tag:
                        m_type = MinionType.MELEE
                    if "ranged" in lower_tag:
                        m_type = MinionType.RANGED

                if team:
                    spawn_points.append(
                        SpawnPoint(
                            location=h, team=team, type=spawn_type, minion_type=m_type
                        )
                    )

    # Distribute spawn points to their respective zones
    for sp in spawn_points:
        for z_id, zone in zones.items():
            if sp.location in zone.hexes:
                zone.spawn_points.append(sp)
                break

    board = Board(zones=zones, spawn_points=spawn_points)
    board.populate_tiles_from_zones()

    for sp in spawn_points:
        if sp.location in board.tiles:
            board.tiles[sp.location].spawn_point = sp

    for h_obs in obstacles:
        if h_obs not in board.tiles:
            board.tiles[h_obs] = Tile(hex=h_obs, is_terrain=True)
        else:
            board.tiles[h_obs].is_terrain = True

    for h, tile in board.tiles.items():
        current_zone_id = tile.zone_id
        if not current_zone_id:
            continue

        current_zone = zones[current_zone_id]

        for neighbor_hex in board.get_neighbors(h):
            neighbor_tile = board.get_tile(neighbor_hex)
            if not neighbor_tile:
                continue

            neighbor_zone_id = neighbor_tile.zone_id
            if neighbor_zone_id and neighbor_zone_id != current_zone_id:
                if neighbor_zone_id not in current_zone.neighbors:
                    current_zone.neighbors.append(neighbor_zone_id)

                neighbor_zone = zones[neighbor_zone_id]
                if current_zone_id not in neighbor_zone.neighbors:
                    neighbor_zone.neighbors.append(current_zone_id)

    # Lane inference
    # Priority: 1. "lane" field in JSON, 2. "ordered_labels" fallback
    lane_labels = data.get("lane")
    if not lane_labels:
        lane_labels = ["RedBase", "RedBeach", "Mid", "BlueBeach", "BlueBase"]

    lane_ids = []
    label_to_id = {z.label: z.id for z in zones.values() if z.label}

    for label in lane_labels:
        if label in label_to_id:
            lane_ids.append(label_to_id[label])
        else:
            print(f"[MapLoader] Warning: Lane label '{label}' not found in zones.")

    if len(lane_ids) >= 3:
        board.lane = lane_ids
        print(f"[MapLoader] Inferred Lane: {lane_labels}")
    else:
        print(
            f"[MapLoader] Could not infer minimal lane (RedBase->Mid->BlueBase). Found: {list(label_to_id.keys())}"
        )

    return board

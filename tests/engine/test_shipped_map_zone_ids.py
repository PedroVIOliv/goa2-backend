"""Checks the shipped map convention that zone ids are their labels."""

import json
from pathlib import Path

import pytest

from goa2.engine.map_loader import load_map

MAP_DIR = Path(__file__).parents[2] / "src" / "goa2" / "data" / "maps"
MAP_PATHS = sorted(MAP_DIR.glob("*.json"))


@pytest.mark.parametrize("map_path", MAP_PATHS, ids=lambda path: path.stem)
def test_shipped_map_zone_ids_match_labels_and_references(map_path: Path) -> None:
    data = json.loads(map_path.read_text())
    zones = data["zone_definitions"]

    assert all(zone["id"] == zone["label"] for zone in zones)
    zone_ids = {zone["id"] for zone in zones}
    assert len(zone_ids) == len(zones)
    assert all(
        hex_def.get("zone_id") is None or hex_def["zone_id"] in zone_ids
        for hex_def in data["hex_map"]
    )

    board = load_map(str(map_path))
    assert set(board.zones) == zone_ids
    assert all(tile.zone_id is None or tile.zone_id in zone_ids for tile in board.tiles.values())

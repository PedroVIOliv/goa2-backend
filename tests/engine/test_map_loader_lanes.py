"""Tests for the multi-lane `"lanes"` key in map JSON."""

import json

import pytest

from goa2.engine.map_loader import load_map


def _zone(zid: str, label: str) -> dict:
    return {"id": zid, "label": label, "color": "#cccccc"}


def _hexes(zid: str, coords: list[tuple[int, int]]) -> list[dict]:
    return [{"q": q, "r": r, "s": -q - r, "zone_id": zid, "tags": []} for q, r in coords]


def _write_map(tmp_path, data: dict) -> str:
    p = tmp_path / "map.json"
    p.write_text(json.dumps(data))
    return str(p)


@pytest.fixture
def two_lane_map(tmp_path) -> str:
    """Two disjoint 3-zone lanes; each zone is a single hex."""
    zones = [
        _zone("z_rb1", "RedBase1"),
        _zone("z_mid1", "Mid1"),
        _zone("z_bb1", "BlueBase1"),
        _zone("z_rb2", "RedBase2"),
        _zone("z_mid2", "Mid2"),
        _zone("z_bb2", "BlueBase2"),
    ]
    hex_map = (
        _hexes("z_rb1", [(0, 0)])
        + _hexes("z_mid1", [(1, 0)])
        + _hexes("z_bb1", [(2, 0)])
        + _hexes("z_rb2", [(0, 5)])
        + _hexes("z_mid2", [(1, 5)])
        + _hexes("z_bb2", [(2, 5)])
    )
    data = {
        "zone_definitions": zones,
        "hex_map": hex_map,
        "lanes": {
            "lane_1": ["RedBase1", "Mid1", "BlueBase1"],
            "lane_2": ["RedBase2", "Mid2", "BlueBase2"],
        },
    }
    return _write_map(tmp_path, data)


def test_lanes_key_loads_both_lanes_in_order(two_lane_map):
    board = load_map(two_lane_map)
    assert board.lanes == {
        "lane_1": ["z_rb1", "z_mid1", "z_bb1"],
        "lane_2": ["z_rb2", "z_mid2", "z_bb2"],
    }


def test_legacy_single_lane_map_still_loads():
    board = load_map("data/maps/test_map.json")
    assert len(board.lanes) == 1
    assert len(board.lane) >= 3  # legacy accessor works on single-lane boards


def test_lane_with_unknown_label_is_skipped(tmp_path):
    data = {
        "zone_definitions": [
            _zone("z_a", "A"),
            _zone("z_b", "B"),
            _zone("z_c", "C"),
        ],
        "hex_map": _hexes("z_a", [(0, 0)]) + _hexes("z_b", [(1, 0)]) + _hexes("z_c", [(2, 0)]),
        "lanes": {
            "lane_1": ["A", "B", "C"],
            "lane_2": ["A", "Nope", "AlsoNope"],  # resolves to 1 zone -> skipped
        },
    }
    board = load_map(_write_map(tmp_path, data))
    assert board.lanes == {"lane_1": ["z_a", "z_b", "z_c"]}

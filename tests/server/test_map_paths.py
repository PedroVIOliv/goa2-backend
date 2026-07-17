"""Map identifiers must never escape the server-owned map directory."""

import pytest
from fastapi import HTTPException

from goa2.server.map_paths import MapFileNotFoundError, resolve_map_path
from goa2.server.replay import _resolve_map_path
from goa2.server.routes_draft import _map_path as draft_map_path
from goa2.server.routes_games import _map_path as game_map_path


def test_valid_map_name_resolves():
    assert resolve_map_path("forgotten_island").endswith("/maps/forgotten_island.json")


@pytest.mark.parametrize("map_name", ["../heroes/arien", "/tmp/external-map"])
def test_map_resolvers_reject_paths_outside_map_directory(map_name):
    for route_resolver in (game_map_path, draft_map_path):
        with pytest.raises(HTTPException) as exc_info:
            route_resolver(map_name)
        assert exc_info.value.status_code == 404

    with pytest.raises(MapFileNotFoundError):
        _resolve_map_path(map_name)

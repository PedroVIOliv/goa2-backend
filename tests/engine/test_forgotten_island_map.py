"""
Tests for loading the Forgotten Island map.
Verifies zone adjacencies and spawn point configurations.
"""
import pytest
import os
from goa2.engine.map_loader import load_map
from goa2.domain.models import TeamColor, MinionType
from goa2.domain.models.spawn import SpawnType

# Path to the forgotten_island.json map file
MAP_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "src", "goa2", "data", "maps", "forgotten_island.json"
)


@pytest.fixture
def board():
    """Load the forgotten island map."""
    return load_map(MAP_PATH)


@pytest.fixture
def zones_by_label(board):
    """Return a dict mapping zone labels to zone objects."""
    return {z.label: z for z in board.zones.values() if z.label}


class TestZoneAdjacencies:
    """Tests for verifying zone adjacency relationships."""
    
    def test_red_jungle_neighbors_red_base_only(self, zones_by_label):
        """RedJungle should only be adjacent to RedBase and Mid."""
        red_jungle = zones_by_label["RedJungle"]
        red_base = zones_by_label["RedBase"]
        mid = zones_by_label["Mid"]
        
        neighbor_labels = {zones_by_label[label].label for zone_id in red_jungle.neighbors 
                          for label, z in zones_by_label.items() if z.id == zone_id}
        
        # Get actual neighbor zone objects to compare
        neighbor_zone_ids = set(red_jungle.neighbors)
        expected_neighbors = {red_base.id, mid.id}
        
        assert neighbor_zone_ids == expected_neighbors, (
            f"RedJungle should be adjacent to RedBase and Mid only, "
            f"but is adjacent to zones: {neighbor_zone_ids}"
        )
    
    def test_blue_jungle_neighbors_blue_base_and_mid(self, zones_by_label):
        """BlueJungle should only be adjacent to BlueBase and Mid."""
        blue_jungle = zones_by_label["BlueJungle"]
        blue_base = zones_by_label["BlueBase"]
        mid = zones_by_label["Mid"]
        
        neighbor_zone_ids = set(blue_jungle.neighbors)
        expected_neighbors = {blue_base.id, mid.id}
        
        assert neighbor_zone_ids == expected_neighbors, (
            f"BlueJungle should be adjacent to BlueBase and Mid only, "
            f"but is adjacent to zones: {neighbor_zone_ids}"
        )
    
    def test_red_beach_neighbors_red_base_and_mid(self, zones_by_label):
        """RedBeach should be adjacent to RedBase and Mid."""
        red_beach = zones_by_label["RedBeach"]
        red_base = zones_by_label["RedBase"]
        mid = zones_by_label["Mid"]
        
        neighbor_zone_ids = set(red_beach.neighbors)
        expected_neighbors = {red_base.id, mid.id}
        
        assert neighbor_zone_ids == expected_neighbors, (
            f"RedBeach should be adjacent to RedBase and Mid only, "
            f"but is adjacent to zones: {neighbor_zone_ids}"
        )
    
    def test_blue_beach_neighbors_blue_base_and_mid(self, zones_by_label):
        """BlueBeach should be adjacent to BlueBase and Mid."""
        blue_beach = zones_by_label["BlueBeach"]
        blue_base = zones_by_label["BlueBase"]
        mid = zones_by_label["Mid"]
        
        neighbor_zone_ids = set(blue_beach.neighbors)
        expected_neighbors = {blue_base.id, mid.id}
        
        assert neighbor_zone_ids == expected_neighbors, (
            f"BlueBeach should be adjacent to BlueBase and Mid only, "
            f"but is adjacent to zones: {neighbor_zone_ids}"
        )
    
    def test_mid_has_four_neighbors(self, zones_by_label):
        """Mid should be adjacent to both beaches and both jungles."""
        mid = zones_by_label["Mid"]
        red_beach = zones_by_label["RedBeach"]
        blue_beach = zones_by_label["BlueBeach"]
        red_jungle = zones_by_label["RedJungle"]
        blue_jungle = zones_by_label["BlueJungle"]
        
        neighbor_zone_ids = set(mid.neighbors)
        expected_neighbors = {red_beach.id, blue_beach.id, red_jungle.id, blue_jungle.id}
        
        assert neighbor_zone_ids == expected_neighbors, (
            f"Mid should be adjacent to RedBeach, BlueBeach, RedJungle, BlueJungle, "
            f"but is adjacent to zones: {neighbor_zone_ids}"
        )
    
    def test_red_base_has_correct_neighbors(self, zones_by_label):
        """RedBase should be adjacent to RedBeach and RedJungle only."""
        red_base = zones_by_label["RedBase"]
        red_beach = zones_by_label["RedBeach"]
        red_jungle = zones_by_label["RedJungle"]
        
        neighbor_zone_ids = set(red_base.neighbors)
        expected_neighbors = {red_beach.id, red_jungle.id}
        
        assert neighbor_zone_ids == expected_neighbors, (
            f"RedBase should be adjacent to RedBeach and RedJungle only, "
            f"but is adjacent to zones: {neighbor_zone_ids}"
        )
    
    def test_blue_base_has_correct_neighbors(self, zones_by_label):
        """BlueBase should be adjacent to BlueBeach and BlueJungle only."""
        blue_base = zones_by_label["BlueBase"]
        blue_beach = zones_by_label["BlueBeach"]
        blue_jungle = zones_by_label["BlueJungle"]
        
        neighbor_zone_ids = set(blue_base.neighbors)
        expected_neighbors = {blue_beach.id, blue_jungle.id}
        
        assert neighbor_zone_ids == expected_neighbors, (
            f"BlueBase should be adjacent to BlueBeach and BlueJungle only, "
            f"but is adjacent to zones: {neighbor_zone_ids}"
        )
    
    def test_no_direct_base_to_mid_connection(self, zones_by_label):
        """Bases should NOT be directly adjacent to Mid."""
        mid = zones_by_label["Mid"]
        red_base = zones_by_label["RedBase"]
        blue_base = zones_by_label["BlueBase"]
        
        assert red_base.id not in mid.neighbors, "RedBase should NOT be directly adjacent to Mid"
        assert blue_base.id not in mid.neighbors, "BlueBase should NOT be directly adjacent to Mid"


class TestSpawnPoints:
    """Tests for verifying spawn point configurations."""
    
    def test_total_spawn_points_equal_per_team(self, board):
        """Total spawn points should be equal for both teams."""
        red_spawns = [sp for sp in board.spawn_points if sp.team == TeamColor.RED]
        blue_spawns = [sp for sp in board.spawn_points if sp.team == TeamColor.BLUE]
        
        assert len(red_spawns) == len(blue_spawns), (
            f"Teams should have equal spawn points: Red has {len(red_spawns)}, Blue has {len(blue_spawns)}"
        )
    
    def test_red_beach_has_correct_spawn_count(self, board, zones_by_label):
        """RedBeach should have 5 spawn points for one team, 6 for the other."""
        red_beach = zones_by_label["RedBeach"]
        beach_spawns = [sp for sp in board.spawn_points if sp.location in red_beach.hexes]
        
        red_spawns = [sp for sp in beach_spawns if sp.team == TeamColor.RED]
        blue_spawns = [sp for sp in beach_spawns if sp.team == TeamColor.BLUE]
        
        spawn_counts = sorted([len(red_spawns), len(blue_spawns)])
        assert spawn_counts == [5, 6], (
            f"RedBeach should have 5 spawns for one team and 6 for the other, "
            f"but has Red: {len(red_spawns)}, Blue: {len(blue_spawns)}"
        )
    
    def test_blue_beach_has_correct_spawn_count(self, board, zones_by_label):
        """BlueBeach should have 5 spawn points for one team, 6 for the other."""
        blue_beach = zones_by_label["BlueBeach"]
        beach_spawns = [sp for sp in board.spawn_points if sp.location in blue_beach.hexes]
        
        red_spawns = [sp for sp in beach_spawns if sp.team == TeamColor.RED]
        blue_spawns = [sp for sp in beach_spawns if sp.team == TeamColor.BLUE]
        
        spawn_counts = sorted([len(red_spawns), len(blue_spawns)])
        assert spawn_counts == [5, 6], (
            f"BlueBeach should have 5 spawns for one team and 6 for the other, "
            f"but has Red: {len(red_spawns)}, Blue: {len(blue_spawns)}"
        )
    
    def test_mid_has_six_spawns_per_team(self, board, zones_by_label):
        """Mid should have 6 spawn points for each team."""
        mid = zones_by_label["Mid"]
        mid_spawns = [sp for sp in board.spawn_points if sp.location in mid.hexes]
        
        red_spawns = [sp for sp in mid_spawns if sp.team == TeamColor.RED]
        blue_spawns = [sp for sp in mid_spawns if sp.team == TeamColor.BLUE]
        
        assert len(red_spawns) == 6, f"Mid should have 6 Red spawns, but has {len(red_spawns)}"
        assert len(blue_spawns) == 6, f"Mid should have 6 Blue spawns, but has {len(blue_spawns)}"
    
    def test_red_base_has_three_hero_spawns(self, board, zones_by_label):
        """RedBase should have exactly 3 hero spawn points."""
        red_base = zones_by_label["RedBase"]
        base_spawns = [sp for sp in board.spawn_points if sp.location in red_base.hexes]
        
        hero_spawns = [sp for sp in base_spawns if sp.type == SpawnType.HERO]
        red_hero_spawns = [sp for sp in hero_spawns if sp.team == TeamColor.RED]
        
        assert len(red_hero_spawns) == 3, (
            f"RedBase should have 3 Red hero spawn points, but has {len(red_hero_spawns)}"
        )
    
    def test_blue_base_has_three_hero_spawns(self, board, zones_by_label):
        """BlueBase should have exactly 3 hero spawn points."""
        blue_base = zones_by_label["BlueBase"]
        base_spawns = [sp for sp in board.spawn_points if sp.location in blue_base.hexes]
        
        hero_spawns = [sp for sp in base_spawns if sp.type == SpawnType.HERO]
        blue_hero_spawns = [sp for sp in hero_spawns if sp.team == TeamColor.BLUE]
        
        assert len(blue_hero_spawns) == 3, (
            f"BlueBase should have 3 Blue hero spawn points, but has {len(blue_hero_spawns)}"
        )
    
    def test_jungles_have_no_spawn_points(self, board, zones_by_label):
        """Jungles should not have any spawn points."""
        red_jungle = zones_by_label["RedJungle"]
        blue_jungle = zones_by_label["BlueJungle"]
        
        red_jungle_spawns = [sp for sp in board.spawn_points if sp.location in red_jungle.hexes]
        blue_jungle_spawns = [sp for sp in board.spawn_points if sp.location in blue_jungle.hexes]
        
        assert len(red_jungle_spawns) == 0, f"RedJungle should have no spawn points, but has {len(red_jungle_spawns)}"
        assert len(blue_jungle_spawns) == 0, f"BlueJungle should have no spawn points, but has {len(blue_jungle_spawns)}"

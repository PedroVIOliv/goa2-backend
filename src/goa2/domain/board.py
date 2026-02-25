from __future__ import annotations
from typing import Set, Dict, Optional, List, Any
from pydantic import BaseModel, Field

from goa2.domain.hex import Hex
from goa2.domain.models.spawn import SpawnPoint
from goa2.domain.tile import Tile


class Zone(BaseModel):
    """
    A named collection of Hexes representing a distinct area of the board.
    e.g. "Zone 1", "Throne Room".
    """

    id: str
    label: Optional[str] = None
    hexes: Set[Hex]
    neighbors: List[str] = Field(default_factory=list)  # IDs of connected zones

    # Spawn Points contained in this zone
    spawn_points: List[SpawnPoint] = Field(default_factory=list)

    def contains(self, h: Hex) -> bool:
        return h in self.hexes


class Board(BaseModel):
    """
    The static map container.
    """

    zones: Dict[str, Zone] = Field(default_factory=dict)

    spawn_points: List[SpawnPoint] = Field(default_factory=list)

    tiles: Dict[Hex, Tile] = Field(default_factory=dict)

    # E.g. [RedBase, Zone1, Mid, Zone2, BlueBase]
    lane: List[str] = Field(default_factory=list)

    # Private optimized lookup for O(1) zone resolution
    # Populated by validation
    _hex_lookup: Dict[Hex, str] = {}

    def model_post_init(self, __context: Any) -> None:
        """
        Populate the hex lookup table after initialization.
        """
        # Using model_post_init instead of validator to avoid ser/de issues with private fields.
        self._rebuild_lookup()

    def _rebuild_lookup(self):
        self._hex_lookup = {}
        for z_id, zone in self.zones.items():
            for h in zone.hexes:
                self._hex_lookup[h] = z_id

    def get_zone_for_hex(self, h: Hex) -> Optional[str]:
        # Optimization: Check Tile first
        if h in self.tiles:
            return self.tiles[h].zone_id

        # Fallback to O(N) search if tiles not built (Legacy/Setup)
        for z in self.zones.values():
            if z.contains(h):
                return z.id
        return None

    def get_spawn_point(self, h: Hex) -> Optional[SpawnPoint]:
        for sp in self.spawn_points:
            if sp.location == h:
                return sp
        return None

    def populate_tiles_from_zones(self):
        """Helper to build Tile grid from Zones."""
        for z in self.zones.values():
            for h in z.hexes:
                self.tiles[h] = Tile(hex=h, zone_id=z.id)

    # --- Smart Grid Methods (O(1) Boundary Checks) ---

    def get_tile(self, h: Hex) -> Tile:
        """Retrieves a tile. Returns a virtual terrain tile if off-map."""
        if h in self.tiles:
            return self.tiles[h]
        return Tile(hex=h, is_terrain=True)

    def is_on_map(self, h: Hex) -> bool:
        """O(1) check if a hex coordinate exists on the board."""
        return h in self.tiles

    def get_neighbors(self, h: Hex) -> List[Hex]:
        """Returns all adjacent hexes (off-map hexes are treated as terrain)."""
        return h.neighbors()

    def get_ring(self, h: Hex, radius: int) -> List[Hex]:
        """Returns all hexes in a ring (off-map hexes are treated as terrain)."""
        return h.ring(radius)

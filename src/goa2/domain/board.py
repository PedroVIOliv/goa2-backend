from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from goa2.domain.hex import Hex
from goa2.domain.models.spawn import SpawnPoint
from goa2.domain.tile import Tile

# Lane id used for single-lane maps and as the default binding for minions.
# Double-lane maps will declare their own ids (e.g. "lane_1"/"lane_2").
DEFAULT_LANE_ID = "lane_1"


class Zone(BaseModel):
    """
    A named collection of Hexes representing a distinct area of the board.
    e.g. "Zone 1", "Throne Room".
    """

    id: str
    label: str | None = None
    hexes: set[Hex]
    neighbors: list[str] = Field(default_factory=list)  # IDs of connected zones

    # Spawn Points contained in this zone
    spawn_points: list[SpawnPoint] = Field(default_factory=list)

    def contains(self, h: Hex) -> bool:
        return h in self.hexes


class Board(BaseModel):
    """
    The static map container.
    """

    zones: dict[str, Zone] = Field(default_factory=dict)

    spawn_points: list[SpawnPoint] = Field(default_factory=list)

    tiles: dict[Hex, Tile] = Field(default_factory=dict)

    # Ordered zone sequences from Red Throne to Blue Throne, keyed by lane id.
    # Single-lane maps have one entry (DEFAULT_LANE_ID);
    # double-lane maps will have two. E.g. {"lane_1": [RedBase, Zone1, Mid, Zone2, BlueBase]}
    lanes: dict[str, list[str]] = Field(default_factory=dict)

    # Optional per-lane starting Battle Zone (zone id), keyed by lane id.
    # Set from the map's "battle_zones" key; lanes without an entry start at
    # the lane's center zone. Lets even-length (e.g. 6-zone) lanes express
    # which side the initial advantage goes to.
    starting_battle_zones: dict[str, str] = Field(default_factory=dict)

    # Private optimized lookup for O(1) zone resolution
    # Populated by validation
    _hex_lookup: dict[Hex, str] = {}

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_lane(cls, data: Any) -> Any:
        """Accept the legacy single-lane shape (`lane: [...]`) from old saves
        and map JSON, converting it to `lanes: {DEFAULT_LANE_ID: [...]}`."""
        if isinstance(data, dict):
            legacy = data.pop("lane", None)
            if legacy and not data.get("lanes"):
                data["lanes"] = {DEFAULT_LANE_ID: legacy}
        return data

    @property
    def lane(self) -> list[str]:
        """Legacy single-lane accessor. Raises on multi-lane boards so a missed
        call site fails loudly instead of silently picking one lane."""
        if len(self.lanes) > 1:
            raise RuntimeError(
                "Board.lane is single-lane only; this board has multiple lanes. "
                "Use Board.lanes / lane-aware helpers instead."
            )
        return next(iter(self.lanes.values()), [])

    @lane.setter
    def lane(self, value: list[str]) -> None:
        self.lanes = {DEFAULT_LANE_ID: list(value)} if value else {}

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

    def lane_of_zone(self, zone_id: str) -> str | None:
        """Returns the id of the lane whose zone sequence contains zone_id."""
        for lane_id, zone_ids in self.lanes.items():
            if zone_id in zone_ids:
                return lane_id
        return None

    def get_zone_for_hex(self, h: Hex) -> str | None:
        # Optimization: Check Tile first
        if h in self.tiles:
            return self.tiles[h].zone_id

        # Fallback to O(N) search if tiles not built (Legacy/Setup)
        for z in self.zones.values():
            if z.contains(h):
                return z.id
        return None

    def get_spawn_point(self, h: Hex) -> SpawnPoint | None:
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

    def get_neighbors(self, h: Hex) -> list[Hex]:
        """Returns all adjacent hexes (off-map hexes are treated as terrain)."""
        return h.neighbors()

    def get_ring(self, h: Hex, radius: int) -> list[Hex]:
        """Returns all hexes in a ring (off-map hexes are treated as terrain)."""
        return h.ring(radius)

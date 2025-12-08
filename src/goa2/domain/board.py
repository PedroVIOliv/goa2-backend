from __future__ import annotations
from enum import Enum
from typing import Set, Dict, Optional, List, Union, Any
from pydantic import BaseModel, Field, model_validator

from goa2.domain.hex import Hex
from goa2.domain.models import TeamColor, MinionType
from goa2.domain.tile import Tile

class Zone(BaseModel):
    """
    A named collection of Hexes representing a distinct area of the board.
    e.g. "Zone 1", "Throne Room".
    """
    id: str
    label: Optional[str] = None
    hexes: Set[Hex]
    neighbors: List[str] = Field(default_factory=list) # IDs of connected zones

    def contains(self, h: Hex) -> bool:
        return h in self.hexes


class SpawnType(str, Enum):
    HERO = "HERO"
    MINION = "MINION"


class SpawnPoint(BaseModel):
    """
    A specific location reserved for spawning units.
    """
    location: Hex
    team: TeamColor
    
    # If not None, this spawn point is RESERVED for this minion type.
    # If None, it is generally considered a Hero spawn point (or undefined, but usually Hero).
    # The user requested: "spawn points should be specified in minion as one of the 3 minion types"
    type: SpawnType = SpawnType.MINION # Default to Minion if not specified? Or Hero? Let's generic.
    # Actually user wants "change spawn typing to include hero spawn type". 
    # Current model relies on minion_type being None.
    # Explicit type is better.
    
    # New Model:
    type: SpawnType
    minion_type: Optional[MinionType] = None 
    
    @model_validator(mode='after')
    def validate_spawn_type(self) -> SpawnPoint:
        if self.type == SpawnType.MINION and self.minion_type is None:
             raise ValueError("Minion spawn point must specify minion_type")
        if self.type == SpawnType.HERO and self.minion_type is not None:
             raise ValueError("Hero spawn point cannot specify minion_type")
        return self

    @property
    def is_minion_spawn(self) -> bool:
        return self.type == SpawnType.MINION

    @property
    def is_hero_spawn(self) -> bool:
        return self.type == SpawnType.HERO 


class Board(BaseModel):
    """
    The static map container.
    """
    # All valid traversable or occupy-able hexes are implicitly defined 
    # by inclusion in a Zone or simply by the coordinate system, 
    # but usually we want a master list of "The Map".
    
    zones: Dict[str, Zone] = Field(default_factory=dict)
    
    # Spawn points definitions
    spawn_points: List[SpawnPoint] = Field(default_factory=list)

    # Tile Grid (New Source of Truth for Topology)
    tiles: Dict[Hex, Tile] = Field(default_factory=dict)
    
    # Lane Definition (Ordered Sequence of Zone IDs for Push Logic)
    # E.g. [RedBase, Zone1, Mid, Zone2, BlueBase]
    lane: List[str] = Field(default_factory=list)

    # Private optimized lookup for O(1) zone resolution
    # Populated by validation
    _hex_lookup: Dict[Hex, str] = {}

    def model_post_init(self, __context: Any) -> None:
        """
        Populate the hex lookup table after initialization.
        Using model_post_init instead of validator to avoid ser/de issues with private fields.
        """
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

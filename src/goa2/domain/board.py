from __future__ import annotations
from enum import Enum
from typing import Set, Dict, Optional, List, Union
from pydantic import BaseModel, Field

from goa2.domain.hex import Hex
from goa2.domain.models import TeamColor, MinionType

class Zone(BaseModel):
    """
    A named collection of Hexes representing a distinct area of the board.
    e.g. "Zone 1", "Throne Room".
    """
    id: str
    hexes: Set[Hex]

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
    minion_type: Optional[MinionType] = None 
    
    @property
    def is_minion_spawn(self) -> bool:
        return self.minion_type is not None

    @property
    def is_hero_spawn(self) -> bool:
        return self.minion_type is None 


class Board(BaseModel):
    """
    The static map container.
    """
    # All valid traversable or occupy-able hexes are implicitly defined 
    # by inclusion in a Zone or simply by the coordinate system, 
    # but usually we want a master list of "The Map".
    
    zones: Dict[str, Zone] = Field(default_factory=dict)
    
    # Static obstacles (Walls, Water, etc.) that permanently block movement
    obstacles: Set[Hex] = Field(default_factory=set)
    
    # Spawn points definitions
    spawn_points: List[SpawnPoint] = Field(default_factory=list)

    def is_obstacle(self, h: Hex) -> bool:
        return h in self.obstacles

    def get_zone_for_hex(self, h: Hex) -> Optional[str]:
        """Finds which zone ID a hex belongs to."""
        for z_id, zone in self.zones.items():
            if h in zone.hexes:
                return z_id
        return None
    
    def get_spawn_point(self, h: Hex) -> Optional[SpawnPoint]:
        for sp in self.spawn_points:
            if sp.location == h:
                return sp
        return None

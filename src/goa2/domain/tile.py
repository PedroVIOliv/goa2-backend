from typing import Optional
from pydantic import BaseModel, Field
from goa2.domain.hex import Hex
from goa2.domain.types import BoardEntityID

# Forward ref to avoid circular import if needed, but GameEntity is in models.base
# We need to import GameEntity to inherit from it.
# BUT models.base imports tile? No, I reverted that in previous step.
# Wait, models.base was importing tile.BoardEntity. 
# Now I want BoardEntity to inherit from GameEntity.
# So tile.py imports models.base.
from goa2.domain.models.spawn import SpawnPoint
from goa2.domain.models.base import GameEntity

class Tile(BaseModel):
    """
    A specific location on the board.
    Aggregates Coordinate, Zone info, and Occupant.
    """
    hex: Hex
    zone_id: Optional[str] = None # Which zone this tile belongs to
    
    # Spawn Point Info (if any)
    spawn_point: Optional[SpawnPoint] = None

    # Runtime State
    # We store the ID of the entity here.
    # Why ID? Because storing the object makes serialization harder (circular refs)
    # and we have Entity Repositories (State.teams, State.minions) to look up the object.
    occupant_id: Optional[BoardEntityID] = None 
    
    # Static Terrain (Walls, Holes, etc.)
    is_terrain: bool = False

    @property
    def is_obstacle(self) -> bool:
        """
        Returns true if this tile is blocked by EITHER:
        1. Static Terrain (Wall/Water)
        2. Dynamic Occupant (Unit/Obstacle Token)
        """
        return self.is_terrain or self.is_occupied
    
    @property
    def is_occupied(self) -> bool:
        return self.occupant_id is not None

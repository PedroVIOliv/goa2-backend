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
pass

from goa2.domain.models.base import GameEntity

class BoardEntity(GameEntity):
    """
    Superset for anything that can occupy a Tile.
    Examples: Unit (Hero, Minion), Token (Objective, Trap).
    This allows us to treat Units and Tokens uniformly for occupancy.
    """
    id: BoardEntityID
    pass

class Tile(BaseModel):
    """
    A specific location on the board.
    Aggregates Coordinate, Zone info, and Occupant.
    """
    hex: Hex
    zone_id: Optional[str] = None # Which zone this tile belongs to
    
    # Runtime State
    # We store the ID of the entity here.
    # Why ID? Because storing the object makes serialization harder (circular refs)
    # and we have Entity Repositories (State.teams, State.minions) to look up the object.
    occupant_id: Optional[BoardEntityID] = None 
    
    @property
    def is_occupied(self) -> bool:
        return self.occupant_id is not None

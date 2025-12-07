from __future__ import annotations
from pydantic import BaseModel
from goa2.domain.types import BoardEntityID

class GameEntity(BaseModel):
    """Base class for anything that has a distinct identity in the game."""
    id: str
    name: str

class BoardEntity(GameEntity):
    """
    Superset for anything that can occupy a Tile.
    Examples: Unit (Hero, Minion), Token (Objective, Trap).
    This allows us to treat Units and Tokens uniformly for occupancy.
    """
    id: BoardEntityID
    pass
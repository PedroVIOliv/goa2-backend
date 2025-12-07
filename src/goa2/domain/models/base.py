from __future__ import annotations
from pydantic import BaseModel

class GameEntity(BaseModel):
    """Base class for anything that has a distinct identity in the game."""
    id: str
    name: str

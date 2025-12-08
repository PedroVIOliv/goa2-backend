from __future__ import annotations
from typing import Optional
from goa2.domain.models.base import GameEntity
from goa2.domain.types import HeroID

class Marker(GameEntity):
    """
    Status effect attached to a Unit.
    Inherits `id` and `name` from GameEntity.
    Does NOT inherit from BoardEntity because Markers do not occupy board space.
    """
    owner_id: Optional[HeroID] = None
    pass

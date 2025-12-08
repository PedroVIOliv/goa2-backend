from __future__ import annotations
from goa2.domain.models.base import GameEntity

class Marker(GameEntity):
    """
    Status effect attached to a Unit.
    Inherits `id` and `name` from GameEntity.
    Does NOT inherit from BoardEntity because Markers do not occupy board space.
    """
    pass

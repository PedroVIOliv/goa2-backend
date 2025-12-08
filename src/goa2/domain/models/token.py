from __future__ import annotations
from pydantic import Field
from goa2.domain.models.base import BoardEntity

class Token(BoardEntity):
    """
    A BoardEntity that represents an object on the board that is NOT a Unit.
    Inherits `id` and `name` from GameEntity/BoardEntity.
    """
    # Tokens are obstacles by default (as per rules: "Tokens are Obstacles")
    # This logic is handled by the fact that if a Tile has an occupant_id, it is occupied.
    pass

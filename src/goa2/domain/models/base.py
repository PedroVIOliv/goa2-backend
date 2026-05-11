from __future__ import annotations

from typing import Literal

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


class Placeholder(BoardEntity):
    """Placeholder to keep AnyMiscEntity a valid Union. Replace with Turret/Dragon."""

    entity_kind: Literal["placeholder"] = "placeholder"


class Turret(BoardEntity):
    """Trinkets' unique Turret board entity.

    The Turret is an obstacle, but it is not a Unit and not a Token.
    """

    entity_kind: Literal["turret"] = "turret"
    owner_id: str | None = None
    is_obstacle: bool = True

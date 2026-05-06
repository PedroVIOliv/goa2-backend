from pydantic import BaseModel

from goa2.domain.hex import Hex
from goa2.domain.models.spawn import SpawnPoint
from goa2.domain.types import BoardEntityID


class Tile(BaseModel):
    """
    A specific location on the board.
    Aggregates Coordinate, Zone info, and Occupant.
    """

    hex: Hex
    zone_id: str | None = None

    spawn_point: SpawnPoint | None = None

    # We store the ID of the entity here.
    # Why ID? Because storing the object makes serialization harder (circular refs)
    # and we have Entity Repositories (State.teams, State.minions) to look up the object.
    occupant_id: BoardEntityID | None = None

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

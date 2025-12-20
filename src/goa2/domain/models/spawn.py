from enum import Enum
from typing import Optional
from pydantic import BaseModel, model_validator
from goa2.domain.hex import Hex
from goa2.domain.models.enums import TeamColor, MinionType

class SpawnType(str, Enum):
    HERO = "HERO"
    MINION = "MINION"

class SpawnPoint(BaseModel):
    """
    A specific location reserved for spawning units.
    """
    location: Hex
    team: TeamColor
    type: SpawnType
    minion_type: Optional[MinionType] = None 
    
    @model_validator(mode='after')
    def validate_spawn_type(self) -> 'SpawnPoint':
        if self.type == SpawnType.MINION and self.minion_type is None:
             raise ValueError("Minion spawn point must specify minion_type")
        if self.type == SpawnType.HERO and self.minion_type is not None:
             raise ValueError("Hero spawn point cannot specify minion_type")
        return self

    @property
    def is_minion_spawn(self) -> bool:
        return self.type == SpawnType.MINION

    @property
    def is_hero_spawn(self) -> bool:
        return self.type == SpawnType.HERO 

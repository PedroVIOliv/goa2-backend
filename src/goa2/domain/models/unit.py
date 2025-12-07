from __future__ import annotations
from typing import List, Optional, TYPE_CHECKING
from pydantic import Field
from .enums import TeamColor, MinionType
from .base import GameEntity
from .card import Card

if TYPE_CHECKING:
    from .team import Team

class Unit(GameEntity):
    """Common base for Heroes and Minions."""
    team: TeamColor

class Hero(Unit):
    """
    Static definition of a Hero character.
    Dynamic state (HP, Level) will be in GameState.
    """
    deck: List[Card]
    level: int = 1
    gold: int = 0
    # Circular reference to parent Team
    team_obj: Optional['Team'] = Field(default=None, exclude=True)

class Minion(Unit):
    """
    A Minion unit.
    """
    type: MinionType
    
    @property
    def value(self) -> int:
        return 4 if self.type == MinionType.HEAVY else 2

    @property
    def is_heavy(self) -> bool:
        return self.type == MinionType.HEAVY

from __future__ import annotations
from typing import List, Optional, TYPE_CHECKING, Dict
from pydantic import Field
from .enums import TeamColor, MinionType, StatType
from .base import GameEntity
from .card import Card

if TYPE_CHECKING:
    from .team import Team

class Unit(GameEntity):
    """Common base for Heroes and Minions."""
    team: TeamColor

class Hero(Unit):
    """
    Represents a specific Hero instance in the game.
    Contains both static identity (ID, Name, Class) AND dynamic state (Level, Gold, Hand).
    This object lives inside GameState.
    """
    deck: List[Card]
    # Card Management
    draw_pile: List[Card] = Field(default_factory=list)
    hand: List[Card] = Field(default_factory=list)
    discard_pile: List[Card] = Field(default_factory=list)
    level: int = 1
    gold: int = 0
    # Items (Passive Stat Bonuses)
    items: Dict[StatType, int] = Field(default_factory=dict)
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

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel
from .enums import TeamColor, MinionType

class GameEntity(BaseModel):
    """Base class for anything that has a distinct identity in the game."""
    id: str
    name: str

class Unit(GameEntity):
    """Common base for Heroes and Minions."""
    team: TeamColor

class Hero(Unit):
    """
    Static definition of a Hero character.
    Dynamic state (HP, Level) will be in GameState.
    """
    # Heroes might have specific static attributes like max_health if it varied,
    # but in GoA2 life is a shared team resource (Life Counters).
    # Individual hero properties (like verify specific class) can go here.
    pass

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

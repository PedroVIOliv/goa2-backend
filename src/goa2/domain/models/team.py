from __future__ import annotations
from typing import List
from pydantic import BaseModel, Field
from .enums import TeamColor
from .unit import Hero, Minion


class Team(BaseModel):
    """
    Represents a team of heroes.
    Holds shared resources like Life Counters.
    """

    color: TeamColor
    # Per rules, life counters are a partially shared resource.
    # We'll initialize with a default (e.g., 5 or 0 depending on game setup,
    # but having the field is the requirement).
    life_counters: int = 5
    heroes: List[Hero] = Field(default_factory=list)
    minions: List[Minion] = Field(default_factory=list)

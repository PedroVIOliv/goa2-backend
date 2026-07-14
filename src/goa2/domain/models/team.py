from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

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
    starting_life_counters: int | None = None
    heroes: list[Hero] = Field(default_factory=list)
    minions: list[Minion] = Field(default_factory=list)

    @model_validator(mode="after")
    def initialize_starting_life_counters(self) -> Team:
        if self.starting_life_counters is None:
            self.starting_life_counters = self.life_counters
        return self

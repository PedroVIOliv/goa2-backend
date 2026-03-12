"""Marker model for singleton tokens placed on heroes."""

from __future__ import annotations
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel

from goa2.domain.models.enums import StatType


class MarkerType(str, Enum):
    """Types of markers in the game. Each type is a singleton."""

    VENOM = "venom"  # Rogue's venom marker: debuffs Attack, Defense, Initiative
    POISON = "poison"  # Tigerclaw's poison marker: debuffs Attack, Defense, Initiative


class MarkerStatEffect(BaseModel):
    """Defines a stat effect that a marker applies."""

    stat_type: StatType
    # If True, uses the marker's value field. If False, uses fixed_value.
    use_marker_value: bool = True
    fixed_value: int = 0  # Used when use_marker_value is False


# Registry of what effects each marker type applies
MARKER_EFFECTS: dict[MarkerType, List[MarkerStatEffect]] = {
    MarkerType.VENOM: [
        MarkerStatEffect(stat_type=StatType.ATTACK, use_marker_value=True),
        MarkerStatEffect(stat_type=StatType.DEFENSE, use_marker_value=True),
        MarkerStatEffect(stat_type=StatType.INITIATIVE, use_marker_value=True),
    ],
    MarkerType.POISON: [
        MarkerStatEffect(stat_type=StatType.ATTACK, use_marker_value=True),
        MarkerStatEffect(stat_type=StatType.DEFENSE, use_marker_value=True),
        MarkerStatEffect(stat_type=StatType.INITIATIVE, use_marker_value=True),
    ],
}


class Marker(BaseModel):
    """
    Represents a singleton marker token that can be placed on heroes.

    Per board game rules:
    - Markers are used as reminders, usually given to other heroes
    - Unlike tokens, markers are not placed on the board
    - Each marker type is a singleton - only one exists
    - When placed on a new hero, it leaves the previous hero
    - All markers return to supply at end of round
    - Markers on defeated heroes are returned

    Attributes:
        type: The marker type (VENOM, etc.)
        target_id: Hero ID if placed, None if in supply
        value: Effect magnitude when placed (e.g., -1 or -2 for stat debuffs)
        source_id: Hero ID who placed this marker (for cleanup on defeat)
    """

    type: MarkerType
    target_id: Optional[str] = None  # Hero ID if placed, None if in supply
    value: int = 0  # Effect magnitude (can be negative for debuffs)
    source_id: Optional[str] = None  # Hero who placed this marker

    @property
    def is_placed(self) -> bool:
        """Check if marker is currently placed on a hero."""
        return self.target_id is not None

    def place(self, target_id: str, value: int, source_id: str) -> None:
        """Place marker on a target hero with given effect value."""
        self.target_id = target_id
        self.value = value
        self.source_id = source_id

    def remove(self) -> None:
        """Return marker to supply."""
        self.target_id = None
        self.value = 0
        self.source_id = None

    def get_stat_effects(self) -> List[tuple[StatType, int]]:
        """
        Get the stat effects this marker applies based on its type and value.

        Returns:
            List of (StatType, value) tuples
        """
        effects = MARKER_EFFECTS.get(self.type, [])
        result = []
        for effect in effects:
            if effect.use_marker_value:
                result.append((effect.stat_type, self.value))
            else:
                result.append((effect.stat_type, effect.fixed_value))
        return result

from __future__ import annotations
from typing import List, Optional, TYPE_CHECKING, Dict
from pydantic import Field
from .enums import TeamColor, MinionType, StatType, CardTier, CardState
from .base import GameEntity, BoardEntity
from .card import Card

if TYPE_CHECKING:
    from .team import Team

class Unit(BoardEntity):
    """Common base for Heroes and Minions."""
    team: Optional[TeamColor] = None

class Hero(Unit):
    """
    Represents a specific Hero instance in the game.
    Contains both static identity (ID, Name, Class) AND dynamic state (Level, Gold, Hand).
    This object lives inside GameState.
    """
    name: str
    title: Optional[str] = None

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

    def initialize_state(self):
        """
        Initializes the dynamic state of the hero for a new game.
        - Populates hand with Untiered and Tier I cards from the deck.
        - Sets up draw/discard piles if necessary.
        """
        self.hand = []
        for c in self.deck:
             if c.tier == CardTier.UNTIERED or c.tier == CardTier.I:
                 c.state = CardState.HAND
                 self.hand.append(c)
             else:
                 c.state = CardState.DECK
        
        # In the future, we might want to separate 'deck' (all cards) from 'active_deck'
        # For now, this satisfies the requirement to initialize the hand.


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

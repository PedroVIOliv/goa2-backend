from __future__ import annotations
from typing import List, Optional, TYPE_CHECKING, Dict
from pydantic import Field
from .enums import TeamColor, MinionType, StatType, CardTier, CardState
from .base import GameEntity, BoardEntity
from .card import Card
from .marker import Marker

if TYPE_CHECKING:
    from .team import Team

class Unit(BoardEntity):
    """Common base for Heroes and Minions."""
    team: Optional[TeamColor] = None
    markers: List[Marker] = Field(default_factory=list)

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
    played_cards: List[Card] = Field(default_factory=list, description="Cards currently on the dashboard (Unresolved or Resolved)")
    current_turn_card: Optional[Card] = Field(default=None, description="The card played for the current turn (Unresolved)")
    
    discard_pile: List[Card] = Field(default_factory=list)
    level: int = 1
    gold: int = 0
    # Items (Passive Stat Bonuses)
    items: Dict[StatType, int] = Field(default_factory=dict)
    # Circular reference to parent Team
    team_obj: Optional['Team'] = Field(default=None, exclude=True)

    def get_effective_initiative(self) -> int:
        """
        Calculates total initiative for the current turn.
        Formula: Card Base + Items[INITIATIVE] + (Future: Modifiers)
        """
        if not self.current_turn_card:
            return 0
        
        val = self.current_turn_card.initiative
        val += self.items.get(StatType.INITIATIVE, 0)
        return val

    def play_card(self, card: Card):
        """
        Moves a card from Hand to 'Played' state (Facedown/Unresolved).
        This marks the card as committed for the turn.
        """
        if card not in self.hand:
            raise ValueError(f"Card {card.id} is not in hand.")
            
        self.hand.remove(card)
        card.state = CardState.UNRESOLVED
        card.is_facedown = True
        card.played_this_round = True

    def discard_card(self, card: Card, from_hand: bool = True):
        """
        Moves a card to the discard pile.
        Default: From Hand (per rules).
        """
        if from_hand:
            if card not in self.hand:
                raise ValueError(f"Cannot discard {card.id} from hand (not found).")
            self.hand.remove(card)
        
        # If discarding a Played card (e.g. from Dashboard), we assume caller removed it from played_cards.
        # But we should handle state update:
        card.state = CardState.DISCARD
        card.is_facedown = False # Open information
        self.discard_pile.append(card)

    def retrieve_cards(self):
        """
        End of Round: Return Resolved and Discarded cards to hand.
        Resets card states and lifecycle flags.
        """
        # Combine lists
        cards_to_return = self.played_cards + self.discard_pile
        
        for card in cards_to_return:
            card.state = CardState.HAND
            card.is_facedown = False
            card.played_this_round = False # Reset lifecycle flag
            self.hand.append(card)
            
        # Clear piles
        self.played_cards = []
        self.discard_pile = []

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

from __future__ import annotations
from typing import List, Optional, TYPE_CHECKING, Dict
from pydantic import Field
from .enums import TeamColor, MinionType, StatType, CardTier, CardState
from .base import BoardEntity
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
    hand: List[Card] = Field(default_factory=list)
    played_cards: List[Card] = Field(
        default_factory=list,
        description="Cards currently on the dashboard (Unresolved or Resolved)",
    )
    current_turn_card: Optional[Card] = Field(
        default=None, description="The card played for the current turn (Unresolved)"
    )

    discard_pile: List[Card] = Field(default_factory=list)
    level: int = 1
    gold: int = 0
    items: Dict[StatType, int] = Field(
        default_factory=dict
    )  # Items (Passive Stat Bonuses)
    team_obj: Optional["Team"] = Field(
        default=None, exclude=True
    )  # Circular reference to parent Team

    def get_effective_initiative(self) -> int:
        """
        Calculates total initiative for the current turn.
        Formula: Card Base + Items[INITIATIVE] + (Future: Modifiers)
        """
        if not self.current_turn_card:
            return 0

        val = self.current_turn_card.current_initiative
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

        # Set as current unresolved card.
        # It moves to 'played_cards' (Resolved slots) only after turn completion.
        self.current_turn_card = card

    def resolve_current_card(self):
        """
        Moves the current turn card to the resolved 'played_cards' list.
        Should be called at the end of the turn.
        """
        if self.current_turn_card:
            self.current_turn_card.state = CardState.RESOLVED
            self.played_cards.append(self.current_turn_card)
            self.current_turn_card = None

    def discard_card(self, card: Card, from_hand: bool = True):
        """
        Moves a card to the discard pile.
        Default: From Hand (per rules).
        """
        if from_hand:
            if card not in self.hand:
                raise ValueError(f"Cannot discard {card.id} from hand (not found).")
            self.hand.remove(card)
        else:
            if self.current_turn_card == card:
                self.current_turn_card = None
            elif card in self.played_cards:
                self.played_cards.remove(card)

        card.state = CardState.DISCARD
        card.is_facedown = False  # Open information
        self.discard_pile.append(card)

    def swap_cards(self, card_a: Card, card_b: Card):
        """
        Swaps two cards between their respective locations (Hand, Resolved Slots, Unresolved Slot, Discard).
        Swaps their State, Facedown status, and lifecycle flags.
        """

        # Helper to get location info: (Type, Container/Field, Index/Key)
        def get_loc(c: Card):
            if c in self.hand:
                return ("list", self.hand, self.hand.index(c))
            if c in self.played_cards:
                return ("list", self.played_cards, self.played_cards.index(c))
            if c in self.discard_pile:
                return ("list", self.discard_pile, self.discard_pile.index(c))
            if c == self.current_turn_card:
                return ("field", "current_turn_card", None)
            return (None, None, None)

        type_a, container_a, idx_a = get_loc(card_a)
        type_b, container_b, idx_b = get_loc(card_b)

        if not type_a:
            raise ValueError(f"Card A {card_a.id} not found.")
        if not type_b:
            raise ValueError(f"Card B {card_b.id} not found.")

        # We execute the swap by putting B in A's spot, and A in B's spot.
        if type_a == "list":
            assert isinstance(container_a, list)
            assert isinstance(idx_a, int)
            container_a[idx_a] = card_b
        else:  # field
            assert isinstance(container_a, str)
            setattr(self, container_a, card_b)

        if type_b == "list":
            assert isinstance(container_b, list)
            assert isinstance(idx_b, int)
            container_b[idx_b] = card_a
        else:  # field
            assert isinstance(container_b, str)
            setattr(self, container_b, card_a)

        card_a.state, card_b.state = card_b.state, card_a.state
        card_a.is_facedown, card_b.is_facedown = card_b.is_facedown, card_a.is_facedown
        card_a.played_this_round, card_b.played_this_round = (
            card_b.played_this_round,
            card_a.played_this_round,
        )

    def retrieve_cards(self):
        """
        End of Round: Return Resolved and Discarded cards to hand.
        Resets card states and lifecycle flags.
        """
        cards_to_return = self.played_cards + self.discard_pile
        if self.current_turn_card:
            cards_to_return.append(self.current_turn_card)

        for card in cards_to_return:
            card.is_facedown = False
            card.played_this_round = False  # Reset lifecycle flag
            self.return_card_to_hand(card)

    def return_card_to_hand(self, card: Card):
        """
        Returns a card to the hand.
        """
        if card in self.hand:
            raise ValueError(f"Card {card.id} is already in hand.")
        card.state = CardState.HAND
        card.is_facedown = False
        self.hand.append(card)
        if card in self.played_cards:
            self.played_cards.remove(card)
        if card in self.discard_pile:
            self.discard_pile.remove(card)
        if card == self.current_turn_card:
            self.current_turn_card = None

    def return_card_to_deck(self, card: Card):
        """
        Returns a card to the deck.
        """
        if card in self.deck:
            raise ValueError(f"Card {card.id} is already in deck.")
        card.state = CardState.DECK
        card.is_facedown = False
        self.deck.append(card)

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

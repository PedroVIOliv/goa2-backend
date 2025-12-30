from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from goa2.engine.steps import GameStep
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card

class CardEffect(ABC):
    """
    Base class for custom card logic.
    Primary actions on cards delegate their execution to these effects.
    """
    @abstractmethod
    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        """
        Returns a list of GameStep objects that implement the card's effect.
        """
        pass

class CardEffectRegistry:
    """
    Global registry for card effects, indexed by effect_id.
    """
    _effects: Dict[str, CardEffect] = {}

    @classmethod
    def register(cls, effect_id: str, effect: CardEffect):
        cls._effects[effect_id] = effect

    @classmethod
    def get(cls, effect_id: str) -> Optional[CardEffect]:
        return cls._effects.get(effect_id)

def register_effect(effect_id: str):
    """Decorator for easy effect registration."""
    def decorator(cls):
        CardEffectRegistry.register(effect_id, cls())
        return cls
    return decorator

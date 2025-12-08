from __future__ import annotations
from typing import Optional, Dict, List, Type, Any, Callable
from dataclasses import dataclass

from goa2.domain.state import GameState
from goa2.domain.models import Card, Unit, StatType
from goa2.engine.command import Command

@dataclass
class EffectContext:
    """
    Context passed to effect hooks.
    Contains the state of the world and details about the current action.
    """
    state: GameState
    # The command triggering the action (if applicable)
    command: Optional[Command] = None
    # The actor performing the action (Hero or Minion)
    actor: Optional[Unit] = None
    # The target of the action (if applicable)
    target: Optional[Unit] = None
    # The card being played (if applicable)
    card: Optional[Card] = None
    # Arbitrary data storage for the effect lifecycle
    data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.data is None:
            self.data = {}

class Effect:
    """
    Base class for Card Script effects.
    """
    @property
    def id(self) -> str:
        raise NotImplementedError

    def on_pre_action(self, ctx: EffectContext) -> None:
        """
        Hook called logically BEFORE the primary action is executed.
        Can modify state, validate conditions, or trigger side effects.
        """
        pass

    def on_post_action(self, ctx: EffectContext) -> None:
        """
        Hook called logically AFTER the primary action is executed.
        """
        pass

    def modify_stat(self, stat_type: StatType, value: int, ctx: EffectContext) -> int:
        """
        Hook to modify a stat calculation.
        """
        return value

    def modify_validation(self, validation_type: str, ctx: EffectContext) -> bool:
        """
        Hook to override validation logic.
        Return True to ALLOW, False to DENY.
        """
        return True

    def modify_defense_components(self, components: Dict[str, int], ctx: EffectContext) -> None:
        """
        Hook to modify defense calculation components in-place.
        Components: 'base', 'items', 'auras', etc.
        """
        pass

class EffectRegistry:
    _effects: Dict[str, Effect] = {}

    @classmethod
    def register(cls, effect_cls: Type[Effect]):
        """
        Decorator to register an effect class.
        """
        instance = effect_cls()
        cls._effects[instance.id] = instance
        return effect_cls

    @classmethod
    def register_instance(cls, instance: Effect):
        cls._effects[instance.id] = instance

    @classmethod
    def get(cls, effect_id: str) -> Optional[Effect]:
        return cls._effects.get(effect_id)

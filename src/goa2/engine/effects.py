from __future__ import annotations
from abc import ABC
from typing import List, Dict, Any, TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from goa2.engine.steps import GameStep
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card


class CardEffect(ABC):
    """
    Base class for custom card logic.
    Primary actions on cards delegate their execution to these effects.

    Methods:
        get_steps: Steps for primary action on your turn (ATTACK/SKILL/MOVEMENT).
        get_defense_steps: Steps when used as primary DEFENSE in reaction.
        get_on_block_steps: Steps after successful block ('if you do' effects).
    """

    def get_steps(self, state: GameState, hero: Hero, card: Card) -> List[GameStep]:
        """
        Returns steps for the card's primary action on your turn.

        For most cards: implements the primary ATTACK/SKILL/MOVEMENT effect.
        For DEFENSE_SKILL cards: also used when defending (same logic applies).

        Default: empty list (for pure DEFENSE-only cards like Wasp's projectile blockers).
        """
        return []

    def get_defense_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        context: Dict[str, Any],
    ) -> Optional[List[GameStep]]:
        """
        Returns steps when used as primary DEFENSE in reaction.

        Args:
            state: Current game state.
            defender: The hero defending (being attacked).
            card: The defense card being played.
            context: Contains attack information:
                - attack_is_ranged: bool - True if the attack is ranged
                - attacker_id: str - ID of the attacking unit
                - defender_id: str - ID of the defending hero (same as defender.id)

        Returns:
            List of steps to execute, or None to fall back to get_steps().

        Note:
            Return None for DEFENSE_SKILL cards where the same effect applies
            in both offense and defense contexts. The engine will use get_steps().
        """
        return None

    def get_on_block_steps(
        self,
        state: GameState,
        defender: Hero,
        card: Card,
        context: Dict[str, Any],
    ) -> List[GameStep]:
        """
        Returns steps to run after a successful block ('if you do' effects).

        Only called if the defense succeeded (context['block_succeeded'] == True).

        Example: Wasp's Reflect Projectiles - "if you do, enemy hero discards"

        Args:
            state: Current game state.
            defender: The hero who successfully blocked.
            card: The defense card that was used.
            context: Contains combat result information including block_succeeded.

        Returns:
            List of steps to execute after the block, or empty list.
        """
        return []


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

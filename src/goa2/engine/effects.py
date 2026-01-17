from __future__ import annotations
from abc import ABC
from typing import List, Dict, Any, TYPE_CHECKING, Optional
from pydantic import BaseModel

if TYPE_CHECKING:
    from goa2.engine.steps import GameStep
    from goa2.domain.state import GameState
    from goa2.domain.models import Hero, Card
    from goa2.domain.models.enums import PassiveTrigger
    from goa2.engine.stats import CardStats


class PassiveConfig(BaseModel):
    """
    Configuration for a card's passive ability.

    Passive abilities are persistent effects that trigger during specific game events
    (e.g., before attacking, before moving). They differ from active effects which
    only trigger once when the card is played.

    Attributes:
        trigger: When the passive activates (BEFORE_ATTACK, BEFORE_MOVEMENT, etc.)
        uses_per_turn: Maximum uses per turn. -1 means unlimited.
        is_optional: If True, player is prompted "you may". If False, auto-executes.
        prompt: Custom UI prompt for optional passives.
    """

    trigger: "PassiveTrigger"
    uses_per_turn: int = 1
    is_optional: bool = True
    prompt: str = ""


class CardEffect(ABC):
    """
    Base class for custom card logic.
    Primary actions on cards delegate their execution to these effects.

    Public API (called by engine):
        get_steps: Steps for primary action on your turn (ATTACK/SKILL/MOVEMENT).
        get_defense_steps: Steps when used as primary DEFENSE in reaction.
        get_on_block_steps: Steps after successful block ('if you do' effects).

    Override in subclasses (stats pre-computed):
        build_steps: Implement primary action logic with pre-computed stats.
        build_defense_steps: Implement defense logic with pre-computed stats.
        build_on_block_steps: Implement on-block logic with pre-computed stats.
    """

    # -------------------------------------------------------------------------
    # Public API - Called by engine. Computes stats and delegates to build_*.
    # -------------------------------------------------------------------------

    def get_steps(
        self, state: "GameState", hero: "Hero", card: "Card"
    ) -> List["GameStep"]:
        """
        Returns steps for the card's primary action on your turn.

        Computes card stats and delegates to build_steps().
        Override build_steps() in subclasses, not this method.
        """
        from goa2.engine.stats import compute_card_stats

        stats = compute_card_stats(state, hero.id, card)
        return self.build_steps(state, hero, card, stats)

    def get_defense_steps(
        self,
        state: "GameState",
        defender: "Hero",
        card: "Card",
        context: Dict[str, Any],
    ) -> Optional[List["GameStep"]]:
        """
        Returns steps when used as primary DEFENSE in reaction.

        Computes card stats and delegates to build_defense_steps().
        Override build_defense_steps() in subclasses, not this method.

        Returns:
            List of steps to execute, or None to fall back to get_steps().
        """
        from goa2.engine.stats import compute_card_stats

        stats = compute_card_stats(state, defender.id, card)
        return self.build_defense_steps(state, defender, card, stats, context)

    def get_on_block_steps(
        self,
        state: "GameState",
        defender: "Hero",
        card: "Card",
        context: Dict[str, Any],
    ) -> List["GameStep"]:
        """
        Returns steps to run after a successful block ('if you do' effects).

        Computes card stats and delegates to build_on_block_steps().
        Override build_on_block_steps() in subclasses, not this method.
        """
        from goa2.engine.stats import compute_card_stats

        stats = compute_card_stats(state, defender.id, card)
        return self.build_on_block_steps(state, defender, card, stats, context)

    # -------------------------------------------------------------------------
    # Override these in subclasses - stats are pre-computed
    # -------------------------------------------------------------------------

    def build_steps(
        self,
        state: "GameState",
        hero: "Hero",
        card: "Card",
        stats: "CardStats",
    ) -> List["GameStep"]:
        """
        Returns steps for the card's primary action on your turn.

        Override this method in subclasses. Stats are pre-computed.

        Args:
            state: Current game state.
            hero: The hero playing the card.
            card: The card being played.
            stats: Pre-computed card stats (attack, defense, range, radius, etc.)

        Returns:
            List of steps to execute.
        """
        return []

    def build_defense_steps(
        self,
        state: "GameState",
        defender: "Hero",
        card: "Card",
        stats: "CardStats",
        context: Dict[str, Any],
    ) -> Optional[List["GameStep"]]:
        """
        Returns steps when used as primary DEFENSE in reaction.

        Override this method in subclasses. Stats are pre-computed.

        Args:
            state: Current game state.
            defender: The hero defending (being attacked).
            card: The defense card being played.
            stats: Pre-computed card stats.
            context: Contains attack information:
                - attack_is_ranged: bool - True if the attack is ranged
                - attacker_id: str - ID of the attacking unit
                - defender_id: str - ID of the defending hero

        Returns:
            List of steps to execute, or None to fall back to build_steps().
        """
        return None

    def build_on_block_steps(
        self,
        state: "GameState",
        defender: "Hero",
        card: "Card",
        stats: "CardStats",
        context: Dict[str, Any],
    ) -> List["GameStep"]:
        """
        Returns steps to run after a successful block ('if you do' effects).

        Override this method in subclasses. Stats are pre-computed.

        Args:
            state: Current game state.
            defender: The hero who successfully blocked.
            card: The defense card that was used.
            stats: Pre-computed card stats.
            context: Contains combat result information including block_succeeded.

        Returns:
            List of steps to execute after the block, or empty list.
        """
        return []

    # -------------------------------------------------------------------------
    # Passive ability methods (unchanged)
    # -------------------------------------------------------------------------

    def get_passive_config(self) -> Optional[PassiveConfig]:
        """
        Returns passive configuration if this card has a passive ability.

        Passive abilities are persistent effects that trigger during specific game
        events while the card is active (RESOLVED + face-up for regular cards,
        or hero level >= 8 for ultimates).

        Override in subclasses that have passive abilities.

        Returns:
            PassiveConfig describing the passive, or None if no passive ability.
        """
        return None

    def get_passive_steps(
        self,
        state: "GameState",
        hero: "Hero",
        card: "Card",
        trigger: "PassiveTrigger",
        context: Dict[str, Any],
    ) -> List["GameStep"]:
        """
        Returns steps to execute when this passive ability triggers.

        Only called if get_passive_config() returns a config with a matching trigger.

        Args:
            state: Current game state.
            hero: The hero who owns the passive ability.
            card: The card providing the passive ability.
            trigger: The trigger point (BEFORE_ATTACK, BEFORE_MOVEMENT, etc.)
            context: Execution context with current action information.

        Returns:
            List of steps to execute for the passive effect.
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

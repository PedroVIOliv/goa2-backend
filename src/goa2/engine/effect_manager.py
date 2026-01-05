"""EffectManager for creating and expiring effects/modifiers."""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from goa2.domain.models.modifier import Modifier, DurationType
from goa2.domain.models.enums import StatType
from goa2.domain.models.effect import ActiveEffect, EffectType, EffectScope

if TYPE_CHECKING:
    from goa2.domain.state import GameState


class EffectManager:
    """
    Manages effect lifecycle: creation, expiration, querying.
    Works alongside ValidationService.
    """

    @staticmethod
    def create_modifier(
        state: "GameState",
        source_id: str,
        target_id: str,
        stat_type: Optional[StatType] = None,
        value_mod: int = 0,
        status_tag: Optional[str] = None,
        duration: DurationType = DurationType.THIS_TURN,
        source_card_id: Optional[str] = None
    ) -> Modifier:
        """Create and register a new modifier."""
        modifier = Modifier(
            id=f"mod_{state.create_entity_id('m')}",
            source_id=source_id,
            source_card_id=source_card_id,
            target_id=target_id,
            stat_type=stat_type,
            value_mod=value_mod,
            status_tag=status_tag,
            duration=duration,
            created_at_turn=state.turn,
            created_at_round=state.round
        )
        state.add_modifier(modifier)
        return modifier

    @staticmethod
    def create_effect(
        state: "GameState",
        source_id: str,
        effect_type: EffectType,
        scope: EffectScope,
        duration: DurationType = DurationType.THIS_TURN,
        source_card_id: Optional[str] = None,
        **kwargs
    ) -> ActiveEffect:
        """Create and register a new spatial effect."""
        effect = ActiveEffect(
            id=f"eff_{state.create_entity_id('e')}",
            source_id=source_id,
            source_card_id=source_card_id,
            effect_type=effect_type,
            scope=scope,
            duration=duration,
            created_at_turn=state.turn,
            created_at_round=state.round,
            **kwargs
        )
        state.add_effect(effect)
        return effect

    @staticmethod
    def expire_by_card(state: "GameState", card_id: str):
        """Remove all effects/modifiers linked to a specific card."""
        state.active_modifiers = [
            m for m in state.active_modifiers
            if m.source_card_id != card_id
        ]
        state.active_effects = [
            e for e in state.active_effects
            if e.source_card_id != card_id
        ]

    @staticmethod
    def expire_modifiers(state: "GameState", duration: DurationType):
        """Remove all modifiers matching duration type."""
        state.active_modifiers = [
            m for m in state.active_modifiers
            if m.duration != duration
        ]

    @staticmethod
    def expire_effects(state: "GameState", duration: DurationType):
        """Remove all effects matching duration type."""
        state.active_effects = [
            e for e in state.active_effects
            if e.duration != duration
        ]

    @staticmethod
    def expire_by_source(state: "GameState", source_id: str):
        """Remove all effects/modifiers from a specific source (e.g., defeated hero)."""
        state.active_modifiers = [
            m for m in state.active_modifiers
            if m.source_id != source_id
        ]
        state.active_effects = [
            e for e in state.active_effects
            if e.source_id != source_id
        ]

    @staticmethod
    def cleanup_stale_effects(state: "GameState"):
        """
        Remove effects whose source card is no longer in played state.
        Called at round end for memory cleanup (lazy expiration).
        """
        def is_effect_valid(effect: ActiveEffect) -> bool:
            # Effects without card link are always valid
            if effect.source_card_id is None:
                return True
            # PASSIVE effects are always valid
            if effect.duration == DurationType.PASSIVE:
                return True
            # Check if card is still in played state
            return state.validator._is_card_in_played_state(
                state, effect.source_id, effect.source_card_id
            )

        def is_modifier_valid(mod: Modifier) -> bool:
            # Modifiers without card link are always valid
            if mod.source_card_id is None:
                return True
            # PASSIVE modifiers are always valid
            if mod.duration == DurationType.PASSIVE:
                return True
            # Check if card is still in played state
            return state.validator._is_card_in_played_state(
                state, mod.source_id, mod.source_card_id
            )

        state.active_effects = [e for e in state.active_effects if is_effect_valid(e)]
        state.active_modifiers = [m for m in state.active_modifiers if is_modifier_valid(m)]

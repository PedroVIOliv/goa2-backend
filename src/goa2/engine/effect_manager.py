"""EffectManager for creating and expiring effects/modifiers."""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING, List

from goa2.domain.models.modifier import Modifier, DurationType
from goa2.domain.models.enums import StatType
from goa2.domain.models.effect import ActiveEffect, EffectType, EffectScope
from goa2.domain.types import BoardEntityID, CardID, ModifierID

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
        source_card_id: Optional[str] = None,
        is_active: bool = False,
    ) -> Modifier:
        """Create and register a new modifier."""
        modifier = Modifier(
            id=ModifierID(f"mod_{state.create_entity_id('m')}"),
            source_id=BoardEntityID(source_id),
            source_card_id=CardID(source_card_id) if source_card_id else None,
            target_id=BoardEntityID(target_id),
            stat_type=stat_type,
            value_mod=value_mod,
            status_tag=status_tag,
            duration=duration,
            created_at_turn=state.turn,
            created_at_round=state.round,
            is_active=is_active,
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
        except_card_colors: Optional[List] = None,
        is_active: bool = False,
        **kwargs,
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
            except_card_colors=except_card_colors or [],
            is_active=is_active,
            **kwargs,
        )
        state.add_effect(effect)
        return effect

    @staticmethod
    def expire_by_card(state: "GameState", card_id: str):
        """Remove all effects/modifiers linked to a specific card."""
        state.active_modifiers = [
            m for m in state.active_modifiers if m.source_card_id != card_id
        ]
        state.active_effects = [
            e for e in state.active_effects if e.source_card_id != card_id
        ]

    @staticmethod
    def expire_modifiers(state: "GameState", duration: DurationType):
        """Remove all modifiers matching duration type."""
        state.active_modifiers = [
            m for m in state.active_modifiers if m.duration != duration
        ]

    @staticmethod
    def expire_effects(state: "GameState", duration: DurationType):
        """Remove all effects matching duration type."""
        state.active_effects = [
            e for e in state.active_effects if e.duration != duration
        ]

    @staticmethod
    def expire_by_source(state: "GameState", source_id: str):
        """Remove all effects/modifiers from a specific source (e.g., defeated hero)."""
        state.active_modifiers = [
            m for m in state.active_modifiers if m.source_id != source_id
        ]
        state.active_effects = [
            e for e in state.active_effects if e.source_id != source_id
        ]

    # -------------------------------------------------------------------------
    # Activation / Deactivation
    # -------------------------------------------------------------------------

    @staticmethod
    def activate_effects_by_card(state: "GameState", card_id: str):
        """
        Activate all effects/modifiers linked to a specific card.
        Called when a card becomes RESOLVED (after hero's turn completes).
        """
        for mod in state.active_modifiers:
            if mod.source_card_id == card_id:
                mod.is_active = True
        for effect in state.active_effects:
            if effect.source_card_id == card_id:
                effect.is_active = True

    @staticmethod
    def deactivate_effects_by_card(state: "GameState", card_id: str):
        """
        Deactivate all effects/modifiers linked to a specific card.
        Called when a card leaves played state or is turned facedown.
        """
        for mod in state.active_modifiers:
            if mod.source_card_id == card_id:
                mod.is_active = False
        for effect in state.active_effects:
            if effect.source_card_id == card_id:
                effect.is_active = False

    @staticmethod
    def activate_effect_by_id(state: "GameState", effect_id: str):
        """Explicitly activate a specific effect by ID (for card abilities that reactivate)."""
        for effect in state.active_effects:
            if effect.id == effect_id:
                effect.is_active = True
                return
        for mod in state.active_modifiers:
            if mod.id == effect_id:
                mod.is_active = True
                return

    @staticmethod
    def deactivate_effect_by_id(state: "GameState", effect_id: str):
        """Explicitly deactivate a specific effect by ID."""
        for effect in state.active_effects:
            if effect.id == effect_id:
                effect.is_active = False
                return
        for mod in state.active_modifiers:
            if mod.id == effect_id:
                mod.is_active = False
                return

    @staticmethod
    def cleanup_stale_effects(state: "GameState"):
        """
        Remove effects that are no longer active and have expired.
        Called at round end for memory cleanup.

        Effects are removed if:
        - They have a source card AND is_active is False (card left play/went facedown)
        - AND they're not PASSIVE (PASSIVE effects persist)
        """

        def is_effect_valid(effect: ActiveEffect) -> bool:
            # Effects without card link are always valid (cleaned by duration)
            if effect.source_card_id is None:
                return True
            # PASSIVE effects are always valid
            if effect.duration == DurationType.PASSIVE:
                return True
            # Card-based effects are valid if still active
            return effect.is_active

        def is_modifier_valid(mod: Modifier) -> bool:
            # Modifiers without card link are always valid (cleaned by duration)
            if mod.source_card_id is None:
                return True
            # PASSIVE modifiers are always valid
            if mod.duration == DurationType.PASSIVE:
                return True
            # Card-based modifiers are valid if still active
            return mod.is_active

        state.active_effects = [e for e in state.active_effects if is_effect_valid(e)]
        state.active_modifiers = [
            m for m in state.active_modifiers if is_modifier_valid(m)
        ]

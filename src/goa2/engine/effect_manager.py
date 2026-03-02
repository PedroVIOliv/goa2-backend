"""EffectManager for creating and expiring effects."""

from __future__ import annotations
from typing import Optional, Tuple, TYPE_CHECKING, List

from goa2.domain.models.effect import (
    ActiveEffect,
    EffectType,
    EffectScope,
    DurationType,
)
from goa2.domain.models.enums import ActionType

if TYPE_CHECKING:
    from goa2.domain.state import GameState


class EffectManager:
    """
    Manages effect lifecycle: creation, expiration, querying.
    Works alongside ValidationService.
    """

    @staticmethod
    def create_effect(
        state: "GameState",
        source_id: str,
        effect_type: EffectType,
        scope: EffectScope,
        duration: DurationType = DurationType.THIS_TURN,
        source_card_id: Optional[str] = None,
        except_card_colors: Optional[List] = None,
        except_attacker_ids: Optional[List[str]] = None,
        is_active: bool = False,
        origin_action_type: Optional["ActionType"] = None,
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
            except_attacker_ids=except_attacker_ids or [],
            is_active=is_active,
            origin_action_type=origin_action_type,
            **kwargs,
        )
        state.add_effect(effect)
        if source_card_id:
            card = state.get_card_by_id(source_card_id)
            if card:
                card.is_active = True
        return effect

    @staticmethod
    def _update_card_active_status(state: "GameState", card_id: str):
        """
        Set card.is_active based on whether any effects reference it.
        """
        has_active_effect = any(
            e.source_card_id == card_id for e in state.active_effects
        )
        card = state.get_card_by_id(card_id)
        if card:
            card.is_active = has_active_effect

    @staticmethod
    def expire_by_card(state: "GameState", card_id: str):
        """Remove all effects linked to a specific card."""
        state.active_effects = [
            e for e in state.active_effects if e.source_card_id != card_id
        ]
        card = state.get_card_by_id(card_id)
        if card:
            card.is_active = False

    @staticmethod
    def expire_active_turn_effects(
        state: "GameState",
    ) -> List[Tuple[str, List]]:
        """Expire THIS_TURN and active NEXT_TURN effects.

        NEXT_TURN effects are active on created_at_turn + 1 (same round only).
        Returns [(source_id, finishing_steps)] for expired effects that carry
        finishing steps.
        """

        def is_expiring_this_turn(e: ActiveEffect) -> bool:
            if e.duration == DurationType.THIS_TURN:
                return True
            if e.duration == DurationType.NEXT_TURN:
                return (
                    state.round == e.created_at_round
                    and state.turn == e.created_at_turn + 1
                )
            return False

        expiring = [e for e in state.active_effects if is_expiring_this_turn(e)]
        finishing: List[Tuple[str, List]] = [
            (e.source_id, e.finishing_steps)
            for e in expiring
            if e.finishing_steps
        ]
        affected_card_ids = {
            e.source_card_id for e in expiring if e.source_card_id
        }
        state.active_effects = [
            e for e in state.active_effects if not is_expiring_this_turn(e)
        ]
        for card_id in affected_card_ids:
            EffectManager._update_card_active_status(state, card_id)
        return finishing

    @staticmethod
    def expire_effects(
        state: "GameState", duration: DurationType
    ) -> List[Tuple[str, List]]:
        """Remove all effects matching duration type.

        Returns [(source_id, finishing_steps)] for expired effects that carry
        finishing steps (used by DELAYED_TRIGGER effects).
        """
        expiring = [e for e in state.active_effects if e.duration == duration]
        finishing: List[Tuple[str, List]] = [
            (e.source_id, e.finishing_steps)
            for e in expiring
            if e.finishing_steps
        ]
        affected_card_ids = {
            e.source_card_id for e in expiring if e.source_card_id
        }
        state.active_effects = [
            e for e in state.active_effects if e.duration != duration
        ]
        for card_id in affected_card_ids:
            EffectManager._update_card_active_status(state, card_id)
        return finishing

    @staticmethod
    def expire_by_source(state: "GameState", source_id: str):
        """Remove all effects from a specific source (e.g., defeated hero)."""
        affected_card_ids = {
            e.source_card_id
            for e in state.active_effects
            if e.source_id == source_id and e.source_card_id
        }
        state.active_effects = [
            e for e in state.active_effects if e.source_id != source_id
        ]
        for card_id in affected_card_ids:
            EffectManager._update_card_active_status(state, card_id)

    # -------------------------------------------------------------------------
    # Activation / Deactivation
    # -------------------------------------------------------------------------

    @staticmethod
    def activate_effects_by_card(state: "GameState", card_id: str):
        """
        Activate all effects linked to a specific card.
        Called when a card becomes RESOLVED (after hero's turn completes).
        """
        for effect in state.active_effects:
            if effect.source_card_id == card_id:
                effect.is_active = True

    @staticmethod
    def deactivate_effects_by_card(state: "GameState", card_id: str):
        """
        Deactivate all effects linked to a specific card.
        Called when a card leaves played state or is turned facedown.
        """
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

    @staticmethod
    def deactivate_effect_by_id(state: "GameState", effect_id: str):
        """Explicitly deactivate a specific effect by ID."""
        for effect in state.active_effects:
            if effect.id == effect_id:
                effect.is_active = False
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

        state.active_effects = [e for e in state.active_effects if is_effect_valid(e)]

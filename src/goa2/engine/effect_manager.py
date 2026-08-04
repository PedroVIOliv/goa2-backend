"""EffectManager for creating and expiring effects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models.effect import (
    ActiveEffect,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import ActionType, CardState

if TYPE_CHECKING:
    from goa2.domain.state import GameState


class EffectManager:
    """
    Manages effect lifecycle: creation, expiration, querying.
    Works alongside ValidationService.
    """

    @staticmethod
    def award_minion_defeat_bounties(state: GameState, minion_id: str) -> list:
        """Pay out MINION_DEFEAT_BOUNTY effects (Swift's Mark for Death / Hunting
        Season) when an enemy minion in radius is defeated.

        Any player's defeat counts. The radius is measured from the
        beneficiary's *current* hex (it moves with them), and each effect pays at
        most ``max_value`` coins total (decremented per payout). Returns the
        GameEvents for coins granted.
        """
        from goa2.domain.events import GameEvent, GameEventType
        from goa2.domain.types import BoardEntityID, HeroID, UnitID
        from goa2.engine.stats import _is_effect_active
        from goa2.engine.topology import topology_distance

        events: list = []
        minion = state.get_unit(UnitID(minion_id))
        minion_hex = state.entity_locations.get(BoardEntityID(minion_id))
        if minion is None or minion_hex is None:
            return events

        for effect in state.active_effects:
            if effect.effect_type != EffectType.MINION_DEFEAT_BOUNTY:
                continue
            if not _is_effect_active(effect, state):
                continue
            if (effect.max_value or 0) <= 0:
                continue
            beneficiary = state.get_hero(HeroID(effect.protected_unit_id))
            if beneficiary is None:
                continue
            # Only enemy minions of the beneficiary count.
            if getattr(minion, "team", None) == beneficiary.team:
                continue
            bene_hex = state.get_position(effect.protected_unit_id)
            if bene_hex is None:
                continue
            if topology_distance(bene_hex, minion_hex, state) > (effect.scope.range or 0):
                continue

            beneficiary.gold += 1
            effect.max_value = (effect.max_value or 0) - 1
            events.append(
                GameEvent(
                    event_type=GameEventType.GOLD_GAINED,
                    actor_id=effect.protected_unit_id,
                    target_id=minion_id,
                    metadata={"amount": 1, "reason": "minion_defeat_bounty"},
                )
            )
        return events

    @staticmethod
    def create_effect(
        state: GameState,
        source_id: str,
        effect_type: EffectType,
        scope: EffectScope,
        duration: DurationType = DurationType.THIS_TURN,
        source_card_id: str | None = None,
        except_card_colors: list | None = None,
        except_attacker_ids: list[str] | None = None,
        is_active: bool = False,
        origin_action_type: ActionType | None = None,
        **kwargs,
    ) -> ActiveEffect:
        """Create and register a new spatial effect.

        Positional origins bind to the physical board entity: a multi-piece
        hero's implicit (or self-referencing) origin resolves to the acting
        piece, because the owner hero ID has no board position once its turn
        ends and the effect would silently lose its anchor.

        Card-bound effects are deduplicated: see ``_find_existing_instance``.
        """
        if scope.shape != Shape.GLOBAL and scope.origin_hex is None:
            origin_id = scope.origin_id or source_id
            board_origin = state.resolve_board_actor(str(origin_id))
            if board_origin != str(origin_id):
                scope = scope.model_copy(update={"origin_id": board_origin})

        if effect_type == EffectType.STATIC_BARRIER:
            barrier_origin = kwargs.get("barrier_origin_id") or source_id
            board_barrier_origin = state.resolve_board_actor(str(barrier_origin))
            if board_barrier_origin != str(barrier_origin):
                kwargs["barrier_origin_id"] = board_barrier_origin

        existing = EffectManager._find_existing_instance(
            state, source_id, source_card_id, effect_type, scope
        )
        if existing is not None:
            return existing

        card = state.get_card_by_id(source_card_id) if source_card_id else None
        # Dormancy models "played, but not yet resolved": FinalizeHeroTurnStep
        # activates a card's effects when it resolves. That hook only ever fires
        # for a hero's current turn card, so an effect bound to a card that is
        # not awaiting resolution — one re-performed after resolving, or an
        # enemy's card driven by Mind Grip — would stay dormant forever.
        if card is not None and card.state != CardState.UNRESOLVED:
            is_active = True

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
        if card is not None:
            card.is_active = True
        return effect

    @staticmethod
    def _find_existing_instance(
        state: GameState,
        source_id: str,
        source_card_id: str | None,
        effect_type: EffectType,
        scope: EffectScope,
    ) -> ActiveEffect | None:
        """This source's live instance of this card effect, if it has one.

        Game rule: only one instance of an active effect per card can be
        active, and repeating an active effect does not duplicate it. Identity
        is (source, card, effect_type, scope) — a card whose text needs several
        distinct payloads (Brogan's Bulwark, Dodger's Enfeeblement) still gets
        one row per payload, but performing that card again reuses them.

        The source is part of the key because a card can be performed by someone
        else (Gydion's spells, NebKher's Mind Grip): the copier needs their own
        instance, not the original caster's.

        The match ignores ``is_active`` so a present-but-deactivated row still
        blocks a duplicate, and callers must treat a hit as a pure no-op: no
        payload or charge refresh, no new timestamps, and no ``card.is_active``
        write, since a card deliberately turned facedown must not be
        reactivated by a repeat.

        Effects with no card (token-bound effects, engine-internal delayed
        triggers) are never deduplicated — their lifecycle is the token's or
        the schedule's, not a card's.
        """
        if not source_card_id:
            return None
        return next(
            (
                effect
                for effect in state.active_effects
                if effect.source_card_id == source_card_id
                and effect.source_id == source_id
                and effect.effect_type == effect_type
                and effect.scope == scope
            ),
            None,
        )

    @staticmethod
    def _update_card_active_status(state: GameState, card_id: str):
        """
        Set card.is_active based on whether any effects reference it.
        """
        has_active_effect = any(e.source_card_id == card_id for e in state.active_effects)
        card = state.get_card_by_id(card_id)
        if card:
            card.is_active = has_active_effect

    @staticmethod
    def expire_by_card(state: GameState, card_id: str):
        """Remove all effects linked to a specific card (premature removal).

        Intentionally does NOT collect or run ``finishing_steps``: those fire
        only when an effect ends *naturally* via its duration (see
        ``expire_active_turn_effects`` / ``expire_effects``). An effect cut short
        — card leaves play, source defeated — must not trigger its end-of-turn /
        end-of-round payload. (Per game rules: e.g. if Min is defeated the
        Death Grenade does not explode.)
        """
        state.active_effects = [e for e in state.active_effects if e.source_card_id != card_id]
        card = state.get_card_by_id(card_id)
        if card:
            card.is_active = False

    @staticmethod
    def expire_active_turn_effects(
        state: GameState,
    ) -> list[tuple[str, list]]:
        """Expire THIS_TURN and active NEXT_TURN effects.

        NEXT_TURN effects are active on created_at_turn + 1 (same round only).
        Returns [(source_id, finishing_steps)] for expired effects that carry
        finishing steps.
        """

        def is_expiring_this_turn(e: ActiveEffect) -> bool:
            if e.duration == DurationType.THIS_TURN:
                return True
            if e.duration == DurationType.NEXT_TURN:
                if state.round != e.created_at_round:
                    return True  # Cross-round NEXT_TURN effects always expire
                return state.turn >= e.created_at_turn + 1
            return False

        expiring = [e for e in state.active_effects if is_expiring_this_turn(e)]
        # AFTER_CARDS_PLAYED_TRIGGER payloads fire only at their dedicated
        # firing point (start_resolution_phase); expiring here means the
        # window was missed (round boundary etc.) → fizzle silently.
        finishing: list[tuple[str, list]] = [
            (e.source_id, e.finishing_steps)
            for e in expiring
            if e.finishing_steps and e.effect_type != EffectType.AFTER_CARDS_PLAYED_TRIGGER
        ]
        affected_card_ids = {e.source_card_id for e in expiring if e.source_card_id}
        state.active_effects = [e for e in state.active_effects if not is_expiring_this_turn(e)]
        for card_id in affected_card_ids:
            EffectManager._update_card_active_status(state, card_id)
        return finishing

    @staticmethod
    def expire_effects(state: GameState, duration: DurationType) -> list[tuple[str, list]]:
        """Remove all effects matching duration type.

        Returns [(source_id, finishing_steps)] for expired effects that carry
        finishing steps (used by DELAYED_TRIGGER effects).
        """
        expiring = [e for e in state.active_effects if e.duration == duration]
        finishing: list[tuple[str, list]] = [
            (e.source_id, e.finishing_steps)
            for e in expiring
            if e.finishing_steps and e.effect_type != EffectType.AFTER_CARDS_PLAYED_TRIGGER
        ]
        affected_card_ids = {e.source_card_id for e in expiring if e.source_card_id}
        state.active_effects = [e for e in state.active_effects if e.duration != duration]
        for card_id in affected_card_ids:
            EffectManager._update_card_active_status(state, card_id)
        return finishing

    @staticmethod
    def expire_by_source(state: GameState, source_id: str):
        """Remove all effects from a specific source, e.g. a defeated hero
        (premature removal).

        Intentionally does NOT collect or run ``finishing_steps``. Finishing
        steps are an effect's *natural* end-of-turn/round payload and only fire
        when the effect expires on schedule (``expire_active_turn_effects`` /
        ``expire_effects``). When the source ends prematurely (defeated), the
        payload must not run — per game rules a delayed trigger whose owner is
        gone simply fizzles (e.g. Min's Death Grenade does not explode). Any
        physical leftovers (tokens) are reclaimed by the normal round-end sweep.

        Ownership is ``source_id`` — the hero who created the effect, never the
        owner of the card it came from. A card can be performed by someone else
        (NebKher's Mind Grip), and that effect belongs to the performer. Effects
        registered against another unit (Hanu's Journey immunity) carry that unit
        in ``subject_id``, so they still end with their creator.
        """
        affected_card_ids = {
            e.source_card_id
            for e in state.active_effects
            if e.source_id == source_id and e.source_card_id
        }
        state.active_effects = [e for e in state.active_effects if e.source_id != source_id]
        for card_id in affected_card_ids:
            EffectManager._update_card_active_status(state, card_id)

    # -------------------------------------------------------------------------
    # Activation / Deactivation
    # -------------------------------------------------------------------------

    @staticmethod
    def activate_effects_by_card(state: GameState, card_id: str):
        """
        Activate all effects linked to a specific card.
        Called when a card becomes RESOLVED (after hero's turn completes).
        """
        for effect in state.active_effects:
            if effect.source_card_id == card_id:
                effect.is_active = True

    @staticmethod
    def deactivate_effects_by_card(state: GameState, card_id: str):
        """
        Deactivate all effects linked to a specific card.
        Called when a card leaves played state or is turned facedown.
        """
        for effect in state.active_effects:
            if effect.source_card_id == card_id:
                effect.is_active = False

    @staticmethod
    def activate_effect_by_id(state: GameState, effect_id: str):
        """Explicitly activate a specific effect by ID (for card abilities that reactivate)."""
        for effect in state.active_effects:
            if effect.id == effect_id:
                effect.is_active = True
                return

    @staticmethod
    def deactivate_effect_by_id(state: GameState, effect_id: str):
        """Explicitly deactivate a specific effect by ID."""
        for effect in state.active_effects:
            if effect.id == effect_id:
                effect.is_active = False
                return

    @staticmethod
    def expire_effect_by_id(state: GameState, effect_id: str):
        """Remove a single effect by ID and refresh its card's active status.

        Use this (instead of ``deactivate_effect_by_id``) when an effect is
        permanently *consumed* — e.g. a one-shot disruptor that fires once and
        is spent. ``deactivate_effect_by_id`` only flips ``effect.is_active`` and
        leaves the effect in ``active_effects``; because a card's ``is_active``
        flag tracks effect *existence* (see ``_update_card_active_status``), the
        owning card would stay marked active (tapped) even though its effect is
        done. Removing the effect outright untaps a card whose only effect was
        this one, and suppresses re-triggering regardless of card linkage.
        """
        card_ids = {
            e.source_card_id for e in state.active_effects if e.id == effect_id and e.source_card_id
        }
        state.active_effects = [e for e in state.active_effects if e.id != effect_id]
        for card_id in card_ids:
            EffectManager._update_card_active_status(state, card_id)

    @staticmethod
    def cleanup_stale_effects(state: GameState):
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

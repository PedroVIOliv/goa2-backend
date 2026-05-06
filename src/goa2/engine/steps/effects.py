"""Active effects and passive ability steps."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import logging
from pydantic import Field

from goa2.engine.steps.base import GameStep, StepResult
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, HeroID
from goa2.domain.models import ActionType, Card, CardColor, CardState, StepType, TeamColor, Token
from goa2.domain.models.effect import ActiveEffect, DurationType, EffectScope, EffectType
from goa2.domain.models.enums import DisplacementType, StatType
from goa2.domain.hex import Hex
from goa2.domain.input import InputOption, InputRequestType, create_input_request
from goa2.domain.events import GameEvent, GameEventType
from goa2.engine.effect_manager import EffectManager
from goa2.engine.topology import get_topology_service


logger = logging.getLogger(__name__)


class CreateEffectStep(GameStep):
    """Creates a spatial ActiveEffect in the game state."""

    type: StepType = StepType.CREATE_EFFECT

    effect_type: EffectType
    scope: EffectScope
    duration: DurationType = DurationType.THIS_TURN

    restrictions: List[ActionType] = Field(default_factory=list)
    displacement_blocks: List[DisplacementType] = Field(default_factory=list)
    except_card_colors: List[CardColor] = Field(default_factory=list)
    except_attacker_ids: List[str] = Field(
        default_factory=list
    )  # Direct list of attacker IDs
    except_attacker_key: Optional[str] = None  # Context key to read attacker ID from
    stat_type: Optional[StatType] = None
    stat_value: int = 0
    max_value: Optional[int] = None
    limit_actions_only: bool = False

    blocks_enemy_actors: bool = True
    blocks_friendly_actors: bool = False
    blocks_self: bool = False
    is_active: bool = False  # Override default dormant state if True

    # Card linkage (for card-based effects)
    source_card_id: Optional[str] = None  # Explicit card ID
    use_context_card: bool = True  # If True, use "current_card_id" from context

    # Origin action type - tracks whether effect came from skill or attack
    origin_action_type: Optional[ActionType] = None

    # Dynamic origin: read scope.origin_id from context at resolve time
    origin_id_key: Optional[str] = None

    # Token-bound effect: skip card binding so lifecycle is tied to token, not card
    is_token_effect: bool = False

    # Static Barrier parameters (Wasp)
    barrier_radius: int = 0  # The radius boundary for the barrier
    barrier_origin_id: Optional[str] = None  # Entity ID for radius calculation

    # Allowed discard colors for MINION_PROTECTION effects (Brogan)
    allowed_discard_colors: List[CardColor] = Field(default_factory=list)

    # Steps to execute when this effect expires (for DELAYED_TRIGGER effects)
    # Patched to List[AnyStep] in step_types.py.
    finishing_steps: List[GameStep] = Field(default_factory=list)

    # MOVEMENT_AURA_ZONE payload (Silverarrow - Trailblazer)
    grants_pass_through_obstacles: bool = False

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        # Resolve source card ID (skip for token-bound effects)
        card_id = None
        if not self.is_token_effect:
            card_id = self.source_card_id
            if card_id is None and self.use_context_card:
                card_id = context.get("current_card_id")

        # Resolve origin action type: use explicit value or fall back to context
        action_type = self.origin_action_type
        if action_type is None:
            action_type = context.get("current_action_type")

        # Resolve except_attacker_ids: combine direct list with context key
        resolved_except_attackers = list(self.except_attacker_ids)
        if self.except_attacker_key:
            attacker_from_context = context.get(self.except_attacker_key)
            if (
                attacker_from_context
                and attacker_from_context not in resolved_except_attackers
            ):
                resolved_except_attackers.append(attacker_from_context)

        from goa2.engine.effect_manager import EffectManager

        # Resolve dynamic origin_id from context if specified
        resolved_scope = self.scope
        if self.origin_id_key:
            origin_id_from_ctx = context.get(self.origin_id_key)
            if origin_id_from_ctx:
                resolved_scope = self.scope.model_copy(
                    update={"origin_id": str(origin_id_from_ctx)}
                )

        EffectManager.create_effect(
            state=state,
            source_id=(
                str(state.current_actor_id) if state.current_actor_id else "system"
            ),
            source_card_id=card_id,
            effect_type=self.effect_type,
            scope=resolved_scope,
            duration=self.duration,
            restrictions=self.restrictions,
            displacement_blocks=self.displacement_blocks,
            except_card_colors=self.except_card_colors,
            except_attacker_ids=resolved_except_attackers,
            stat_type=self.stat_type,
            stat_value=self.stat_value,
            max_value=self.max_value,
            limit_actions_only=self.limit_actions_only,
            blocks_enemy_actors=self.blocks_enemy_actors,
            blocks_friendly_actors=self.blocks_friendly_actors,
            blocks_self=self.blocks_self,
            is_active=self.is_active,
            origin_action_type=action_type,
            barrier_radius=self.barrier_radius,
            barrier_origin_id=self.barrier_origin_id,
            finishing_steps=self.finishing_steps,
            allowed_discard_colors=self.allowed_discard_colors,
            grants_pass_through_obstacles=self.grants_pass_through_obstacles,
        )

        source = str(state.current_actor_id) if state.current_actor_id else "system"
        logger.debug(f"   [EFFECT] Created {self.effect_type.value} from {source}")

        return StepResult(
            is_finished=True,
            events=[
                GameEvent(
                    event_type=GameEventType.EFFECT_CREATED,
                    actor_id=source,
                    metadata={
                        "effect_type": self.effect_type.value,
                        "duration": self.duration.value,
                    },
                )
            ],
        )


class FinishedExpiringEffectStep(GameStep):
    """
    Placeholder step to indicate that an expiring effect has finished resolving.
    Primarily used to correctly mark the end of abort action cascade.
    """

    type: StepType = StepType.FINISHED_EXPIRING_EFFECT

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        logger.debug("   [EFFECT] Finished resolving expiring effect.")
        return StepResult(is_finished=True)


class CancelEffectsStep(GameStep):
    """
    Cancels (removes) active effects matching specified criteria.

    Usage:
        CancelEffectsStep(
            effect_types=[EffectType.TARGET_PREVENTION],
            origin_action_types=[ActionType.SKILL],
            source_team=TeamColor.RED,
            scope=EffectScope(shape=Shape.RADIUS, range=3, origin_id="turret_1"),
        )
    """

    type: StepType = StepType.CANCEL_EFFECTS

    effect_types: List[EffectType] = Field(default_factory=list)
    origin_action_types: List[ActionType] = Field(default_factory=list)
    source_team: Optional[TeamColor] = None
    source_ids: List[str] = Field(default_factory=list)
    scope: Optional[EffectScope] = None

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        def effect_matches(effect: ActiveEffect) -> bool:
            if self.effect_types and effect.effect_type not in self.effect_types:
                return False

            if (
                self.origin_action_types
                and effect.origin_action_type not in self.origin_action_types
            ):
                return False

            if self.source_ids and effect.source_id not in self.source_ids:
                return False

            if self.source_team:
                source_entity = state.get_entity(BoardEntityID(effect.source_id))
                if source_entity is None:
                    return False
                source_team_color = getattr(source_entity, "team", None)
                if source_team_color != self.source_team:
                    return False

            if self.scope:
                effect_origin = self._get_effect_origin(effect, state)
                scope_origin = self._get_scope_origin(state)
                if not effect_origin or not scope_origin:
                    return False
                if not self._hex_in_scope(effect_origin, scope_origin, state):
                    return False

            return True

        initial_count = len(state.active_effects)
        state.active_effects = [
            e for e in state.active_effects if not effect_matches(e)
        ]
        cancelled_count = initial_count - len(state.active_effects)

        if cancelled_count > 0:
            logger.debug(f"   [EFFECT] Cancelled {cancelled_count} active effect(s)")

        return StepResult(is_finished=True)

    def _get_effect_origin(
        self, effect: ActiveEffect, state: GameState
    ) -> Optional["Hex"]:
        if effect.scope.origin_hex:
            return effect.scope.origin_hex
        origin_id = effect.scope.origin_id or effect.source_id
        return state.entity_locations.get(BoardEntityID(origin_id))

    def _get_scope_origin(self, state: GameState) -> Optional["Hex"]:
        if not self.scope:
            return None
        if self.scope.origin_hex:
            return self.scope.origin_hex
        if self.scope.origin_id:
            return state.entity_locations.get(BoardEntityID(self.scope.origin_id))
        return None

    def _hex_in_scope(self, hex: "Hex", origin: "Hex", state: GameState) -> bool:
        if not origin:
            return False
        if self.scope is None:
            return False

        # Use TopologyService for consolidated, topology-aware scope checking
        topology = get_topology_service()
        return topology.hex_in_scope(
            origin,
            hex,
            self.scope.shape,
            self.scope.range,
            state,
            self.scope.direction,
        )

    def _get_zone_for_hex(self, hex: "Hex", state: GameState) -> Optional[str]:
        for zone_id, zone in state.board.zones.items():
            if hex in zone.hexes:
                return zone_id
        return None


class CheckPassiveAbilitiesStep(GameStep):
    """
    Checks for passive abilities that trigger at the specified point.
    For each eligible passive, spawns an OfferPassiveStep.

    Scans two sources:
    1. Regular cards in played_cards (RESOLVED + face-up)
    2. Ultimate card (if hero.level >= 8)
    """

    type: StepType = StepType.CHECK_PASSIVE_ABILITIES
    trigger: str  # PassiveTrigger value as string for serialization
    hero_id: Optional[str] = (
        None  # Override which hero is scanned (default: current actor)
    )

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        from goa2.engine.effects import CardEffectRegistry
        from goa2.domain.models.enums import PassiveTrigger

        scan_id = self.hero_id or state.current_actor_id
        hero = state.get_hero(HeroID(str(scan_id))) if scan_id else None
        if not hero:
            return StepResult(is_finished=True)

        trigger_enum = PassiveTrigger(self.trigger)
        offer_steps: List[GameStep] = []

        def check_card_for_passive(card: Card) -> None:
            """Helper to check a card for matching passive ability."""
            if not card.current_effect_id:
                return

            effect = CardEffectRegistry.get(card.current_effect_id)
            if not effect:
                return

            config = effect.get_passive_config()
            if not config or config.trigger != trigger_enum:
                return

            # Check usage limit
            if config.uses_per_turn > 0:
                if card.passive_uses_this_turn >= config.uses_per_turn:
                    logger.debug(
                        f"   [PASSIVE] {card.name} already used {card.passive_uses_this_turn}/{config.uses_per_turn} times this turn"
                    )
                    return

            # Runtime predicate (e.g. Battle Fury filters on discard_source)
            if not effect.should_offer_passive(
                state, hero, card, trigger_enum, context
            ):
                return

            # Spawn offer step for this passive
            offer_steps.append(
                OfferPassiveStep(
                    card_id=card.id,
                    trigger=self.trigger,
                    is_optional=config.is_optional,
                    prompt=config.prompt or f"Use {card.name} passive ability?",
                    hero_id=str(hero.id) if self.hero_id else None,
                )
            )

        # 1. Check regular cards: must be RESOLVED and face-up
        for card in hero.played_cards:
            if card and card.state == CardState.RESOLVED and not card.is_facedown:
                check_card_for_passive(card)

        # 2. Check ultimate card: active if level >= 8
        if hero.level >= 8 and hero.ultimate_card:
            check_card_for_passive(hero.ultimate_card)

        if offer_steps:
            logger.debug(
                f"   [PASSIVE] Found {len(offer_steps)} passive(s) for trigger {trigger_enum.value}"
            )

        return StepResult(is_finished=True, new_steps=offer_steps)


class OfferPassiveStep(GameStep):
    """
    Offers player a choice to use an optional passive ability.
    If mandatory or accepted, spawns the passive steps.
    """

    type: StepType = StepType.OFFER_PASSIVE
    card_id: str
    trigger: str  # PassiveTrigger value as string
    is_optional: bool = True
    prompt: str = ""
    hero_id: Optional[str] = (
        None  # Override: whose passive this is (default: current actor)
    )

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        from goa2.engine.effects import CardEffectRegistry
        from goa2.domain.models.enums import PassiveTrigger

        owner_id = self.hero_id or state.current_actor_id
        hero = state.get_hero(HeroID(str(owner_id))) if owner_id else None
        if not hero:
            return StepResult(is_finished=True)

        # Find the card (could be in played_cards or ultimate_card)
        card = next((c for c in hero.played_cards if c and c.id == self.card_id), None)
        if not card and hero.ultimate_card and hero.ultimate_card.id == self.card_id:
            card = hero.ultimate_card

        if not card:
            logger.debug(f"   [PASSIVE] Card {self.card_id} not found")
            return StepResult(is_finished=True)

        if card.current_effect_id is None:
            return StepResult(is_finished=True)

        effect = CardEffectRegistry.get(card.current_effect_id)
        if not effect:
            return StepResult(is_finished=True)

        trigger_enum = PassiveTrigger(self.trigger)

        def execute_passive() -> StepResult:
            """Helper to spawn the passive steps and mark used."""
            passive_steps = effect.get_passive_steps(
                state, hero, card, trigger_enum, context
            )
            if passive_steps:
                logger.debug(
                    f"   [PASSIVE] Activating {card.name}: {len(passive_steps)} step(s)"
                )
                # Add MarkPassiveUsedStep after the passive steps
                return StepResult(
                    is_finished=True,
                    new_steps=passive_steps
                    + [MarkPassiveUsedStep(card_id=self.card_id)],
                )
            return StepResult(is_finished=True)

        # If not optional, auto-execute
        if not self.is_optional:
            return execute_passive()

        # Handle player input for optional passives
        if self.pending_input:
            choice = self.pending_input.get("selection")
            if choice == "YES":
                return execute_passive()
            else:  # "NO" or "SKIP"
                logger.debug(f"   [PASSIVE] Player declined {card.name} passive")
                return StepResult(is_finished=True)

        # Request input from player
        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.CONFIRM_PASSIVE,
                player_id=str(hero.id),
                prompt=self.prompt,
                options=[
                    InputOption(id="YES", text="Yes"),
                    InputOption(id="NO", text="No"),
                ],
                card_id=self.card_id,
                card_name=card.name,
            ),
        )


class MarkPassiveUsedStep(GameStep):
    """Marks a passive ability as used for this turn."""

    type: StepType = StepType.MARK_PASSIVE_USED
    card_id: str

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        hero = state.get_hero(HeroID(str(state.current_actor_id)))
        if not hero:
            return StepResult(is_finished=True)

        # Find the card (could be in played_cards or ultimate_card)
        card = next((c for c in hero.played_cards if c and c.id == self.card_id), None)
        if not card and hero.ultimate_card and hero.ultimate_card.id == self.card_id:
            card = hero.ultimate_card

        if card:
            card.passive_uses_this_turn += 1
            logger.debug(
                f"   [PASSIVE] {card.name} used ({card.passive_uses_this_turn} time(s) this turn)"
            )

        return StepResult(is_finished=True)


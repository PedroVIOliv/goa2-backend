from __future__ import annotations
from abc import ABC
from typing import Optional, Dict, Any, List, Tuple, Sequence, cast
import copy
from pydantic import BaseModel, Field

from goa2.domain.state import GameState
from goa2.domain.types import UnitID, HeroID, BoardEntityID
from goa2.domain.models import (
    ActionType,
    Card,
    TeamColor,
    CardTier,
    CardColor,
    CardState,
    GamePhase,
    StepType,
    TargetType,
    CardContainerType,
)
from goa2.domain.models.effect import (
    DurationType,
    EffectType,
    EffectScope,
    Shape,
    ActiveEffect,
)
from goa2.domain.models.marker import MarkerType
from goa2.domain.hex import Hex
from goa2.engine import rules  # For validation
from goa2.engine.stats import get_computed_stat  # For stat calculation

from goa2.domain.models.enums import StatType
from goa2.engine.effect_manager import EffectManager

# -----------------------------------------------------------------------------
# Base Classes
# -----------------------------------------------------------------------------


class StepResult(BaseModel):
    """Result of a step execution."""

    is_finished: bool = True
    requires_input: bool = False
    input_request: Optional[Dict[str, Any]] = None
    new_steps: Sequence["GameStep"] = Field(default_factory=list)  # Steps to spawn
    abort_action: bool = False  # If True, abort remaining steps in current action


class GameStep(BaseModel, ABC):
    """
    Base class for all atomic game operations.
    Each step performs a single logic unit and can manage its own state.
    """

    type: StepType = StepType.GENERIC

    # Unique ID for tracking this specific step instance (useful for input association)
    step_id: str = Field(default_factory=lambda: str(id(object())))

    # Input buffer: If the client provides input, it's stored here before 'resolve' is called
    pending_input: Optional[Any] = None

    # Mandatory step flag: Per GoA2 rules, mandatory steps that fail abort the action.
    # Optional steps ("you may", "up to", "if able") set this to False.
    is_mandatory: bool = True

    # Conditional Execution: If set, this step only runs if 'active_if_key' exists in context.
    active_if_key: Optional[str] = None

    def should_skip(self, context: Dict[str, Any]) -> bool:
        """Checks if the step should be skipped based on active_if_key."""
        if self.active_if_key:
            val = context.get(self.active_if_key)
            # Skip if key is missing or None (falsy is tricky, but usually checking existence/non-None is safer)
            if val is None:
                return True
        return False

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        """
        Executes the step.
        :param state: Global GameState.
        :param context: Shared transient memory for the current Action chain.
        :return: StepResult indicating if we are done or need input.
        """
        raise NotImplementedError


# -----------------------------------------------------------------------------
# Common Steps
# -----------------------------------------------------------------------------


class CreateEffectStep(GameStep):
    """Creates a spatial ActiveEffect in the game state."""

    type: StepType = StepType.CREATE_EFFECT

    effect_type: EffectType
    scope: EffectScope
    duration: DurationType = DurationType.THIS_TURN

    restrictions: List[ActionType] = Field(default_factory=list)
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

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        # Resolve source card ID
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

        EffectManager.create_effect(
            state=state,
            source_id=str(state.current_actor_id)
            if state.current_actor_id
            else "system",
            source_card_id=card_id,
            effect_type=self.effect_type,
            scope=self.scope,
            duration=self.duration,
            restrictions=self.restrictions,
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
        )

        print(
            f"   [EFFECT] Created {self.effect_type.value} from {state.current_actor_id}"
        )

        return StepResult(is_finished=True)


class PlaceMarkerStep(GameStep):
    """
    Places a marker on a target hero.

    Markers are singletons - placing on a new target automatically removes
    from the previous target. The marker's effects are applied via
    get_computed_stat() which reads markers directly.

    Usage:
        PlaceMarkerStep(
            marker_type=MarkerType.VENOM,
            target_key="victim_id",
            value=-1,
        )
    """

    type: StepType = StepType.GENERIC
    marker_type: MarkerType
    target_id: Optional[str] = None  # Direct target ID
    target_key: Optional[str] = None  # Context key for target ID
    value: int = 0  # Effect magnitude (e.g., -1 or -2 for Venom)

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        # Resolve target
        target = self.target_id
        if not target and self.target_key:
            target = context.get(self.target_key)

        if not target:
            print(f"   [SKIP] No target for PlaceMarkerStep ({self.marker_type.value})")
            return StepResult(is_finished=True)

        # Get source (current actor)
        source_id = str(state.current_actor_id) if state.current_actor_id else "system"

        # Place the marker
        marker = state.place_marker(
            marker_type=self.marker_type,
            target_id=target,
            value=self.value,
            source_id=source_id,
        )

        print(
            f"   [MARKER] Placed {self.marker_type.value} on {target} "
            f"(value={self.value}, source={source_id})"
        )

        return StepResult(is_finished=True)


class RemoveMarkerStep(GameStep):
    """
    Removes a marker, returning it to supply.

    Usage:
        RemoveMarkerStep(marker_type=MarkerType.VENOM)
    """

    type: StepType = StepType.GENERIC
    marker_type: MarkerType

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        marker = state.remove_marker(self.marker_type)

        if marker:
            print(f"   [MARKER] Removed {self.marker_type.value} from play")
        else:
            print(f"   [MARKER] {self.marker_type.value} not in play")

        return StepResult(is_finished=True)


class LogMessageStep(GameStep):
    """Debugging step to print messages."""

    type: StepType = StepType.LOG_MESSAGE
    message: str

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        # Interpolate context variables
        msg = self.message.format(**context)
        print(f"   [STEP] {msg}")
        return StepResult(is_finished=True)


class SetContextFlagStep(GameStep):
    """
    Utility step that sets a flag/value in the execution context.

    Used by defense effects to communicate with combat resolution:
    - auto_block: Block succeeds regardless of values (e.g., stop_projectiles)
    - defense_invalid: Defense fails entirely (e.g., stop_projectiles vs melee)
    - ignore_minion_defense: Skip minion modifier calculation (e.g., aspiring_duelist)
    """

    type: StepType = StepType.SET_CONTEXT_FLAG
    key: str
    value: Any = True

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        context[self.key] = self.value
        print(f"   [CONTEXT] Set {self.key} = {self.value}")
        return StepResult(is_finished=True)


class RestoreActionTypeStep(GameStep):
    """
    Restores the previous action type from the stack after defense resolution.

    Used after defense effects complete to restore the original action type
    (e.g., ATTACK) so that any subsequent effects are correctly attributed.
    """

    type: StepType = StepType.RESTORE_ACTION_TYPE

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        stack = context.get("action_type_stack", [])
        if stack:
            previous_type = stack.pop()
            context["current_action_type"] = previous_type
            print(f"   [CONTEXT] Restored action type to {previous_type.name}")
        return StepResult(is_finished=True)


# -----------------------------------------------------------------------------
# Passive Ability Steps
# -----------------------------------------------------------------------------


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

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        from goa2.engine.effects import CardEffectRegistry
        from goa2.domain.models.enums import PassiveTrigger

        hero = state.get_hero(HeroID(str(state.current_actor_id)))
        if not hero:
            return StepResult(is_finished=True)

        trigger_enum = PassiveTrigger(self.trigger)
        offer_steps: List[GameStep] = []

        def check_card_for_passive(card: Card) -> None:
            """Helper to check a card for matching passive ability."""
            if not card.effect_id:
                return

            effect = CardEffectRegistry.get(card.effect_id)
            if not effect:
                return

            config = effect.get_passive_config()
            if not config or config.trigger != trigger_enum:
                return

            # Check usage limit
            if config.uses_per_turn > 0:
                if card.passive_uses_this_turn >= config.uses_per_turn:
                    print(
                        f"   [PASSIVE] {card.name} already used {card.passive_uses_this_turn}/{config.uses_per_turn} times this turn"
                    )
                    return

            # Spawn offer step for this passive
            offer_steps.append(
                OfferPassiveStep(
                    card_id=card.id,
                    trigger=self.trigger,
                    is_optional=config.is_optional,
                    prompt=config.prompt or f"Use {card.name} passive ability?",
                )
            )

        # 1. Check regular cards: must be RESOLVED and face-up
        for card in hero.played_cards:
            if card.state == CardState.RESOLVED and not card.is_facedown:
                check_card_for_passive(card)

        # 2. Check ultimate card: active if level >= 8
        if hero.level >= 8 and hero.ultimate_card:
            check_card_for_passive(hero.ultimate_card)

        if offer_steps:
            print(
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

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        from goa2.engine.effects import CardEffectRegistry
        from goa2.domain.models.enums import PassiveTrigger

        hero = state.get_hero(HeroID(str(state.current_actor_id)))
        if not hero:
            return StepResult(is_finished=True)

        # Find the card (could be in played_cards or ultimate_card)
        card = next((c for c in hero.played_cards if c.id == self.card_id), None)
        if not card and hero.ultimate_card and hero.ultimate_card.id == self.card_id:
            card = hero.ultimate_card

        if not card:
            print(f"   [PASSIVE] Card {self.card_id} not found")
            return StepResult(is_finished=True)

        effect = CardEffectRegistry.get(card.effect_id)
        if not effect:
            return StepResult(is_finished=True)

        trigger_enum = PassiveTrigger(self.trigger)

        def execute_passive() -> StepResult:
            """Helper to spawn the passive steps and mark used."""
            passive_steps = effect.get_passive_steps(
                state, hero, card, trigger_enum, context
            )
            if passive_steps:
                print(
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
            choice = self.pending_input.get("choice")
            if choice == "YES":
                return execute_passive()
            else:  # "NO" or "SKIP"
                print(f"   [PASSIVE] Player declined {card.name} passive")
                return StepResult(is_finished=True)

        # Request input from player
        return StepResult(
            requires_input=True,
            input_request={
                "type": "CONFIRM_PASSIVE",
                "prompt": self.prompt,
                "player_id": state.current_actor_id,
                "card_id": self.card_id,
                "card_name": card.name,
                "options": ["YES", "NO"],
            },
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
        card = next((c for c in hero.played_cards if c.id == self.card_id), None)
        if not card and hero.ultimate_card and hero.ultimate_card.id == self.card_id:
            card = hero.ultimate_card

        if card:
            card.passive_uses_this_turn += 1
            print(
                f"   [PASSIVE] {card.name} used ({card.passive_uses_this_turn} time(s) this turn)"
            )

        return StepResult(is_finished=True)


from goa2.engine.filters import FilterCondition


class SelectStep(GameStep):
    """
    Unified selection step using the Filter System.
    Replaces SelectTargetStep and SelectHexStep.

    Supports target types: "UNIT", "HEX", "CARD", "NUMBER"
    For NUMBER type, use number_options to specify valid choices.

    Note: For UNIT selections, ImmunityFilter is automatically applied unless
    skip_immunity_filter=True is set.
    """

    type: StepType = StepType.SELECT
    target_type: TargetType  # "UNIT", "HEX", "CARD", "NUMBER"
    prompt: str
    output_key: str = "selection"
    filters: List[FilterCondition] = Field(default_factory=list)
    auto_select_if_one: bool = False
    context_hero_id_key: Optional[str] = (
        None  # Key in context to find hero (for CARD/HAND selection)
    )
    card_container: CardContainerType = (
        CardContainerType.HAND
    )  # "HAND", "PLAYED", "DISCARD", "DECK"
    number_options: List[int] = Field(default_factory=list)  # For NUMBER target type
    skip_immunity_filter: bool = False  # Set True to disable automatic ImmunityFilter
    override_player_id_key: Optional[str] = (
        None  # Key in context to find player ID who provides input
    )

    def _get_effective_filters(self) -> List[FilterCondition]:
        """
        Returns the effective filter list, adding ImmunityFilter for UNIT selections
        unless skip_immunity_filter is True or ImmunityFilter is already present.
        """
        from goa2.engine.filters import ImmunityFilter

        effective = list(self.filters)

        # Auto-add ImmunityFilter for UNIT selections
        if self.target_type == TargetType.UNIT and not self.skip_immunity_filter:
            # Check if ImmunityFilter is already in the list
            has_immunity = any(isinstance(f, ImmunityFilter) for f in effective)
            if not has_immunity:
                effective.append(ImmunityFilter())

        return effective

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            print(
                f"   [SKIP] Conditional Step '{self.prompt}' skipped (Key '{self.active_if_key}' missing)."
            )
            return StepResult(is_finished=True)

        actor_id = state.current_actor_id
        if self.override_player_id_key:
            found = context.get(self.override_player_id_key)
            if found:
                actor_id = HeroID(str(found))

        candidates: List[Any] = []
        if self.target_type == TargetType.UNIT:
            # Filter entity_locations for things that are actually Units
            all_entities = list(state.entity_locations.keys())
            candidates = [
                eid for eid in all_entities if state.get_unit(UnitID(str(eid)))
            ]
        elif self.target_type == TargetType.HEX:
            # Optimization: If there is a RangeFilter, use it to narrow search area
            # For now, simplistic iteration over all tiles
            candidates = list(state.board.tiles.keys())
        elif self.target_type == TargetType.NUMBER:
            # Use number_options directly as candidates
            candidates = list(self.number_options)
        elif self.target_type == TargetType.CARD:
            target_id = actor_id
            if self.context_hero_id_key:
                found_id = context.get(self.context_hero_id_key)
                if found_id:
                    target_id = HeroID(str(found_id))

            hero = state.get_hero(HeroID(str(target_id)))
            if hero:
                source_list = []
                if self.card_container == CardContainerType.HAND:
                    source_list = hero.hand
                elif self.card_container == CardContainerType.PLAYED:
                    source_list = hero.played_cards
                elif self.card_container == CardContainerType.DISCARD:
                    source_list = hero.discard_pile
                elif self.card_container == CardContainerType.DECK:
                    source_list = hero.deck

                candidates = [c.id for c in source_list]

        valid_candidates = []
        effective_filters = self._get_effective_filters()
        for c in candidates:
            # Intrinsic Validation for UNITS: Check can_be_targeted (LOS, etc.)
            if self.target_type == TargetType.UNIT and actor_id:
                val_res = state.validator.can_be_targeted(
                    state, str(actor_id), str(c), context
                )
                if not val_res.allowed:
                    continue

            is_valid = True
            for f in effective_filters:
                if not f.apply(c, state, context):
                    is_valid = False
                    break
            if is_valid:
                valid_candidates.append(c)

        if not valid_candidates:
            if self.is_mandatory:
                print(
                    f"   [ABORT] Mandatory selection '{self.prompt}' failed. No candidates."
                )
                return StepResult(is_finished=True, abort_action=True)
            else:
                print(
                    f"   [SKIP] Optional selection '{self.prompt}' skipped. No candidates."
                )
                return StepResult(is_finished=True)

        if self.auto_select_if_one and len(valid_candidates) == 1 and self.is_mandatory:
            choice = valid_candidates[0]
            context[self.output_key] = choice
            print(f"   [AUTO] Only one valid option: {choice}. Selected automatically.")
            return StepResult(is_finished=True)

        if self.pending_input:
            selection = self.pending_input.get("selection")

            if selection == "SKIP" and not self.is_mandatory:
                print("   [SKIP] Player chose to skip optional selection.")
                return StepResult(is_finished=True)

            # Type Conversion for Hex
            if self.target_type == TargetType.HEX and isinstance(selection, dict):
                selection = Hex(**selection)

            # Type Conversion for NUMBER (ensure int comparison)
            if self.target_type == TargetType.NUMBER and selection is not None:
                selection = int(selection)

            if selection in valid_candidates:
                context[self.output_key] = selection
                print(f"   [INPUT] Player {actor_id} selected {selection}")
                return StepResult(is_finished=True)
            else:
                # Invalid choice, re-request
                pass

        return StepResult(
            requires_input=True,
            input_request={
                "type": f"SELECT_{self.target_type.value}",
                "prompt": self.prompt,
                "player_id": actor_id,
                "valid_options": valid_candidates,
                "can_skip": not self.is_mandatory,
            },
        )


class DrawCardStep(GameStep):
    type: StepType = StepType.DRAW_CARD
    hero_id: str
    amount: int = 1

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        print(f"   [LOGIC] {self.hero_id} draws {self.amount} card(s).")
        return StepResult(is_finished=True)


# -----------------------------------------------------------------------------
# Complex Primitives (Move, Attack, Reaction)
# -----------------------------------------------------------------------------


class DiscardCardStep(GameStep):
    """
    Forces a specific card to be discarded.
    """

    type: StepType = StepType.GENERIC
    card_id: Optional[str] = None
    card_key: Optional[str] = None
    hero_id: Optional[str] = None
    hero_key: Optional[str] = None

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        # Resolve Hero
        h_id = self.hero_id
        if not h_id and self.hero_key:
            h_id = context.get(self.hero_key)

        if not h_id:
            return StepResult(is_finished=True)

        hero = state.get_hero(HeroID(str(h_id)))
        if not hero:
            return StepResult(is_finished=True)

        # Resolve Card
        c_id = self.card_id
        if not c_id and self.card_key:
            c_id = context.get(self.card_key)

        if not c_id:
            return StepResult(is_finished=True)

        # Find card object in hand
        target_card = next((c for c in hero.hand if c.id == c_id), None)
        if not target_card:
            print(f"   [DISCARD] Card {c_id} not found in {h_id}'s hand.")
            return StepResult(is_finished=True)

        print(f"   [DISCARD] {h_id} discards {target_card.name}")
        hero.discard_card(target_card, from_hand=True)
        return StepResult(is_finished=True)


class ForceDiscardStep(GameStep):
    """
    Checks if a victim has cards.
    If YES: Spawns a SelectStep (for victim to choose) + DiscardCardStep.
    If NO: Completes successfully (no penalty).
    """

    type: StepType = StepType.GENERIC
    victim_key: str

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        victim_id = context.get(self.victim_key)
        if not victim_id:
            return StepResult(is_finished=True)

        victim = state.get_hero(HeroID(str(victim_id)))
        if not victim:
            return StepResult(is_finished=True)

        if not victim.hand:
            print(f"   [EFFECT] {victim_id} has no cards to discard (Safe).")
            return StepResult(is_finished=True)

        # Has cards -> Force Discard
        return StepResult(
            is_finished=True,
            new_steps=[
                SelectStep(
                    target_type=TargetType.CARD,
                    prompt=f"{victim_id}, select a card to discard.",
                    output_key="card_to_discard",
                    card_container=CardContainerType.HAND,
                    context_hero_id_key=self.victim_key,  # Look at victim's hand
                    override_player_id_key=self.victim_key,  # Victim chooses
                    is_mandatory=True,
                ),
                DiscardCardStep(card_key="card_to_discard", hero_key=self.victim_key),
            ],
        )


class ForceDiscardOrDefeatStep(GameStep):
    """
    Checks if a victim has cards.
    If YES: Spawns a SelectStep (for victim to choose) + DiscardCardStep.
    If NO: Spawns DefeatUnitStep (the penalty for not discarding).
    """

    type: StepType = StepType.GENERIC
    victim_key: str

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        victim_id = context.get(self.victim_key)
        if not victim_id:
            return StepResult(is_finished=True)

        victim = state.get_hero(HeroID(str(victim_id)))
        if not victim:
            return StepResult(is_finished=True)

        if not victim.hand:
            print(f"   [EFFECT] {victim_id} has no cards to discard! DEFEATED!")
            return StepResult(
                is_finished=True, new_steps=[DefeatUnitStep(victim_id=str(victim_id))]
            )

        # Has cards -> Force Discard
        return StepResult(
            is_finished=True,
            new_steps=[
                SelectStep(
                    target_type=TargetType.CARD,
                    prompt=f"{victim_id}, select a card to discard (or be Defeated).",
                    output_key="card_to_discard",
                    card_container=CardContainerType.HAND,
                    context_hero_id_key=self.victim_key,  # Look at victim's hand
                    override_player_id_key=self.victim_key,  # Victim chooses
                    is_mandatory=True,
                ),
                DiscardCardStep(card_key="card_to_discard", hero_key=self.victim_key),
            ],
        )


class MoveUnitStep(GameStep):
    """
    Moves the active unit (or specified unit) to a target hex.
    Includes Pathfinding validation if destination is selected.
    """

    type: StepType = StepType.MOVE_UNIT
    unit_id: Optional[str] = None  # If None, uses current_actor
    destination_key: str = "target_hex"  # Where to look in context for destination
    range_val: int = 1
    is_movement_action: bool = False  # Flag: Is this a formal "Movement Action"?

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        actor_id = self.unit_id if self.unit_id else state.current_actor_id
        dest_val = context.get(self.destination_key)

        if not actor_id:
            print("   [ERROR] No actor for move.")
            return StepResult(is_finished=True)

        if not dest_val:
            print("   [ERROR] No destination for move.")
            return StepResult(is_finished=True)

        if isinstance(dest_val, dict):
            dest_hex = Hex(**dest_val)
        else:
            dest_hex = dest_val  # Assume it is already a Hex

        # Validation: Check Effects/Constraints
        # Pass is_movement_action to validator
        validation = state.validator.can_move(
            state,
            actor_id,
            self.range_val,
            context,
            is_movement_action=self.is_movement_action,
        )
        if not validation.allowed:
            print(f"   [BLOCKED] MoveUnitStep: {validation.reason}")
            if self.is_mandatory:
                return StepResult(is_finished=True, abort_action=True)
            return StepResult(is_finished=True)

        start_hex = state.entity_locations.get(BoardEntityID(actor_id))
        if not start_hex:
            print(f"   [ERROR] Unit {actor_id} has no location on board.")
            return StepResult(is_finished=True)

        if start_hex == dest_hex:
            is_valid = self.range_val >= 0
        else:
            is_valid = rules.validate_movement_path(
                board=state.board,
                start=start_hex,
                end=dest_hex,
                max_steps=self.range_val,
            )

        if not is_valid:
            # NOTE: This should rarely happen if SelectStep correctly filtered movement options.
            # Invalid path is an ERROR (wrong destination chosen), not an abort trigger.
            # Abort only happens at SelectStep when no valid options exist at all.
            print(
                f"   [ERROR] Invalid move for {actor_id} to {dest_hex}. Path blocked or out of range."
            )
            return StepResult(is_finished=True)

        print(
            f"   [LOGIC] Moving {actor_id} from {start_hex} to {dest_hex} (Range {self.range_val})"
        )
        state.move_unit(UnitID(actor_id), dest_hex)
        return StepResult(is_finished=True)


class MoveSequenceStep(GameStep):
    """
    Composite Step for Movement.
    Expands into: Select Destination Hex -> Move Unit.
    Should ONLY be used for Movement Actions (primary or secondary).
    For other movement purposes, use MoveUnitStep directly.
    """

    type: StepType = StepType.MOVE_SEQUENCE
    unit_id: Optional[str] = None
    range_val: int = 1
    destination_key: str = "target_hex"
    is_mandatory: bool = True

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        actor_id = self.unit_id or state.current_actor_id

        # If we already have the destination in context, just move
        if context.get(self.destination_key):
            return StepResult(
                is_finished=True,
                new_steps=[
                    MoveUnitStep(
                        unit_id=actor_id,
                        destination_key=self.destination_key,
                        range_val=self.range_val,
                        is_mandatory=self.is_mandatory,
                        is_movement_action=True,  # This IS a movement action
                    )
                ],
            )

        from goa2.engine.filters import OccupiedFilter, MovementPathFilter

        # Determine filters.
        # MovementPathFilter now always allows the current hex.
        # We add OccupiedFilter(is_occupied=False, exclude_id=actor_id)
        # to ensure other units block movement but the moving unit doesn't block itself.
        filters = [
            OccupiedFilter(is_occupied=False, exclude_id=actor_id),
            MovementPathFilter(range_val=self.range_val, unit_id=actor_id),
        ]

        # If range is 0, MovementPathFilter will only allow current hex.
        # OccupiedFilter will also allow it because of exclude_id.

        print(f"   [MACRO] Expanding Move Sequence (Range: {self.range_val})")

        return StepResult(
            is_finished=True,
            new_steps=[
                SelectStep(
                    target_type=TargetType.HEX,
                    prompt=f"Select Movement Destination (Range {self.range_val})",
                    output_key=self.destination_key,
                    filters=filters,
                    is_mandatory=self.is_mandatory,
                ),
                MoveUnitStep(
                    unit_id=actor_id,
                    destination_key=self.destination_key,
                    range_val=self.range_val,
                    is_mandatory=self.is_mandatory,
                    is_movement_action=True,  # This IS a movement action
                ),
            ],
        )


class FastTravelStep(GameStep):
    """
    DEPRECATED: Use FastTravelSequenceStep instead.
    Execution step for Fast Travel.
    """

    type: StepType = StepType.FAST_TRAVEL
    unit_id: Optional[str] = None
    destination_key: str = "target_hex"

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        print("   [WARNING] FastTravelStep is deprecated. Use FastTravelSequenceStep.")
        actor_id = self.unit_id or state.current_actor_id
        dest = context.get(self.destination_key)

        if not actor_id or not dest:
            return StepResult(is_finished=True)

        return StepResult(
            is_finished=True,
            new_steps=[PlaceUnitStep(unit_id=actor_id, target_hex_arg=dest)],
        )


class FastTravelSequenceStep(GameStep):
    """
    Composite Step for Fast Travel.
    Expands into: Select Destination Hex -> Place Unit.
    """

    type: StepType = StepType.FAST_TRAVEL_SEQUENCE
    unit_id: Optional[str] = None
    destination_key: str = "target_hex"

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        actor_id = self.unit_id or state.current_actor_id

        if context.get(self.destination_key):
            return StepResult(
                is_finished=True,
                new_steps=[
                    PlaceUnitStep(
                        unit_id=actor_id,
                        destination_key=self.destination_key,
                        is_mandatory=False,
                    )
                ],
            )

        from goa2.engine.filters import FastTravelDestinationFilter

        print("   [MACRO] Expanding Fast Travel Sequence")

        return StepResult(
            is_finished=True,
            new_steps=[
                SelectStep(
                    target_type=TargetType.HEX,
                    prompt="Select Fast Travel Destination",
                    output_key=self.destination_key,
                    filters=[FastTravelDestinationFilter(unit_id=actor_id)],
                    is_mandatory=False,
                ),
                PlaceUnitStep(
                    unit_id=actor_id,
                    destination_key=self.destination_key,
                    is_mandatory=False,
                ),
            ],
        )


class ReactionWindowStep(GameStep):
    """
    Gives a target player a chance to react (Play Defense Card).
    Validates that the chosen card actually HAS a Defense action.

    Stores in context for defense effect resolution:
    - defense_card_id: The card used for defense (or None if passed)
    - defender_id: The defending hero's ID
    - is_primary_defense: True if the card's primary action is DEFENSE
    """

    type: StepType = StepType.REACTION_WINDOW
    target_player_key: str = "target_id"  # The player being attacked

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        target_id = context.get(self.target_player_key)
        if not target_id:
            return StepResult(is_finished=True)  # Should not happen

        target_hero = state.get_hero(target_id)

        # Optimization: Minions/Non-Heroes cannot react.
        if not target_hero:
            print(f"   [REACTION] Target {target_id} is not a hero. Skipping reaction.")
            context["defense_value"] = 0
            context["defense_card_id"] = None
            context["defender_id"] = str(target_id)
            context["is_primary_defense"] = False
            return StepResult(is_finished=True)

        valid_defense_cards = []
        for card in target_hero.hand:
            if (
                card.primary_action == ActionType.DEFENSE
                or card.primary_action == ActionType.DEFENSE_SKILL
                or ActionType.DEFENSE in card.secondary_actions
            ):
                valid_defense_cards.append(card)

        valid_ids = [c.id for c in valid_defense_cards]

        if self.pending_input:
            card_id = self.pending_input.get("selected_card_id")

            # Case A: PASS
            if card_id == "PASS":
                print(f"   [REACTION] Player {target_id} Passed (No Defense).")
                context["defense_value"] = 0
                context["defense_card_id"] = None
                context["defender_id"] = str(target_id)
                context["is_primary_defense"] = False
                return StepResult(is_finished=True)

            # Case B: Selected Card
            if card_id:
                def_val = 0
                selected_card = next(
                    (c for c in valid_defense_cards if c.id == card_id), None
                )

                # Get Base Value
                if selected_card:
                    def_val = selected_card.get_base_stat_value(StatType.DEFENSE)
                elif not selected_card:
                    raise ValueError("Selected card is not a valid defense card.")

                # Compute Total Defense (Base + Items + Modifiers)
                total_def = get_computed_stat(
                    state, target_id, StatType.DEFENSE, def_val
                )

                # Determine if primary defense (triggers effect text)
                is_primary = selected_card.primary_action in (
                    ActionType.DEFENSE,
                    ActionType.DEFENSE_SKILL,
                )

                print(
                    f"   [REACTION] Player {target_id} defends with {card_id} "
                    f"(Value: {total_def} [Base: {def_val}], Primary: {is_primary})"
                )

                # Store context for defense effect resolution
                context["defense_value"] = total_def
                context["defense_card_id"] = card_id
                context["defender_id"] = str(target_id)
                context["is_primary_defense"] = is_primary

                # Save current action type to stack and set DEFENSE for effect tracking
                action_stack = context.setdefault("action_type_stack", [])
                current_action = context.get("current_action_type")
                if current_action:
                    action_stack.append(current_action)
                context["current_action_type"] = ActionType.DEFENSE

                return StepResult(is_finished=True)

        return StepResult(
            requires_input=True,
            input_request={
                "type": "SELECT_CARD_OR_PASS",
                "prompt": f"Player {target_id}, select a Defense card.",
                "player_id": target_id,
                "options": valid_ids + ["PASS"],
            },
        )


class ResolveDefenseTextStep(GameStep):
    """
    Resolves defense card effect text for primary DEFENSE cards.
    Analogous to ResolveCardTextStep for offense.

    Only triggers for cards where primary_action == DEFENSE.
    For DEFENSE_SKILL cards, falls back to get_steps() if get_defense_steps() returns None.
    """

    type: StepType = StepType.RESOLVE_DEFENSE_TEXT

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        card_id = context.get("defense_card_id")
        defender_id = context.get("defender_id")
        is_primary = context.get("is_primary_defense", False)

        # Only trigger effects for primary DEFENSE
        if not card_id or not is_primary or not defender_id:
            print("   [DEFENSE] No primary defense card - skipping effect resolution.")
            return StepResult(is_finished=True)

        defender = state.get_hero(HeroID(str(defender_id)))
        if not defender:
            return StepResult(is_finished=True)

        # Find the card in defender's hand
        card = next((c for c in defender.hand if c.id == card_id), None)

        if not card or not card.effect_id:
            print(
                f"   [DEFENSE] Card {card_id} has no effect_id - using standard defense."
            )
            return StepResult(is_finished=True)

        from goa2.engine.effects import CardEffectRegistry

        effect = CardEffectRegistry.get(card.effect_id)
        if effect:
            # Try defense-specific steps first
            defense_steps = effect.get_defense_steps(state, defender, card, context)

            # If None, fall back to get_steps() (for DEFENSE_SKILL cards)
            if defense_steps is None:
                print(f"   [DEFENSE] Using get_steps() fallback for {card.effect_id}")
                defense_steps = effect.get_steps(state, defender, card)

            if defense_steps:
                print(
                    f"   [DEFENSE] Executing {len(defense_steps)} defense effect steps for {card.effect_id}"
                )
                return StepResult(is_finished=True, new_steps=defense_steps)

        return StepResult(is_finished=True)


class ResolveOnBlockEffectStep(GameStep):
    """
    Runs 'if you do' effects after a successful block.
    Only called if the defense succeeded (block_succeeded=True in context).

    Example: Wasp's Reflect Projectiles - "if you do, enemy hero discards"
    """

    type: StepType = StepType.RESOLVE_ON_BLOCK_EFFECT

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if not context.get("block_succeeded"):
            print("   [ON_BLOCK] Block did not succeed - skipping on_block effects.")
            return StepResult(is_finished=True)

        card_id = context.get("defense_card_id")
        defender_id = context.get("defender_id")
        is_primary = context.get("is_primary_defense", False)

        if not card_id or not is_primary or not defender_id:
            return StepResult(is_finished=True)

        defender = state.get_hero(HeroID(str(defender_id)))
        if not defender:
            return StepResult(is_finished=True)

        # Card may have been discarded, check hand first then discard pile
        card = next((c for c in defender.hand if c.id == card_id), None)
        if not card:
            card = next((c for c in defender.discard_pile if c.id == card_id), None)

        if not card or not card.effect_id:
            return StepResult(is_finished=True)

        from goa2.engine.effects import CardEffectRegistry

        effect = CardEffectRegistry.get(card.effect_id)
        if effect:
            on_block_steps = effect.get_on_block_steps(state, defender, card, context)
            if on_block_steps:
                print(
                    f"   [ON_BLOCK] Executing {len(on_block_steps)} on_block effect steps for {card.effect_id}"
                )
                return StepResult(is_finished=True, new_steps=on_block_steps)

        return StepResult(is_finished=True)


class RemoveUnitStep(GameStep):
    """
    Purely removes a unit from the board.
    Does NOT grant rewards. Used by 'Remove' effects and as a sub-step of Defeat.
    """

    type: StepType = StepType.REMOVE_UNIT
    unit_id: str

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        print(f"   [LOGIC] Removing {self.unit_id} from board.")
        state.remove_unit(UnitID(self.unit_id))
        return StepResult(is_finished=True)


class DefeatUnitStep(GameStep):
    """
    Processes the defeat of a unit (Combat/Skill Kill):
    1. Awards Gold (Killer + Assists).
    2. Updates Life Counters (if Hero).
    3. Returns markers from/to the defeated unit.
    4. Spawns RemoveUnitStep.
    """

    type: StepType = StepType.DEFEAT_UNIT
    victim_id: str
    killer_id: Optional[str] = None

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        print(f"   [DEATH] Processing Defeat of {self.victim_id}...")

        victim = state.get_unit(UnitID(self.victim_id))
        if not victim:
            raise ValueError(f"Cannot defeat unknown unit: {self.victim_id}")

        killer = state.get_unit(UnitID(self.killer_id)) if self.killer_id else None

        # Return markers from the defeated hero
        markers_from = state.return_markers_from_hero(self.victim_id)
        if markers_from:
            print(
                f"   [DEATH] Returned {len(markers_from)} marker(s) from defeated {self.victim_id}"
            )

        # Return markers placed by the defeated hero
        markers_by = state.return_markers_by_source(self.victim_id)
        if markers_by:
            print(
                f"   [DEATH] Returned {len(markers_by)} marker(s) placed by defeated {self.victim_id}"
            )

        if hasattr(victim, "level"):  # Is Hero
            level = getattr(victim, "level", 1)

            # Level: (Kill Reward, Assist Reward, Death Penalty)
            rewards_table = {
                1: (1, 1, 1),
                2: (2, 1, 1),
                3: (3, 1, 1),
                4: (4, 2, 2),
                5: (5, 2, 2),
                6: (6, 2, 2),
                7: (7, 3, 3),
                8: (8, 3, 3),
            }
            kill_gold, assist_gold, penalty_counters = rewards_table.get(
                level, (level, 1, 1)
            )

            if killer and hasattr(killer, "gold"):
                killer.gold += kill_gold
                print(f"   [ECONOMY] Killer {killer.id} gains {kill_gold} Gold.")

            if killer and hasattr(killer, "team"):
                killer_team_color = getattr(killer, "team", None)
                if killer_team_color and killer_team_color in state.teams:
                    killer_team = state.teams[killer_team_color]
                    if killer_team:
                        for ally in killer_team.heroes:
                            if ally.id != killer.id:
                                ally.gold += assist_gold
                                print(
                                    f"   [ECONOMY] Assist: {ally.id} gains {assist_gold} Gold."
                                )

            if hasattr(victim, "team"):
                victim_team_color = getattr(victim, "team", None)
                if victim_team_color and victim_team_color in state.teams:
                    victim_team = state.teams[victim_team_color]
                    if victim_team:
                        victim_team.life_counters = max(
                            0, victim_team.life_counters - penalty_counters
                        )
                        print(
                            f"   [SCORE] Team {victim_team_color.name} loses {penalty_counters} Life Counter(s). Remaining: {victim_team.life_counters}"
                        )

                        if victim_team.life_counters == 0:
                            print(
                                f"   [GAME OVER] Team {victim_team_color.name} has 0 Life Counters! ANNIHILATION."
                            )
                            winning_team = (
                                TeamColor.BLUE
                                if victim_team_color == TeamColor.RED
                                else TeamColor.RED
                            )
                            return StepResult(
                                is_finished=True,
                                new_steps=[
                                    RemoveUnitStep(unit_id=self.victim_id),
                                    TriggerGameOverStep(
                                        winner=winning_team, condition="ANNIHILATION"
                                    ),
                                ],
                            )

        elif hasattr(victim, "value"):  # Is Minion
            reward = victim.value
            print(f"   [DEATH] Minion Defeated! Killer gains {reward} Gold.")
            if killer and hasattr(killer, "gold"):
                killer.gold += reward

        # Execution Order: RemoveUnitStep -> CheckLanePushStep
        return StepResult(
            is_finished=True,
            new_steps=[RemoveUnitStep(unit_id=self.victim_id), CheckLanePushStep()],
        )


class FindNextActorStep(GameStep):
    """
    Triggers the Phase engine to identify the next active player.
    Used to chain turns together.
    """

    type: StepType = StepType.FIND_NEXT_ACTOR

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        # Import internally to avoid circular dependency (steps <-> phases)
        from goa2.engine.phases import resolve_next_action

        print("   [LOOP] Finding next actor...")
        resolve_next_action(state)
        return StepResult(is_finished=True)


class ResolveCombatStep(GameStep):
    """
    Compares Attack vs Defense and applies results.

    Checks context flags from defense effects:
    - defense_invalid: Defense fails entirely (e.g., stop_projectiles vs melee)
    - auto_block: Block succeeds regardless of values (e.g., stop_projectiles vs ranged)
    - ignore_minion_defense: Skip minion modifier calculation (e.g., aspiring_duelist)

    Sets context flag for on_block effects:
    - block_succeeded: True if the attack was blocked
    """

    type: StepType = StepType.RESOLVE_COMBAT
    damage: int  # Base attack value from the card
    target_key: str = "victim_id"

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        target_id = context.get(self.target_key)
        if not target_id:
            print("   [COMBAT] No target selected. Combat cancelled.")
            context["block_succeeded"] = False
            return StepResult(is_finished=True)

        defense_card_val = context.get("defense_value", 0)
        attack_val = self.damage
        actor_id = state.current_actor_id

        # Check for defense_invalid (e.g., stop_projectiles vs melee attack)
        if context.get("defense_invalid"):
            print(
                "   [COMBAT] Defense is invalid (conditions not met) - treating as no defense."
            )
            context["block_succeeded"] = False
            return StepResult(
                is_finished=True,
                new_steps=[DefeatUnitStep(victim_id=target_id, killer_id=actor_id)],
            )

        # Check for auto_block (e.g., stop_projectiles vs ranged attack)
        if context.get("auto_block"):
            print(f"   [COMBAT] Auto-block triggered! {target_id} is safe.")
            context["block_succeeded"] = True
            return StepResult(is_finished=True)

        # Calculate Passive Modifiers (unless ignored by defense effect)
        from goa2.engine.stats import calculate_minion_defense_modifier

        if context.get("ignore_minion_defense"):
            mod_val = 0
            print("   [COMBAT] Ignoring minion defense modifiers (effect active).")
        else:
            mod_val = calculate_minion_defense_modifier(state, target_id)

        total_defense = defense_card_val + mod_val

        print(
            f"   [COMBAT] Attack ({attack_val}) vs Defense ({defense_card_val} Card + {mod_val} Mod = {total_defense})"
        )

        if total_defense >= attack_val:
            print(f"   [RESULT] Attack BLOCKED! {target_id} is safe.")
            context["block_succeeded"] = True
            return StepResult(is_finished=True)
        else:
            print(f"   [RESULT] Attack HITS! {target_id} is DEFEATED!")
            context["block_succeeded"] = False
            return StepResult(
                is_finished=True,
                new_steps=[DefeatUnitStep(victim_id=target_id, killer_id=actor_id)],
            )


class FinalizeHeroTurnStep(GameStep):
    """
    Finalizes a hero's turn by moving their current card to the resolved dashboard.
    Activates any effects created by this card and clears the actor context.
    """

    type: StepType = StepType.FINALIZE_HERO_TURN
    hero_id: str

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        hero = state.get_hero(HeroID(self.hero_id))
        if hero and hero.current_turn_card:
            card_id = hero.current_turn_card.id
            print(
                f"   [LOGIC] Finalizing turn for {self.hero_id}. Card moved to Resolved."
            )
            hero.resolve_current_card()

            # Activate all effects created by this card
            EffectManager.activate_effects_by_card(state, card_id)

        # Reset passive usage counters for all cards (they reset each turn)
        if hero:
            for card in hero.played_cards:
                if card.passive_uses_this_turn > 0:
                    card.passive_uses_this_turn = 0
            # Also reset ultimate card if present
            if hero.ultimate_card and hero.ultimate_card.passive_uses_this_turn > 0:
                hero.ultimate_card.passive_uses_this_turn = 0

        # Clear transient context for the next actor
        context.clear()
        state.current_actor_id = None

        return StepResult(is_finished=True, new_steps=[FindNextActorStep()])


class PlaceUnitStep(GameStep):
    """
    Moves a unit to a target hex directly.
    No pathfinding validation. Used for respawns, swaps, and forced placements.
    """

    type: StepType = StepType.PLACE_UNIT
    unit_id: Optional[str] = None  # If None, checks unit_key, then current_actor
    unit_key: Optional[str] = None  # Look up unit_id in context
    destination_key: str = "target_hex"  # Where to look in context
    target_hex_arg: Optional[Hex] = None  # Explicit argument

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        # Resolve target unit (unit being placed)
        target_unit_id = self.unit_id
        if not target_unit_id and self.unit_key:
            target_unit_id = context.get(self.unit_key)

        if not target_unit_id:
            target_unit_id = state.current_actor_id

        # Priority: explicit arg -> context
        dest_val = self.target_hex_arg
        if not dest_val:
            dest_val = context.get(self.destination_key)

        if not target_unit_id:
            print("   [ERROR] No unit for place.")
            return StepResult(is_finished=True)

        if not dest_val:
            print("   [ERROR] No destination for place.")
            return StepResult(is_finished=True)

        if isinstance(dest_val, dict):
            dest_hex = Hex(**dest_val)
        else:
            dest_hex = dest_val  # Assume it is already a Hex

        # Validation: Check Occupancy (allow if occupied by self)
        tile = state.board.get_tile(dest_hex)
        if tile and tile.is_occupied and str(tile.occupant_id) != target_unit_id:
            print(
                f"   [ERROR] Cannot place {target_unit_id} at {dest_hex}. Tile is occupied."
            )
            return StepResult(is_finished=True)

        # Validation: Check Effects/Constraints
        # actor_id is the entity CAUSING the placement (current_actor)
        actor_id = state.current_actor_id or target_unit_id

        validation = state.validator.can_be_placed(
            state=state,
            unit_id=str(target_unit_id),
            actor_id=str(actor_id),
            destination=dest_hex,
            context=context,
        )

        if not validation.allowed:
            print(f"   [BLOCKED] PlaceUnitStep: {validation.reason}")
            if self.is_mandatory:
                return StepResult(is_finished=True, abort_action=True)
            return StepResult(is_finished=True)

        print(f"   [LOGIC] Placing {target_unit_id} at {dest_hex}")
        state.move_unit(UnitID(str(target_unit_id)), dest_hex)
        return StepResult(is_finished=True)


class SwapUnitsStep(GameStep):
    """
    Swaps the positions of two units.
    Updates the board state directly.

    Supports two modes:
    - Direct: Provide unit_a_id and unit_b_id directly
    - Context: Provide unit_a_key and/or unit_b_key to read from context
    """

    type: StepType = StepType.SWAP_UNITS
    unit_a_id: Optional[str] = None
    unit_b_id: Optional[str] = None
    unit_a_key: Optional[str] = None  # Read unit_a from context
    unit_b_key: Optional[str] = None  # Read unit_b from context

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        # Resolve unit IDs from either direct or context
        actual_unit_a = self.unit_a_id
        if not actual_unit_a and self.unit_a_key:
            actual_unit_a = context.get(self.unit_a_key)

        actual_unit_b = self.unit_b_id
        if not actual_unit_b and self.unit_b_key:
            actual_unit_b = context.get(self.unit_b_key)

        if not actual_unit_a or not actual_unit_b:
            print("   [SKIP] SwapUnitsStep: Missing unit ID(s).")
            return StepResult(is_finished=True)

        # Get current locations from Unified Dict
        loc_a = state.entity_locations.get(BoardEntityID(actual_unit_a))
        loc_b = state.entity_locations.get(BoardEntityID(actual_unit_b))

        if not loc_a or not loc_b:
            print(
                f"   [ERROR] Cannot swap {actual_unit_a} and {actual_unit_b}. One is not on board."
            )
            return StepResult(is_finished=True)

        # Validation
        actor_id = state.current_actor_id
        res_a = state.validator.can_be_swapped(
            state, actual_unit_a, str(actor_id) if actor_id else "system", context
        )
        if not res_a.allowed:
            print(f"   [BLOCKED] Swap prevented for {actual_unit_a}: {res_a.reason}")
            if self.is_mandatory:
                return StepResult(is_finished=True, abort_action=True)
            return StepResult(is_finished=True)

        res_b = state.validator.can_be_swapped(
            state, actual_unit_b, str(actor_id) if actor_id else "system", context
        )
        if not res_b.allowed:
            print(f"   [BLOCKED] Swap prevented for {actual_unit_b}: {res_b.reason}")
            if self.is_mandatory:
                return StepResult(is_finished=True, abort_action=True)
            return StepResult(is_finished=True)

        print(
            f"   [LOGIC] Swapping {actual_unit_a} ({loc_a}) <-> {actual_unit_b} ({loc_b})"
        )

        # Use Primitive operations to ensure cache consistency
        # 1. Remove both
        state.remove_entity(BoardEntityID(actual_unit_a))
        state.remove_entity(BoardEntityID(actual_unit_b))

        # 2. Place at swapped locations
        state.place_entity(BoardEntityID(actual_unit_a), loc_b)
        state.place_entity(BoardEntityID(actual_unit_b), loc_a)

        return StepResult(is_finished=True)


class SwapCardStep(GameStep):
    """
    Swaps the Hero's current turn card with another card (specified by ID or key).
    """

    type: StepType = StepType.SWAP_CARD
    target_card_id: Optional[str] = None
    target_card_key: Optional[str] = None  # Key in context to find ID
    context_hero_id_key: Optional[str] = None  # Key in context to find Hero ID

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        hero_id = state.current_actor_id

        # Override hero if key provided
        if self.context_hero_id_key:
            h_val = context.get(self.context_hero_id_key)
            if h_val:
                hero_id = HeroID(str(h_val))

        if not hero_id:
            return StepResult(is_finished=True)

        hero = state.get_hero(hero_id)
        if not hero or not hero.current_turn_card:
            return StepResult(is_finished=True)

        # Find target card ID
        t_id = self.target_card_id
        if not t_id and self.target_card_key:
            t_id = context.get(self.target_card_key)

        if not t_id:
            print("   [SWAP] No target card specified for swap.")
            return StepResult(is_finished=True)

        # Find the card object
        # We need to search Hand, Discard, Played
        # Simplest is to check all or use a helper, but Hero methods work on objects.
        target_card = None
        # Check Hand
        for c in hero.hand:
            if c.id == t_id:
                target_card = c
                break
        if not target_card:
            for c in hero.discard_pile:
                if c.id == t_id:
                    target_card = c
                    break
        if not target_card:
            for c in hero.played_cards:
                if c.id == t_id:
                    target_card = c
                    break

        if not target_card:
            print(f"   [SWAP] Target card {t_id} not found in {hero_id}'s possession.")
            return StepResult(is_finished=True)

        print(
            f"   [SWAP] Swapping {hero.id}'s current card {hero.current_turn_card.name} with {target_card.name}"
        )
        hero.swap_cards(hero.current_turn_card, target_card)

        # NOTE: After swapping, the "current_turn_card" has changed!
        # This might affect subsequent steps if they rely on "current_card_id" in context.
        # But usually context has the old ID if it was set earlier.
        # Ideally, we should update context if necessary, but "current_card_id" is usually set once at start of ResolveCardText.

        return StepResult(is_finished=True)


class PushUnitStep(GameStep):
    """
    Pushes a unit away from a source location.
    Stops at obstacles or board edge.

    Supports two modes:
    - Direct: Provide target_id and distance directly
    - Context: Provide target_key and/or distance_key to read from context
    """

    type: StepType = StepType.PUSH_UNIT
    target_id: Optional[str] = None  # Direct target ID
    target_key: Optional[str] = None  # Read target from context
    source_hex: Optional[Hex] = None  # If None, uses current actor's location
    distance: int = 1  # Default/fallback distance
    distance_key: Optional[str] = None  # Read distance from context

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        # Resolve target ID from either direct or context
        actual_target_id = self.target_id
        if not actual_target_id and self.target_key:
            actual_target_id = context.get(self.target_key)

        if not actual_target_id:
            print("   [SKIP] PushUnitStep: No target specified or found in context.")
            return StepResult(is_finished=True)

        # Resolve distance from context or use default
        actual_distance = self.distance
        if self.distance_key:
            ctx_dist = context.get(self.distance_key)
            if ctx_dist is not None:
                actual_distance = int(ctx_dist)

        target_loc = state.unit_locations.get(UnitID(actual_target_id))
        if not target_loc:
            return StepResult(is_finished=True)

        src_hex = self.source_hex
        if not src_hex:
            if state.current_actor_id:
                src_hex = state.entity_locations.get(
                    BoardEntityID(state.current_actor_id)
                )

        if not src_hex:
            print("   [ERROR] No source for push.")
            return StepResult(is_finished=True)

        if src_hex == target_loc:
            print("   [ERROR] Cannot push from same hex.")
            return StepResult(is_finished=True)

        # Validation
        actor_id = state.current_actor_id
        res = state.validator.can_be_pushed(
            state, actual_target_id, str(actor_id) if actor_id else "system", context
        )
        if not res.allowed:
            print(f"   [BLOCKED] Push prevented for {actual_target_id}: {res.reason}")
            if self.is_mandatory:
                return StepResult(is_finished=True, abort_action=True)
            return StepResult(is_finished=True)

        direction_idx = src_hex.direction_to(target_loc)
        if direction_idx is None:
            print(
                f"   [ERROR] Push target {actual_target_id} is not in a straight line from source."
            )
            return StepResult(is_finished=True)

        current_loc = target_loc
        pushed_dist = 0
        for _ in range(actual_distance):
            next_hex = current_loc.neighbor(direction_idx)

            if next_hex not in state.board.tiles:
                print(f"   [PUSH] {actual_target_id} hit board edge at {current_loc}")
                break

            tile = state.board.get_tile(next_hex)
            if tile and tile.is_obstacle:
                print(f"   [PUSH] {actual_target_id} hit obstacle at {next_hex}")
                break

            current_loc = next_hex
            pushed_dist += 1

        if pushed_dist > 0:
            print(
                f"   [LOGIC] Pushing {actual_target_id} from {target_loc} to {current_loc} ({pushed_dist} spaces)"
            )
            state.move_unit(UnitID(actual_target_id), current_loc)
        else:
            print(f"   [LOGIC] Push had no effect for {actual_target_id}")

        return StepResult(is_finished=True)


class RespawnHeroStep(GameStep):
    """
    Handles the Hero Respawn choice.
    If Hero is defeated, requests player input: Respawn or Pass.
    """

    type: StepType = StepType.RESPAWN_HERO
    hero_id: str

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        hero = state.get_hero(HeroID(self.hero_id))
        if not hero:
            return StepResult(is_finished=True)

        # Only respawn if not on board
        if self.hero_id in state.unit_locations:
            return StepResult(is_finished=True)

        if self.pending_input:
            choice = self.pending_input.get("choice")
            if choice == "PASS":
                print(f"   [RESPAWN] {self.hero_id} chose NOT to respawn.")
                context["skipped_respawn"] = True
                return StepResult(is_finished=True)

            selected_hex_dict = self.pending_input.get("spawn_hex")
            if selected_hex_dict:
                selected_hex = Hex(**selected_hex_dict)
                print(f"   [RESPAWN] {self.hero_id} respawning at {selected_hex}")
                state.move_unit(UnitID(self.hero_id), selected_hex)
                return StepResult(is_finished=True)

        valid_hexes = []
        for h, tile in state.board.tiles.items():
            if (
                tile.spawn_point
                and tile.spawn_point.is_hero_spawn
                and tile.spawn_point.team == hero.team
            ):
                if not tile.is_occupied:
                    valid_hexes.append(h)

        if not valid_hexes:
            print(f"   [RESPAWN] No empty spawn points for {self.hero_id}!")
            return StepResult(is_finished=True)

        return StepResult(
            requires_input=True,
            input_request={
                "type": "CHOOSE_RESPAWN",
                "prompt": f"Hero {self.hero_id} is defeated. Respawn at an empty spawn point?",
                "player_id": self.hero_id,
                "options": ["RESPAWN", "PASS"],
                "valid_hexes": valid_hexes,
            },
        )


class RespawnMinionStep(GameStep):
    """
    Respawns a minion of a certain type/team in the active zone.
    """

    type: StepType = StepType.RESPAWN_MINION
    team: TeamColor
    minion_type: Any  # MinionType enum

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        zone_id = state.active_zone_id
        if not zone_id:
            return StepResult(is_finished=True)

        zone = state.board.zones.get(zone_id)
        if not zone:
            return StepResult(is_finished=True)

        target_minion = None
        # Check if minion exists in team roster but not on board (limbo)
        team_obj = state.teams.get(self.team) if self.team else None
        if not team_obj:
            return StepResult(is_finished=True)

        for m in team_obj.minions:
            if m.type == self.minion_type and m.id not in state.entity_locations:
                target_minion = m
                break

        if not target_minion:
            # Safely handle team name if team exists, otherwise default
            team_name = self.team.name if self.team else "Unknown"
            print(
                f"   [RESPAWN] No available {team_name} {self.minion_type} to respawn."
            )
            return StepResult(is_finished=True)

        if self.pending_input:
            selected_hex_dict = self.pending_input.get("spawn_hex")
            if selected_hex_dict:
                selected_hex = Hex(**selected_hex_dict)
                tile = state.board.get_tile(selected_hex)
                if tile and tile.is_occupied:
                    print(
                        f"   [ERROR] Cannot respawn {self.minion_type} at {selected_hex}. Occupied."
                    )
                    return StepResult(is_finished=True)

                state.move_unit(UnitID(target_minion.id), selected_hex)
                print(f"   [RESPAWN] Respawned {target_minion.id} at {selected_hex}")
                return StepResult(is_finished=True)

        valid_spaces = [
            h for h in zone.hexes if not state.board.get_tile(h).is_occupied
        ]
        if not valid_spaces:
            return StepResult(is_finished=True)

        return StepResult(
            requires_input=True,
            input_request={
                "type": "SELECT_HEX",
                "prompt": f"Select space to respawn {self.minion_type}.",
                "player_id": str(state.current_actor_id)
                if state.current_actor_id
                else "system",
                "valid_hexes": valid_spaces,
            },
        )


class ResolveCardTextStep(GameStep):
    """
    Placeholder for executing the specific Python script/logic associated with a card's text.
    In a full implementation, this would look up a registry using `card.effect_id`
    and execute the specific function/class for that card.
    """

    type: StepType = StepType.RESOLVE_CARD_TEXT
    card_id: str
    hero_id: str

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        hero = state.get_hero(HeroID(self.hero_id))
        if not hero or not hero.current_turn_card:
            return StepResult(is_finished=True)

        card = hero.current_turn_card

        # Set card ID in context for effect creation
        context["current_card_id"] = card.id

        print(
            f"   [SCRIPT] Executing logic for '{card.name}' (Effect: {card.effect_id})"
        )

        from goa2.engine.effects import CardEffectRegistry

        effect = CardEffectRegistry.get(card.effect_id)

        if effect:
            # We must use a different variable name here or not declare `new_steps` again below
            effect_steps = effect.get_steps(state, hero, card)
            return StepResult(is_finished=True, new_steps=effect_steps)

        # Fallback to standard primary primitives if no specific script found
        if not card.primary_action:
            print("            > No custom script found and no primary action.")
            return StepResult(is_finished=True)

        print(
            f"            > No custom script found. Using standard {card.primary_action.name} logic."
        )
        # Declared here for the first time in this scope path
        steps_list: List[GameStep] = []

        if card.primary_action == ActionType.MOVEMENT:
            # MOVEMENT: Compute Total
            base_val = card.get_base_stat_value(StatType.MOVEMENT)
            total_val = get_computed_stat(
                state, UnitID(self.hero_id), StatType.MOVEMENT, base_val
            )
            steps_list.append(
                MoveSequenceStep(unit_id=self.hero_id, range_val=total_val)
            )

        elif card.primary_action == ActionType.ATTACK:
            # ATTACK: Compute Damage & Range
            base_dmg = card.get_base_stat_value(StatType.ATTACK)
            total_dmg = get_computed_stat(
                state, UnitID(self.hero_id), StatType.ATTACK, base_dmg
            )

            base_rng = card.get_base_stat_value(StatType.RANGE)
            # Default Range is 1 if not specified (and get_base_stat_value returns 0 if None)
            if base_rng == 0:
                base_rng = 1
            total_rng = get_computed_stat(
                state, UnitID(self.hero_id), StatType.RANGE, base_rng
            )

            steps_list.append(AttackSequenceStep(damage=total_dmg, range_val=total_rng))

        elif card.primary_action == ActionType.DEFENSE:
            steps_list.append(
                LogMessageStep(message=f"{self.hero_id} Defends (Primary).")
            )
        elif card.primary_action == ActionType.SKILL:
            print(f"            > Skill '{card.name}' has no registered effect!")
            steps_list.append(
                LogMessageStep(message=f"Skill '{card.name}' did nothing.")
            )

        return StepResult(is_finished=True, new_steps=steps_list)


class ResolveCardStep(GameStep):
    """
    Analyzes the active card and prompts the user to choose an Action.
    Spawns the appropriate logic steps based on the choice.
    """

    type: StepType = StepType.RESOLVE_CARD
    hero_id: str

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        hero = state.get_hero(HeroID(self.hero_id))
        if not hero or not hero.current_turn_card:
            return StepResult(is_finished=True)

        card = hero.current_turn_card

        options = []

        from goa2.engine.rules import get_safe_zones_for_fast_travel

        def is_action_available(act_type: ActionType) -> bool:
            # 1. Check Global/Effect Validation (e.g. Spell Break prevention)
            # We pass the 'card' object in context so validation can check exceptions (color).
            val_res = state.validator.can_perform_action(
                state, self.hero_id, act_type, context={"card": card}
            )
            if not val_res.allowed:
                return False

            if act_type == ActionType.FAST_TRAVEL:
                u_loc = state.unit_locations.get(UnitID(self.hero_id))
                if not u_loc:
                    return False
                z_id = state.board.get_zone_for_hex(u_loc)
                if not z_id:
                    return False

                if not hero:
                    return False

                # Ensure team is present
                team = getattr(hero, "team", None)
                if not team:
                    return False

                safe = get_safe_zones_for_fast_travel(state, team, z_id)
                if not safe:
                    return False
            return True

        # Helper to compute option values
        def compute_option(
            act_type: ActionType, base_val: Optional[int]
        ) -> Tuple[int, str]:
            # Default
            final_val = base_val or 0
            text_val = str(final_val) if base_val is not None else "-"

            # Map Action to Stat
            stat_type = None
            if act_type == ActionType.MOVEMENT:
                stat_type = StatType.MOVEMENT
            elif act_type == ActionType.ATTACK:
                stat_type = StatType.ATTACK
            elif act_type == ActionType.DEFENSE:
                stat_type = StatType.DEFENSE
            elif act_type == ActionType.DEFENSE_SKILL:
                stat_type = StatType.DEFENSE
            elif act_type == ActionType.DEFENSE_SKILL:
                stat_type = StatType.DEFENSE

            if stat_type:
                final_val = get_computed_stat(
                    state, UnitID(self.hero_id), stat_type, base_val or 0
                )
                text_val = str(final_val)

            return final_val, text_val

        # Primary - DEFENSE cannot be chosen as an active action on your turn
        # DEFENSE_SKILL is shown as SKILL option
        primary_action = card.current_primary_action
        if primary_action and primary_action not in (
            ActionType.DEFENSE,
            ActionType.DEFENSE_SKILL,
        ):
            if is_action_available(primary_action):
                c_val, c_text = compute_option(
                    primary_action, card.current_primary_action_value
                )
                options.append(
                    {
                        "id": primary_action.name,
                        "type": primary_action,
                        "value": c_val,
                        "text": f"Primary: {primary_action.name} ({c_text})",
                    }
                )
        # DEFENSE_SKILL is shown as SKILL option
        elif primary_action == ActionType.DEFENSE_SKILL:
            if is_action_available(ActionType.SKILL):
                c_val, c_text = compute_option(
                    ActionType.SKILL, card.current_primary_action_value
                )
                options.append(
                    {
                        "id": ActionType.SKILL.name,
                        "type": ActionType.SKILL,
                        "value": c_val,
                        "text": f"Primary: SKILL ({c_text})",
                    }
                )

        # Secondaries - DEFENSE cannot be chosen as an active action on your turn
        for action_type, val in card.current_secondary_actions.items():
            if action_type == ActionType.DEFENSE:
                continue  # Skip DEFENSE - it can only be used during reaction window
            if is_action_available(action_type):
                c_val, c_text = compute_option(action_type, val)
                options.append(
                    {
                        "id": action_type.name,
                        "type": action_type,
                        "value": c_val,
                        "text": f"Secondary: {action_type.name} ({c_text})",
                    }
                )

        if self.pending_input:
            choice_id = self.pending_input.get("choice_id")
            selected_opt = next((o for o in options if o["id"] == choice_id), None)

            if selected_opt:
                # Type safe access
                act_type = cast(ActionType, selected_opt["type"])
                val = cast(int, selected_opt["value"])
                # Determine if primary by checking the card itself
                is_primary = act_type == primary_action
                # DEFENSE_SKILL played as SKILL still uses primary effect
                if (
                    card.primary_action == ActionType.DEFENSE_SKILL
                    and act_type == ActionType.SKILL
                ):
                    is_primary = True

                print(f"   [CHOICE] Player selected {choice_id} ({act_type.name})")

                # Track current action type for effect origin tracking
                context["current_action_type"] = act_type

                # NOTE: Renamed local variable to avoid shadowing re-declaration if any
                steps_list: List[GameStep] = []

                # Check for BEFORE_* passive abilities based on action type
                from goa2.domain.models.enums import PassiveTrigger

                passive_trigger = None
                if act_type == ActionType.ATTACK:
                    passive_trigger = PassiveTrigger.BEFORE_ATTACK
                elif act_type == ActionType.MOVEMENT:
                    passive_trigger = PassiveTrigger.BEFORE_MOVEMENT
                elif act_type == ActionType.SKILL:
                    passive_trigger = PassiveTrigger.BEFORE_SKILL

                if passive_trigger:
                    steps_list.append(
                        CheckPassiveAbilitiesStep(trigger=passive_trigger.value)
                    )

                if is_primary:
                    # User Mandate: Primary actions apply custom script.
                    steps_list.append(
                        ResolveCardTextStep(card_id=card.id, hero_id=self.hero_id)
                    )
                else:
                    # Secondary: Standard Primitives
                    if act_type == ActionType.MOVEMENT:
                        steps_list.append(
                            MoveSequenceStep(unit_id=self.hero_id, range_val=val)
                        )

                    elif act_type == ActionType.FAST_TRAVEL:
                        steps_list.append(FastTravelSequenceStep(unit_id=self.hero_id))

                    elif act_type == ActionType.ATTACK:
                        # Damage is already computed in 'val'
                        # But Range is implicit, so compute it here
                        base_rng = card.get_base_stat_value(StatType.RANGE)
                        if base_rng == 0:
                            base_rng = 1
                        total_rng = get_computed_stat(
                            state, UnitID(self.hero_id), StatType.RANGE, base_rng
                        )

                        steps_list.append(
                            AttackSequenceStep(damage=val, range_val=total_rng)
                        )

                    elif act_type == ActionType.CLEAR:
                        steps_list.append(
                            LogMessageStep(message=f"{self.hero_id} clears tokens.")
                        )

                    elif act_type == ActionType.HOLD:
                        steps_list.append(
                            LogMessageStep(message=f"{self.hero_id} Holds.")
                        )

                    elif act_type == ActionType.DEFENSE:
                        # Should not happen as action, but valid in enum
                        steps_list.append(
                            LogMessageStep(message=f"{self.hero_id} Defends (Active).")
                        )

                return StepResult(is_finished=True, new_steps=steps_list)

        return StepResult(
            requires_input=True,
            input_request={
                "type": "CHOOSE_ACTION",
                "prompt": f"Choose action for card {card.name}",
                "player_id": self.hero_id,
                "options": options,
            },
        )


class ResolveDisplacementStep(GameStep):
    """
    Handles the placement of minions that could not spawn due to occupied tiles.
    Uses BFS to find nearest empty hexes and prompts team if multiple options exist.
    """

    type: StepType = StepType.RESOLVE_DISPLACEMENT
    # List of (UnitID, OriginalHex)
    displacements: List[Tuple[str, Hex]] = Field(default_factory=list)

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if not self.displacements:
            return StepResult(is_finished=True)

        red_units = []
        blue_units = []

        for uid, origin in self.displacements:
            unit = state.get_unit(UnitID(uid))
            if unit:
                if unit.team == TeamColor.RED:
                    red_units.append((uid, origin))
                elif unit.team == TeamColor.BLUE:
                    blue_units.append((uid, origin))

        first_group = []
        second_group = []

        if state.tie_breaker_team == TeamColor.RED:
            first_group = red_units
            second_group = blue_units
        else:
            first_group = blue_units
            second_group = red_units

        active_group = first_group if first_group else second_group
        if not active_group:
            return StepResult(is_finished=True)

        if self.pending_input:
            sel_uid = self.pending_input.get("selected_unit_id")
            if sel_uid:
                target_tuple = next((u for u in active_group if u[0] == sel_uid), None)
                if target_tuple:
                    remaining_active = [u for u in active_group if u[0] != sel_uid]
                    remaining = remaining_active + (
                        second_group if active_group is first_group else []
                    )

                    return StepResult(
                        is_finished=True,
                        new_steps=[
                            ResolveDisplacementStep(displacements=[target_tuple]),
                            ResolveDisplacementStep(displacements=remaining),
                        ],
                    )

        if len(active_group) > 1:
            options = [u[0] for u in active_group]
            unit_obj = state.get_unit(UnitID(options[0]))
            team = unit_obj.team if unit_obj else TeamColor.RED

            delegate_id = "unknown"
            team_obj = state.teams.get(team) if team else None
            if team_obj and team_obj.heroes:
                delegate_id = team_obj.heroes[0].id

            return StepResult(
                requires_input=True,
                input_request={
                    "type": "SELECT_UNIT",
                    "prompt": f"Team {team.name if team else 'Unknown'}, choose which displaced unit to place first.",
                    "player_id": delegate_id,
                    "valid_options": options,
                },
            )

        uid, origin = active_group[0]
        remaining = active_group[1:] + (
            second_group if active_group is first_group else []
        )

        from goa2.engine.map_logic import find_nearest_empty_hexes

        if not state.active_zone_id:
            # Should be impossible if game is running, but safety check
            return StepResult(is_finished=True)

        candidates = find_nearest_empty_hexes(state, origin, state.active_zone_id)

        if not candidates:
            print(f"   [DISPLACE] No empty space found for {uid} in zone!")
            return StepResult(
                is_finished=True,
                new_steps=[ResolveDisplacementStep(displacements=remaining)],
            )

        if self.pending_input:
            selection = self.pending_input.get("selection")
            if selection:
                target_hex = Hex(**selection)
                if target_hex in candidates:
                    print(f"   [DISPLACE] Team chose {target_hex} for {uid}")
                    return StepResult(
                        is_finished=True,
                        new_steps=[
                            PlaceUnitStep(unit_id=uid, target_hex_arg=target_hex),
                            ResolveDisplacementStep(displacements=remaining),
                        ],
                    )

        if len(candidates) == 1:
            target = candidates[0]
            print(f"   [DISPLACE] Auto-placing {uid} at {target}")
            return StepResult(
                is_finished=True,
                new_steps=[
                    PlaceUnitStep(unit_id=uid, target_hex_arg=target),
                    ResolveDisplacementStep(displacements=remaining),
                ],
            )

        unit_obj = state.get_unit(UnitID(uid))
        team = unit_obj.team if unit_obj else TeamColor.RED

        delegate_id = "unknown"
        # Safely access state.teams with team key
        if team:
            team_obj = state.teams.get(team)
            if team_obj and team_obj.heroes:
                delegate_id = team_obj.heroes[0].id

        return StepResult(
            requires_input=True,
            input_request={
                "type": "SELECT_HEX",
                "prompt": f"Team {team.name if team else 'Unknown'}, choose displacement for {unit_obj.name if unit_obj else uid}.",
                "player_id": delegate_id,
                "valid_hexes": candidates,
                "context_unit_id": uid,
            },
        )


class LanePushStep(GameStep):
    """
    Executes a Lane Push:
    1. Removes Wave Counter.
    2. Moves Battle Zone.
    3. Wipes Minions in old zone.
    4. Respawns Minions in new zone.
    5. Checks Victory Conditions (Throne or Last Push).
    """

    type: StepType = StepType.LANE_PUSH
    losing_team: TeamColor

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        from goa2.engine.map_logic import get_push_target_zone_id

        print(f"   [PUSH] Lane Push Triggered! Losing Team: {self.losing_team.name}")

        state.wave_counter -= 1
        print(f"   [PUSH] Wave Counter removed. Remaining: {state.wave_counter}")

        if state.wave_counter <= 0:
            print("   [GAME OVER] Last Push Victory!")
            winning_team = (
                TeamColor.BLUE if self.losing_team == TeamColor.RED else TeamColor.RED
            )
            return StepResult(
                is_finished=True,
                new_steps=[
                    TriggerGameOverStep(winner=winning_team, condition="LAST_PUSH")
                ],
            )

        next_zone_id, is_game_over = get_push_target_zone_id(state, self.losing_team)

        if is_game_over:
            print(
                f"   [GAME OVER] Lane Push Victory! {self.losing_team.name} Throne reached."
            )
            winning_team = (
                TeamColor.BLUE if self.losing_team == TeamColor.RED else TeamColor.RED
            )
            return StepResult(
                is_finished=True,
                new_steps=[
                    TriggerGameOverStep(winner=winning_team, condition="LANE_PUSH")
                ],
            )

        if not next_zone_id:
            print("   [ERROR] Could not determine next zone for push.")
            return StepResult(is_finished=True)

        if not state.active_zone_id:
            print("   [ERROR] No active zone for push.")
            return StepResult(is_finished=True)

        current_zone = state.board.zones.get(state.active_zone_id)

        # Per rules: "Remove all Minions from old Battle Zone."
        # Heroes stay? Yes, heroes are displaced only if blocking spawn (handled by respawn logic later).
        # Actually rules say: "Occupied by Unit: Owning Team Places Minion..."
        # But here we just wipe OLD minions.

        to_remove = []
        if current_zone:
            for uid, loc in state.unit_locations.items():
                if loc in current_zone.hexes:
                    unit = state.get_unit(UnitID(uid))
                    if hasattr(unit, "type") and hasattr(
                        unit, "value"
                    ):  # Duck typing Minion
                        to_remove.append(uid)

        for uid in to_remove:
            state.remove_unit(uid)
            print(f"   [PUSH] Wiped {uid} from old zone.")

        print(f"   [PUSH] Battle Zone moved: {state.active_zone_id} -> {next_zone_id}")
        state.active_zone_id = next_zone_id

        next_zone = state.board.zones.get(next_zone_id)
        pending_displacements = []

        if next_zone:
            # We need to spawn minions for BOTH teams at their respective points in the new zone.

            for sp in next_zone.spawn_points:
                if sp.is_minion_spawn:
                    team = state.teams.get(sp.team)
                    if team:
                        candidate = next(
                            (
                                m
                                for m in team.minions
                                if m.type == sp.minion_type
                                and m.id not in state.unit_locations
                            ),
                            None,
                        )

                        if candidate:
                            tile = state.board.get_tile(sp.location)
                            if tile and not tile.is_occupied:
                                state.move_unit(candidate.id, sp.location)
                                print(
                                    f"   [PUSH] Spawning {candidate.id} at {sp.location}"
                                )
                            else:
                                print(
                                    f"   [PUSH] Spawn blocked at {sp.location} (Displacement Queued)"
                                )
                                pending_displacements.append(
                                    (candidate.id, sp.location)
                                )

        if pending_displacements:
            # Explicitly type cast the list to match ResolveDisplacementStep's expectation
            # ResolveDisplacementStep expects List[Tuple[str, Hex]] or similar.
            # candidate.id is BoardEntityID (subtype of str).
            return StepResult(
                is_finished=True,
                new_steps=[
                    ResolveDisplacementStep(
                        displacements=cast(List[Tuple[str, Hex]], pending_displacements)
                    )
                ],
            )

        return StepResult(is_finished=True)


class AskConfirmationStep(GameStep):
    """
    Prompts the player for a Yes/No confirmation.
    Useful for optional repeats or effects.
    """

    type: StepType = StepType.ASK_CONFIRMATION
    prompt: str
    output_key: str = "confirmation"
    player_id: Optional[str] = None

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        actor_id = self.player_id or state.current_actor_id
        if not actor_id:
            return StepResult(is_finished=True)

        if self.pending_input:
            selection = self.pending_input.get("selection")
            # Logic: "YES" = True, "NO" = False
            context[self.output_key] = selection == "YES"
            print(f"   [INPUT] {actor_id} chose {selection} for '{self.prompt}'")
            return StepResult(is_finished=True)

        return StepResult(
            requires_input=True,
            input_request={
                "type": "SELECT_OPTION",  # Frontend maps this to Buttons
                "prompt": self.prompt,
                "player_id": actor_id,
                "options": [
                    {"id": "YES", "text": "Yes"},
                    {"id": "NO", "text": "No"},
                ],
            },
        )


class RecordTargetStep(GameStep):
    """
    Appends a target ID (from context) to a list (in context).
    Used to track history for 'different target' filters.
    """

    type: StepType = StepType.RECORD_TARGET
    input_key: str  # The key holding the current target ID
    output_list_key: str  # The key for the list of IDs

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        target_id = context.get(self.input_key)
        if target_id:
            if self.output_list_key not in context:
                context[self.output_list_key] = []
            if isinstance(context[self.output_list_key], list):
                context[self.output_list_key].append(target_id)
                print(f"   [LOGIC] Recorded {target_id} to {self.output_list_key}")
        return StepResult(is_finished=True)


class MayRepeatOnceStep(GameStep):
    """
    Wraps a sequence of steps that can be repeated once upon player confirmation.
    Checks ValidationService.can_repeat_action() before asking.
    """

    type: StepType = StepType.MAY_REPEAT_ONCE
    steps_template: List["GameStep"] = Field(default_factory=list)
    prompt: str = "Repeat action?"

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        actor_id = state.current_actor_id
        if not actor_id:
            return StepResult(is_finished=True)

        # 1. Validation Check (Early exit if blocked)
        res = state.validator.can_repeat_action(state, str(actor_id), context)
        if not res.allowed:
            print(f"   [REPEAT] Blocked by validation: {res.reason}")
            return StepResult(is_finished=True)

        # 2. Input Handling
        if self.pending_input:
            selection = self.pending_input.get("selection")
            if selection == "YES":
                print(
                    f"   [REPEAT] Confirmed. Spawning {len(self.steps_template)} steps."
                )
                # Deepcopy to ensure fresh state for the new steps
                new_steps = [copy.deepcopy(s) for s in self.steps_template]
                return StepResult(is_finished=True, new_steps=new_steps)
            else:
                print("   [REPEAT] Declined.")
                return StepResult(is_finished=True)

        # 3. Request Input
        return StepResult(
            requires_input=True,
            input_request={
                "type": "SELECT_OPTION",
                "prompt": self.prompt,
                "player_id": actor_id,
                "options": [
                    {"id": "YES", "text": "Yes"},
                    {"id": "NO", "text": "No"},
                ],
            },
        )


class ValidateRepeatStep(GameStep):
    """
    Checks if the actor is allowed to repeat an action.
    Consults ValidationService.can_repeat_action().
    Can optionally AND the result with an existing context flag.
    """

    type: StepType = StepType.VALIDATE_REPEAT
    actor_id: Optional[str] = None
    and_with_key: Optional[str] = None  # If set, combines with this boolean key
    output_key: str = "can_repeat"

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        act_id = self.actor_id or state.current_actor_id
        if not act_id:
            context[self.output_key] = False
            return StepResult(is_finished=True)

        res = state.validator.can_repeat_action(state, str(act_id), context)
        val = res.allowed

        if self.and_with_key:
            prev_val = context.get(self.and_with_key, False)
            val = val and prev_val
            print(
                f"   [CHECK] Repeat Validation: Validator={res.allowed}, Context({self.and_with_key})={prev_val} -> Result={val}"
            )
        else:
            print(f"   [CHECK] Repeat Validation: Result={val}")

        context[self.output_key] = val
        return StepResult(is_finished=True)


class CheckAdjacencyStep(GameStep):
    """
    Checks if two units are adjacent and sets a context flag.
    Used for conditional effects (e.g. Ebb and Flow).
    """

    type: StepType = StepType.CHECK_ADJACENCY
    unit_a_id: Optional[str] = None
    unit_b_id: Optional[str] = None
    unit_a_key: Optional[str] = None
    unit_b_key: Optional[str] = None
    output_key: str = "is_adjacent"

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        u_a = self.unit_a_id
        if not u_a and self.unit_a_key:
            u_a = context.get(self.unit_a_key)

        u_b = self.unit_b_id
        if not u_b and self.unit_b_key:
            u_b = context.get(self.unit_b_key)

        if not u_a or not u_b:
            context[self.output_key] = False
            return StepResult(is_finished=True)

        loc_a = state.entity_locations.get(BoardEntityID(u_a))
        loc_b = state.entity_locations.get(BoardEntityID(u_b))

        if not loc_a or not loc_b:
            context[self.output_key] = False
            return StepResult(is_finished=True)

        dist = loc_a.distance(loc_b)
        context[self.output_key] = dist == 1
        print(f"   [CHECK] Adjacency between {u_a} and {u_b}: {dist == 1}")

        return StepResult(is_finished=True)


class CheckLanePushStep(GameStep):
    """
    Checks if the active zone meets the condition for a Lane Push (0 minions for one team).
    If so, spawns a LanePushStep.
    """

    type: StepType = StepType.CHECK_LANE_PUSH

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        from goa2.engine.map_logic import check_lane_push_trigger

        if not state.active_zone_id:
            return StepResult(is_finished=True)

        losing_team = check_lane_push_trigger(state, state.active_zone_id)
        if losing_team:
            print(f"   [CHECK] Lane Push Condition Met for {losing_team.name}")
            return StepResult(
                is_finished=True, new_steps=[LanePushStep(losing_team=losing_team)]
            )

        return StepResult(is_finished=True)


class EndPhaseCleanupStep(GameStep):
    """
    Handles the non-combat cleanup of End Phase:
    Retrieve Cards, Clear Tokens, Level Up, Round Reset.
    """

    type: StepType = StepType.END_PHASE_CLEANUP

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        print("   [CLEANUP] Processing End Phase Cleanup...")
        from goa2.engine.effect_manager import EffectManager

        # Expire THIS_ROUND items
        EffectManager.expire_effects(state, DurationType.THIS_ROUND)

        # Return all markers to supply (per board game rules)
        state.return_all_markers()
        print("   [CLEANUP] All markers returned to supply")

        # Cleanup stale items (lazy expiration for cards leaving play)
        EffectManager.cleanup_stale_effects(state)

        self._retrieve_cards(state)
        self._clear_tokens(state)
        self._level_up(state)

        if state.pending_upgrades:
            print("   [PHASE] Level Up Phase started.")
            return StepResult(is_finished=True, new_steps=[ResolveUpgradesStep()])

        state.round += 1
        state.turn = 1
        state.phase = GamePhase.PLANNING
        print(f"   [ROUND START] Round {state.round}, Turn {state.turn}")

        return StepResult(is_finished=True)

    def _retrieve_cards(self, state: GameState):
        for team in state.teams.values():
            for hero in team.heroes:
                # Deactivate effects from all cards before retrieval
                for card in hero.played_cards:
                    EffectManager.deactivate_effects_by_card(state, card.id)
                if hero.current_turn_card:
                    EffectManager.deactivate_effects_by_card(
                        state, hero.current_turn_card.id
                    )
                hero.retrieve_cards()

    def _clear_tokens(self, state: GameState):
        pass

    def _level_up(self, state: GameState):
        """
        Calculates gold spending and level increments.
        Rule 3.1: Costs follow cumulative table. Mandatory purchase.

        Note: Level 8 unlocks the ultimate card automatically (no upgrade choice).
        Only levels 2-7 count as pending upgrades requiring card selection.
        """
        LEVEL_COSTS = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7}
        any_level_ups = False

        for team in state.teams.values():
            for hero in team.heroes:
                upgrades_this_round = 0
                unlocked_ultimate = False
                while hero.level < 8:
                    next_level = hero.level + 1
                    cost = LEVEL_COSTS[next_level]
                    if hero.gold >= cost:
                        hero.gold -= cost
                        hero.level = next_level
                        any_level_ups = True

                        if next_level == 8:
                            # Level 8: Ultimate unlocks automatically (no upgrade choice)
                            unlocked_ultimate = True
                            if hero.ultimate_card:
                                print(
                                    f"   [ULTIMATE UNLOCKED] {hero.id} reached Level 8! "
                                    f"'{hero.ultimate_card.name}' is now active!"
                                )
                            else:
                                print(f"   [LEVEL] {hero.id} reached Level 8!")
                        else:
                            # Levels 2-7: Count as pending upgrade (requires card choice)
                            upgrades_this_round += 1
                            print(f"   [LEVEL] {hero.id} reached Level {hero.level}!")
                    else:
                        break

                if upgrades_this_round > 0:
                    state.pending_upgrades[hero.id] = upgrades_this_round
                elif not unlocked_ultimate:
                    # Pity Coin: Players who did not Level Up gain 1 Gold.
                    # (Don't give pity coin if they unlocked ultimate)
                    hero.gold += 1
                    print(
                        f"   [ECONOMY] {hero.id} did not level up. Gains 1 Pity Gold. (Gold: {hero.gold})"
                    )

        if any_level_ups:
            state.phase = GamePhase.LEVEL_UP


class EndPhaseStep(GameStep):
    """
    Entry point for End Phase.
    Executes Minion Battle, checks for Lane Push, then queues Cleanup.
    """

    type: StepType = StepType.END_PHASE

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        print("   [ROUND END] Processing End Phase (Battle)...")

        self._resolve_minion_battle(state)

        new_steps: List[GameStep] = []

        from goa2.engine.map_logic import check_lane_push_trigger

        if state.active_zone_id:
            losing_team = check_lane_push_trigger(state, state.active_zone_id)
            if losing_team:
                new_steps.append(LanePushStep(losing_team=losing_team))

        new_steps.append(EndPhaseCleanupStep())

        return StepResult(is_finished=True, new_steps=new_steps)

    def _resolve_minion_battle(self, state: GameState):
        """
        Compare minion counts in active zone. Loser removes difference.
        Heavy minions must be last to be removed.
        """
        if not state.active_zone_id:
            return

        zone = state.board.zones.get(state.active_zone_id)
        if not zone:
            return

        red_minions = []
        blue_minions = []

        for unit_id, loc in state.unit_locations.items():
            if loc in zone.hexes:
                unit = state.get_unit(UnitID(unit_id))
                if unit and hasattr(unit, "type") and hasattr(unit, "is_heavy"):
                    if unit.team == TeamColor.RED:
                        red_minions.append(unit)
                    elif unit.team == TeamColor.BLUE:
                        blue_minions.append(unit)

        r_count = len(red_minions)
        b_count = len(blue_minions)
        diff = abs(r_count - b_count)

        if diff == 0:
            print("   [BATTLE] Minion count tied. No removals.")
            return

        loser_team = TeamColor.RED if r_count < b_count else TeamColor.BLUE
        loser_minions = red_minions if loser_team == TeamColor.RED else blue_minions

        print(f"   [BATTLE] {loser_team.name} loses {diff} minion(s).")

        loser_minions.sort(key=lambda m: m.is_heavy)

        removals = loser_minions[:diff]
        for m in removals:
            print(f"   [BATTLE] Removing {m.id} ({m.type.name})")
            state.remove_unit(m.id)


class ResolveTieBreakerStep(GameStep):
    """
    Recursive handler for tied initiative players.
    1. Determines next winner (via Coin Flip or Team Choice).
    2. Pushes Winner's logic to stack.
    3. Pushes remaining players back via another TieBreakerStep.
    """

    type: StepType = StepType.RESOLVE_TIE_BREAKER
    tied_hero_ids: List[HeroID]

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if not self.tied_hero_ids:
            return StepResult(is_finished=True)

        teams_represented: Dict[TeamColor, List[str]] = {}
        for h_id in self.tied_hero_ids:
            hero = state.get_hero(HeroID(h_id))
            if hero and hero.team:
                teams_represented.setdefault(hero.team, []).append(h_id)

        winner_id = None
        needs_input = False
        target_team = None
        candidates = []

        # LOGIC:
        # A. If multiple teams -> Use Tie Breaker Coin to pick the FAVORED Team.
        if len(teams_represented) > 1:
            favored_team = state.tie_breaker_team
            if favored_team in teams_represented:
                candidates = teams_represented[favored_team]
                target_team = favored_team
            else:
                target_team = list(teams_represented.keys())[0]
                candidates = teams_represented[target_team]

            if len(candidates) > 1:
                needs_input = True
            else:
                winner_id = candidates[0]
                state.tie_breaker_team = (
                    TeamColor.BLUE
                    if state.tie_breaker_team == TeamColor.RED
                    else TeamColor.RED
                )
                print(
                    f"   [TIE] Coin wins for {favored_team.name}. {winner_id} acts. Coin flipped."
                )

        # B. If only one team -> they must choose who goes next
        else:
            target_team = list(teams_represented.keys())[0]
            candidates = teams_represented[target_team]
            if len(candidates) > 1:
                needs_input = True
            else:
                winner_id = candidates[0]

        if needs_input:
            if self.pending_input:
                winner_id = self.pending_input.get("selected_hero_id")
                print(
                    f"   [TIE] Team {target_team.name} chose {winner_id} to act first."
                )
                if len(teams_represented) > 1:
                    state.tie_breaker_team = (
                        TeamColor.BLUE
                        if state.tie_breaker_team == TeamColor.RED
                        else TeamColor.RED
                    )
            else:
                return StepResult(
                    requires_input=True,
                    input_request={
                        "type": "CHOOSE_ACTOR",
                        "prompt": f"Team {target_team.name}, choose who acts first between {candidates}.",
                        "player_ids": candidates,
                        "team": target_team,
                    },
                )

        # We have a winner!
        if not winner_id:
            raise ValueError("No winner identified in tie breaker.")

        winner_hero = state.get_hero(HeroID(winner_id))
        winner_card = winner_hero.current_turn_card if winner_hero else None

        # CRITICAL: Remove winner from unresolved pool so they don't act again immediately
        if winner_id in state.unresolved_hero_ids:
            state.unresolved_hero_ids.remove(HeroID(winner_id))

        state.current_actor_id = HeroID(winner_id)

        new_steps: List[GameStep] = []
        new_steps.append(ResolveCardStep(hero_id=winner_id))

        new_steps.append(FinalizeHeroTurnStep(hero_id=winner_id))

        return StepResult(is_finished=True, new_steps=new_steps)


class AttackSequenceStep(GameStep):
    """
    Composite Step.
    Expands into: Select Target -> Reaction Window -> Defense Effect -> Resolve Combat -> On Block Effect.

    Stores in context for defense effect resolution:
    - attack_is_ranged: True if range_val > 1
    - attacker_id: The ID of the attacking unit

    If target_id_key is provided, assumes target is already selected in context and skips selection.
    """

    type: StepType = StepType.ATTACK_SEQUENCE
    damage: int
    range_val: int = 1
    target_id_key: Optional[str] = (
        None  # Optional: Use existing context key instead of selecting
    )

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        print(
            f"   [MACRO] Expanding Attack Sequence (Dmg: {self.damage}, Rng: {self.range_val})"
        )

        from goa2.engine.filters import RangeFilter, TeamFilter

        key = self.target_id_key if self.target_id_key else "victim_id"

        # Store attack context for defense effect resolution
        context["attack_is_ranged"] = self.range_val > 1
        context["attacker_id"] = (
            str(state.current_actor_id) if state.current_actor_id else None
        )

        new_steps: List[GameStep] = []

        # Only spawn selection if we don't have a pre-selected key
        if not self.target_id_key:
            new_steps.append(
                SelectStep(
                    target_type=TargetType.UNIT,
                    prompt="Select Attack Target",
                    output_key=key,
                    filters=[
                        RangeFilter(max_range=self.range_val),
                        TeamFilter(relation="ENEMY"),
                    ],
                )
            )

        new_steps.extend(
            [
                ReactionWindowStep(target_player_key=key),
                ResolveDefenseTextStep(),  # NEW: Process defense card effects
                ResolveCombatStep(damage=self.damage, target_key=key),
                ResolveOnBlockEffectStep(),  # NEW: Process 'if you do' effects
                RestoreActionTypeStep(),  # Restore action type after defense resolution
            ]
        )

        return StepResult(is_finished=True, new_steps=new_steps)


def apply_hero_upgrade(state: GameState, hero_id: str, chosen_card_id: str):
    """
    Executes the upgrade transition for a hero.
    1. Removes old tier card of same color.
    2. Adds chosen card to hand.
    3. Tucks pair card as item.
    4. Decrements pending count.
    """
    hero = state.get_hero(HeroID(hero_id))
    if not hero:
        return

    chosen_card = next((c for c in hero.deck if c.id == chosen_card_id), None)
    if not chosen_card:
        print(f"   [!] Upgrade Error: Chosen card {chosen_card_id} not found in deck.")
        return

    prev_card = None
    if chosen_card.tier != CardTier.IV:
        for c in hero.hand:
            if c.color == chosen_card.color:
                prev_card = c
                break

    pair_card = None
    if chosen_card.tier != CardTier.IV:
        pair_card = next(
            (
                c
                for c in hero.deck
                if c.color == chosen_card.color
                and c.tier == chosen_card.tier
                and c.id != chosen_card.id
            ),
            None,
        )

    if prev_card:
        print(
            f"   [UPGRADE] Removing {prev_card.id} (Tier {prev_card.tier.name}) from hand."
        )
        hero.hand.remove(prev_card)
        prev_card.state = CardState.RETIRED

    print(
        f"   [UPGRADE] Adding {chosen_card.id} (Tier {chosen_card.tier.name}) to hand."
    )
    chosen_card.state = CardState.HAND
    hero.hand.append(chosen_card)

    if pair_card:
        stat = pair_card.item
        if stat:
            hero.items[stat] = hero.items.get(stat, 0) + 1
            print(f"   [UPGRADE] Tucking {pair_card.id} as Item (+1 {stat.name}).")
        pair_card.state = CardState.ITEM

    if hero_id in state.pending_upgrades:
        state.pending_upgrades[HeroID(hero_id)] -= 1
        if state.pending_upgrades[HeroID(hero_id)] <= 0:
            del state.pending_upgrades[HeroID(hero_id)]


class RoundResetStep(GameStep):
    """Resets round state and transitions to Planning."""

    type: StepType = StepType.ROUND_RESET

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        state.round += 1
        state.turn = 1
        state.phase = GamePhase.PLANNING
        print(f"   [ROUND START] Round {state.round}, Turn {state.turn}")
        return StepResult(is_finished=True)


class ResolveUpgradesStep(GameStep):
    """
    Simultaneous Upgrade loop.
    Waits for players to finish their pending upgrades.
    """

    type: StepType = StepType.RESOLVE_UPGRADES

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if not state.pending_upgrades:
            print("   [PHASE] All upgrades complete.")
            return StepResult(is_finished=True, new_steps=[RoundResetStep()])

        broadcast_data = {}
        for h_id, count in state.pending_upgrades.items():
            options = self._get_upgrade_options(state, h_id)
            broadcast_data[str(h_id)] = {"remaining": count, "options": options}

        return StepResult(
            requires_input=True,
            input_request={
                "type": "UPGRADE_PHASE",
                "players": broadcast_data,
                "prompt": "Mandatory Upgrade Phase",
            },
        )

    def _get_upgrade_options(self, state: GameState, hero_id: str):
        """
        Returns upgrade options for a hero.

        Note: Ultimate cards (Tier IV) are handled separately - they unlock
        automatically at level 8, so they should never appear as upgrade options.
        """
        hero = state.get_hero(HeroID(hero_id))
        if not hero:
            return []
        non_basic_colors = [CardColor.RED, CardColor.BLUE, CardColor.GREEN]
        hand_non_basics = [c for c in hero.hand if c.color in non_basic_colors]
        if not hand_non_basics:
            return []

        tier_map = {CardTier.I: 1, CardTier.II: 2, CardTier.III: 3}
        min_tier_val = min(tier_map.get(c.tier, 99) for c in hand_non_basics)

        # If all cards are Tier III, there are no upgrade options.
        # Ultimate cards auto-activate at level 8 (handled in _level_up).
        if min_tier_val == 3:
            return []

        eligible_colors = [
            c.color for c in hand_non_basics if tier_map.get(c.tier) == min_tier_val
        ]
        next_tier_map = {1: CardTier.II, 2: CardTier.III}
        target_tier = next_tier_map.get(min_tier_val)
        if not target_tier:
            return []

        options = []
        for color in eligible_colors:
            pair = [
                c
                for c in hero.deck
                if c.color == color
                and c.tier == target_tier
                and c.state == CardState.DECK
            ]
            if len(pair) == 2:
                options.append(
                    {
                        "color": color,
                        "tier": target_tier,
                        "pair": [c.id for c in pair],
                        "card_details": [c.model_dump() for c in pair],
                    }
                )
        return options


class TriggerGameOverStep(GameStep):
    """
    Executes an immediate Game Over sequence.
    1. Sets winner and condition.
    2. Changes Phase to GAME_OVER.
    3. PURGES execution and input stacks to stop all gameplay.
    """

    type: StepType = StepType.TRIGGER_GAME_OVER
    winner: TeamColor
    condition: str

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        print(
            f"   [GAME OVER] Victory for {self.winner.name}! Reason: {self.condition}"
        )

        state.winner = self.winner
        state.victory_condition = self.condition
        state.phase = GamePhase.GAME_OVER

        # Hard Stop: Clear everything pending
        state.execution_stack.clear()
        state.input_stack.clear()

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
            print(f"   [EFFECT] Cancelled {cancelled_count} active effect(s)")

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
        shape = self.scope.shape
        if shape == Shape.GLOBAL:
            return True
        if shape == Shape.POINT:
            return hex == origin
        if shape == Shape.ADJACENT:
            return origin.distance(hex) == 1
        if shape == Shape.RADIUS:
            return origin.distance(hex) <= self.scope.range
        if shape == Shape.LINE:
            if self.scope.direction is None:
                return False
            return (
                origin.is_straight_line(hex)
                and origin.distance(hex) <= self.scope.range
            )
        if shape == Shape.ZONE:
            origin_zone = self._get_zone_for_hex(origin, state)
            target_zone = self._get_zone_for_hex(hex, state)
            if origin_zone is None or target_zone is None:
                return False
            return origin_zone == target_zone
        return False

    def _get_zone_for_hex(self, hex: "Hex", state: GameState) -> Optional[str]:
        for zone_id, zone in state.board.zones.items():
            if hex in zone.hexes:
                return zone_id
        return None


# Rebuild recursive models
MayRepeatOnceStep.model_rebuild()

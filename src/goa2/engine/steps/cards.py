"""Card resolution, discard, retrieval, upgrades, and economy steps."""

from __future__ import annotations

import logging
from typing import Any, cast

from goa2.domain.events import GameEvent, GameEventType
from goa2.domain.input import InputRequestType, create_input_request
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardContainerType,
    CardState,
    CardTier,
    GamePhase,
    StepType,
    TargetType,
    TeamColor,
)
from goa2.domain.models.enums import StatType
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, HeroID, UnitID
from goa2.engine.filters_hex import RangeFilter
from goa2.engine.filters_units import UnitTypeFilter
from goa2.engine.stats import get_computed_stat
from goa2.engine.steps.base import GameStep, StepResult

logger = logging.getLogger(__name__)


class DiscardCardStep(GameStep):
    """
    Forces a specific card to be discarded.
    """

    type: StepType = StepType.DISCARD_CARD
    card_id: str | None = None
    card_key: str | None = None
    hero_id: str | None = None
    hero_key: str | None = None
    source: CardContainerType = CardContainerType.HAND  # HAND or PLAYED

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.effects import CheckPassiveAbilitiesStep

        if self.should_skip(context):
            return StepResult(is_finished=True)

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

        # Find card in the specified source container
        if self.source == CardContainerType.HAND:
            target_card = next((c for c in hero.hand if c.id == c_id), None)
        elif self.source == CardContainerType.PLAYED:
            target_card = next(
                (c for c in hero.played_cards if c is not None and c.id == c_id), None
            )
        else:
            logger.debug(f"   [DISCARD] Unsupported source container: {self.source}")
            return StepResult(is_finished=True)

        if not target_card:
            logger.debug(f"   [DISCARD] Card {c_id} not found in {h_id}'s {self.source.value}.")
            return StepResult(is_finished=True)

        logger.debug(f"   [DISCARD] {h_id} discards {target_card.name}")
        hero.discard_card(target_card, from_hand=(self.source == CardContainerType.HAND))

        # Fire AFTER_CARD_DISCARD passive trigger for every discard.
        # Passives that only care about specific sources (e.g. Battle Fury, which
        # only triggers on discards of resolved cards) filter via discard_source.
        from goa2.domain.models.enums import PassiveTrigger

        context["discarded_card_id"] = target_card.id
        context["discarded_card_owner_id"] = str(h_id)
        context["discard_source"] = self.source.value
        return StepResult(
            is_finished=True,
            new_steps=[
                CheckPassiveAbilitiesStep(
                    trigger=PassiveTrigger.AFTER_CARD_DISCARD.value,
                    hero_id=str(h_id),
                )
            ],
        )


class ForceDiscardStep(GameStep):
    """
    Checks if a victim has cards.
    If YES: Spawns a SelectStep (for victim to choose) + DiscardCardStep.
    If NO: Completes successfully (no penalty).
    """

    type: StepType = StepType.FORCE_DISCARD
    victim_key: str

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.selection import SelectStep

        victim_id = context.get(self.victim_key)
        if not victim_id:
            return StepResult(is_finished=True)

        victim = state.get_hero(HeroID(str(victim_id)))
        if not victim:
            return StepResult(is_finished=True)

        if not victim.hand:
            logger.debug(f"   [EFFECT] {victim_id} has no cards to discard (Safe).")
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

    type: StepType = StepType.FORCE_DISCARD_OR_DEFEAT
    victim_key: str

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.combat import DefeatUnitStep
        from goa2.engine.steps.selection import SelectStep

        victim_id = context.get(self.victim_key)
        if not victim_id:
            return StepResult(is_finished=True)

        victim = state.get_hero(HeroID(str(victim_id)))
        if not victim:
            return StepResult(is_finished=True)

        if not victim.hand:
            logger.debug(f"   [EFFECT] {victim_id} has no cards to discard! DEFEATED!")
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


class ResolveCardTextStep(GameStep):
    """
    Placeholder for executing the specific Python script/logic associated with a card's text.
    In a full implementation, this would look up a registry using `card.effect_id`
    and execute the specific function/class for that card.
    """

    type: StepType = StepType.RESOLVE_CARD_TEXT
    card_id: str
    hero_id: str

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.combat import AttackSequenceStep
        from goa2.engine.steps.movement import MoveSequenceStep
        from goa2.engine.steps.utility import LogMessageStep

        hero = state.get_hero(HeroID(self.hero_id))
        if not hero or not hero.current_turn_card:
            return StepResult(is_finished=True)

        card = hero.current_turn_card

        # Set card ID in context for effect creation
        context["current_card_id"] = card.id

        logger.debug(
            f"   [SCRIPT] Executing logic for '{card.name}' (Effect: {card.current_effect_id})"
        )

        from goa2.engine.effects import CardEffectRegistry

        if card.current_effect_id is None:
            return StepResult(is_finished=True)

        effect = CardEffectRegistry.get(card.current_effect_id)

        if effect:
            # We must use a different variable name here or not declare `new_steps` again below
            effect_steps = effect.get_steps(state, hero, card)
            return StepResult(is_finished=True, new_steps=effect_steps)

        # Fallback to standard primary primitives if no specific script found
        if not card.current_primary_action:
            logger.debug("            > No custom script found and no primary action.")
            return StepResult(is_finished=True)

        logger.debug(
            f"            > No custom script found. Using standard {card.current_primary_action.name} logic."
        )

        # Declared here for the first time in this scope path
        steps_list: list[GameStep] = []

        if card.current_primary_action == ActionType.MOVEMENT:
            # MOVEMENT: Compute Total
            base_val = card.get_base_stat_value(StatType.MOVEMENT)
            total_val = get_computed_stat(state, UnitID(self.hero_id), StatType.MOVEMENT, base_val)
            steps_list.append(MoveSequenceStep(unit_id=self.hero_id, range_val=total_val))

        elif card.current_primary_action == ActionType.ATTACK:
            # ATTACK: Compute Damage & Range
            base_dmg = card.get_base_stat_value(StatType.ATTACK)
            total_dmg = get_computed_stat(state, UnitID(self.hero_id), StatType.ATTACK, base_dmg)

            base_rng = card.get_base_stat_value(StatType.RANGE)
            # Default Range is 1 if not specified (and get_base_stat_value returns 0 if None)
            if base_rng == 0:
                base_rng = 1
            total_rng = get_computed_stat(state, UnitID(self.hero_id), StatType.RANGE, base_rng)

            steps_list.append(AttackSequenceStep(damage=total_dmg, range_val=total_rng))

        elif card.current_primary_action == ActionType.DEFENSE:
            steps_list.append(LogMessageStep(message=f"{self.hero_id} Defends (Primary)."))
        elif card.current_primary_action == ActionType.SKILL:
            logger.debug(f"            > Skill '{card.name}' has no registered effect!")
            steps_list.append(LogMessageStep(message=f"Skill '{card.name}' did nothing."))

        return StepResult(is_finished=True, new_steps=steps_list)


class ResolveCardStep(GameStep):
    """
    Analyzes the active card and prompts the user to choose an Action.
    Spawns the appropriate logic steps based on the choice.
    """

    type: StepType = StepType.RESOLVE_CARD
    hero_id: str

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.combat import AttackSequenceStep
        from goa2.engine.steps.effects import CheckPassiveAbilitiesStep
        from goa2.engine.steps.markers import RemoveTokenStep
        from goa2.engine.steps.movement import (
            FastTravelSequenceStep,
            MoveSequenceStep,
            ResolvePreActionMovementStep,
        )
        from goa2.engine.steps.selection import MultiSelectStep
        from goa2.engine.steps.utility import ForEachStep, LogMessageStep, SetContextFlagStep

        hero = state.get_hero(HeroID(self.hero_id))
        if not hero or not hero.current_turn_card:
            return StepResult(is_finished=True)

        # If hero is off-board (didn't respawn), skip action
        if self.hero_id not in state.entity_locations:
            return StepResult(is_finished=True)

        card = hero.current_turn_card

        context["current_card_id"] = card.id
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
        def compute_option(act_type: ActionType, base_val: int | None) -> tuple[int, str]:
            # Default
            final_val = base_val or 0
            text_val = str(final_val) if base_val is not None else "-"

            # Map Action to Stat
            stat_type = None
            if act_type == ActionType.MOVEMENT:
                stat_type = StatType.MOVEMENT
            elif act_type == ActionType.ATTACK:
                stat_type = StatType.ATTACK
            elif act_type == ActionType.DEFENSE or act_type == ActionType.DEFENSE_SKILL:
                stat_type = StatType.DEFENSE

            if stat_type:
                final_val = get_computed_stat(state, UnitID(self.hero_id), stat_type, base_val or 0)
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
                c_val, c_text = compute_option(primary_action, card.current_primary_action_value)
                options.append(
                    {
                        "id": primary_action.name,
                        "type": primary_action,
                        "value": c_val,
                        "text": f"Primary: {primary_action.name} ({c_text})",
                    }
                )
        # DEFENSE_SKILL is shown as SKILL option
        elif primary_action == ActionType.DEFENSE_SKILL and is_action_available(ActionType.SKILL):
            c_val, c_text = compute_option(ActionType.SKILL, card.current_primary_action_value)
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
            choice_id = self.pending_input.get("selection")
            selected_opt = next((o for o in options if o["id"] == choice_id), None)

            if selected_opt:
                # Type safe access
                act_type = cast(ActionType, selected_opt["type"])
                val = cast(int, selected_opt["value"])
                # Determine if primary by checking the card itself
                is_primary = act_type == primary_action
                # DEFENSE_SKILL played as SKILL still uses primary effect
                if (
                    card.current_primary_action == ActionType.DEFENSE_SKILL
                    and act_type == ActionType.SKILL
                ):
                    is_primary = True

                logger.debug(f"   [CHOICE] Player selected {choice_id} ({act_type.name})")

                # Track current action type for effect origin tracking
                context["current_action_type"] = act_type

                # NOTE: Renamed local variable to avoid shadowing re-declaration if any
                steps_list: list[GameStep] = []

                # Check for BEFORE_* passive abilities based on action type.
                # BEFORE_ACTION always fires — primary, secondary, or HOLD —
                # in addition to any specific BEFORE_ATTACK/MOVEMENT/SKILL.
                from goa2.domain.models.enums import PassiveTrigger

                steps_list.append(
                    CheckPassiveAbilitiesStep(trigger=PassiveTrigger.BEFORE_ACTION.value)
                )

                specific_trigger = None
                if act_type == ActionType.ATTACK:
                    specific_trigger = PassiveTrigger.BEFORE_ATTACK
                elif act_type == ActionType.MOVEMENT:
                    specific_trigger = PassiveTrigger.BEFORE_MOVEMENT
                elif act_type == ActionType.SKILL:
                    specific_trigger = PassiveTrigger.BEFORE_SKILL

                if specific_trigger:
                    steps_list.append(CheckPassiveAbilitiesStep(trigger=specific_trigger.value))

                if is_primary:
                    steps_list.append(ResolvePreActionMovementStep(hero_id=self.hero_id))
                    steps_list.append(ResolveCardTextStep(card_id=card.id, hero_id=self.hero_id))
                else:
                    # Secondary: Standard Primitives
                    if act_type == ActionType.MOVEMENT:
                        steps_list.append(MoveSequenceStep(unit_id=self.hero_id, range_val=val))

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

                        steps_list.append(AttackSequenceStep(damage=val, range_val=total_rng))

                    elif act_type == ActionType.CLEAR:
                        hero_loc = state.entity_locations.get(BoardEntityID(self.hero_id))
                        if not hero_loc:
                            steps_list.append(
                                LogMessageStep(
                                    message=f"{self.hero_id} attempted clear but is not on board."
                                )
                            )
                        else:
                            steps_list.extend(
                                [
                                    MultiSelectStep(
                                        min_selections=0,
                                        max_selections=6,
                                        filters=[
                                            UnitTypeFilter(unit_type="TOKEN"),
                                            RangeFilter(max_range=1),
                                        ],
                                        output_key="clear_targets",
                                        target_type=TargetType.UNIT_OR_TOKEN,
                                        prompt="Select tokens to clear.",
                                    ),
                                    ForEachStep(
                                        list_key="clear_targets",
                                        item_key="target_id",
                                        steps_template=[RemoveTokenStep(token_key="target_id")],
                                    ),
                                ]
                            )
                    elif act_type == ActionType.HOLD:
                        steps_list.append(LogMessageStep(message=f"{self.hero_id} Holds."))

                    elif act_type == ActionType.DEFENSE:
                        # Should not happen as action, but valid in enum
                        steps_list.append(
                            LogMessageStep(message=f"{self.hero_id} Defends (Active).")
                        )

                # Add AFTER_ATTACK passive check for ALL attack actions
                if act_type == ActionType.ATTACK:
                    # Store attack info so passives can rebuild the effect
                    if is_primary and card.current_effect_id:
                        steps_list.append(
                            SetContextFlagStep(
                                key="attack_effect_id",
                                value=card.current_effect_id,
                            )
                        )
                        steps_list.append(SetContextFlagStep(key="attack_card_id", value=card.id))
                    steps_list.append(
                        CheckPassiveAbilitiesStep(trigger=PassiveTrigger.AFTER_ATTACK.value)
                    )

                # Add AFTER_BASIC_SKILL passive check for Gold/Silver SKILL cards
                if act_type == ActionType.SKILL and card.current_color in (
                    CardColor.GOLD,
                    CardColor.SILVER,
                ):
                    steps_list.append(
                        CheckPassiveAbilitiesStep(trigger=PassiveTrigger.AFTER_BASIC_SKILL.value)
                    )

                # Add AFTER_BASIC_ACTION passive check for basic card actions
                if card.is_basic and act_type in (
                    ActionType.ATTACK,
                    ActionType.MOVEMENT,
                    ActionType.SKILL,
                ):
                    steps_list.append(
                        SetContextFlagStep(key="basic_action_type", value=act_type.value)
                    )
                    steps_list.append(SetContextFlagStep(key="basic_action_value", value=val))
                    # Store range for attack repeats
                    if act_type == ActionType.ATTACK:
                        base_rng_ba = card.get_base_stat_value(StatType.RANGE)
                        if base_rng_ba == 0:
                            base_rng_ba = 1
                        total_rng_ba = get_computed_stat(
                            state,
                            UnitID(self.hero_id),
                            StatType.RANGE,
                            base_rng_ba,
                        )
                        steps_list.append(
                            SetContextFlagStep(key="basic_action_range", value=total_rng_ba)
                        )
                    # Store effect info for primary actions so passives can
                    # rebuild the full effect sequence (e.g. Blink Strike)
                    if is_primary and card.current_effect_id:
                        steps_list.append(
                            SetContextFlagStep(
                                key="basic_action_effect_id",
                                value=card.current_effect_id,
                            )
                        )
                        steps_list.append(
                            SetContextFlagStep(key="basic_action_card_id", value=card.id)
                        )
                    steps_list.append(
                        CheckPassiveAbilitiesStep(trigger=PassiveTrigger.AFTER_BASIC_ACTION.value)
                    )

                return StepResult(is_finished=True, new_steps=steps_list)

        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.CHOOSE_ACTION,
                player_id=self.hero_id,
                prompt=f"Choose action for card {card.name}",
                options=options,
            ),
        )


class SwapCardStep(GameStep):
    """
    Swaps the Hero's current turn card with another card (specified by ID or key).
    """

    type: StepType = StepType.SWAP_CARD
    target_card_id: str | None = None
    target_card_key: str | None = None  # Key in context to find ID
    context_hero_id_key: str | None = None  # Key in context to find Hero ID

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
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
            logger.debug("   [SWAP] No target card specified for swap.")
            return StepResult(is_finished=True)

        # Find the card object
        # We need to search Hand, Discard, Played
        # Simplest is to check all or use a helper, but Hero methods work on objects.
        target_card: Card | None = None
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
            for played_card in hero.played_cards:
                if played_card is not None and played_card.id == t_id:
                    target_card = played_card
                    break

        if not target_card:
            logger.debug(f"   [SWAP] Target card {t_id} not found in {hero_id}'s possession.")
            return StepResult(is_finished=True)

        logger.debug(
            f"   [SWAP] Swapping {hero.id}'s current card {hero.current_turn_card.name} with {target_card.name}"
        )
        hero.swap_cards(hero.current_turn_card, target_card)

        # NOTE: After swapping, the "current_turn_card" has changed!
        # This might affect subsequent steps if they rely on "current_card_id" in context.
        # But usually context has the old ID if it was set earlier.
        # Ideally, we should update context if necessary, but "current_card_id" is usually set once at start of ResolveCardText.

        return StepResult(is_finished=True)


class RetrieveCardStep(GameStep):
    """
    Retrieves a card from discard pile back to hand.
    Uses context[card_key] for the card ID.
    If hero_key is set, looks up the hero ID from context; otherwise uses
    current_actor_id.
    """

    type: StepType = StepType.RETRIEVE_CARD
    card_key: str
    hero_key: str | None = None

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        card_id = context.get(self.card_key)
        if not card_id:
            return StepResult(is_finished=True)

        # Determine which hero retrieves the card
        if self.hero_key:
            hero_id_str = context.get(self.hero_key)
            if not hero_id_str:
                return StepResult(is_finished=True)
            actor_id = hero_id_str
        else:
            actor_id = state.current_actor_id
            if not actor_id:
                return StepResult(is_finished=True)

        hero = state.get_hero(HeroID(str(actor_id)))
        if not hero:
            return StepResult(is_finished=True)

        # Find card in played_cards or discard_pile
        target_card = next(
            (c for c in hero.played_cards if c is not None and c.id == card_id),
            None,
        )
        source = "played"
        if not target_card:
            target_card = next((c for c in hero.discard_pile if c.id == card_id), None)
            source = "discard"
        if not target_card:
            logger.debug(
                f"   [RETRIEVE] Card {card_id} not found in {actor_id}'s played or discard."
            )
            return StepResult(is_finished=True)

        hero.return_card_to_hand(target_card)
        logger.debug(f"   [RETRIEVE] {actor_id} retrieved {target_card.name} from {source}.")

        event = GameEvent(
            event_type=GameEventType.CARD_RETRIEVED,
            actor_id=str(actor_id),
            metadata={"card_id": card_id, "card_name": target_card.name},
        )
        return StepResult(is_finished=True, events=[event])


class CountCardsStep(GameStep):
    """
    Counts cards in a hero's container (hand, discard, deck, played)
    and stores the count in context[output_key].
    """

    type: StepType = StepType.COUNT_CARDS
    hero_id: str | None = None
    hero_key: str | None = None
    card_container: CardContainerType = CardContainerType.DISCARD
    output_key: str = "card_count"

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            context[self.output_key] = 0
            return StepResult(is_finished=True)

        h_id = self.hero_id
        if not h_id and self.hero_key:
            h_id = context.get(self.hero_key)
        if not h_id:
            h_id = state.current_actor_id

        if not h_id:
            context[self.output_key] = 0
            return StepResult(is_finished=True)

        hero = state.get_hero(HeroID(str(h_id)))
        if not hero:
            context[self.output_key] = 0
            return StepResult(is_finished=True)

        if self.card_container == CardContainerType.HAND:
            count = len(hero.hand)
        elif self.card_container == CardContainerType.DISCARD:
            count = len(hero.discard_pile)
        elif self.card_container == CardContainerType.DECK:
            count = len(hero.deck)
        elif self.card_container == CardContainerType.PLAYED:
            count = len([c for c in hero.played_cards if c is not None])
        else:
            count = 0

        context[self.output_key] = count
        logger.debug(f"   [COUNT_CARDS] {h_id} {self.card_container.value}: {count}")
        return StepResult(is_finished=True)


class GainCoinsStep(GameStep):
    """Grants gold to a hero identified by a context key."""

    type: StepType = StepType.GAIN_COINS
    hero_key: str  # context key → hero ID
    amount: int = 0  # static amount
    amount_key: str = ""  # context key → dynamic amount (overrides static)

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)
        hero_id = context.get(self.hero_key)
        if not hero_id:
            return StepResult(is_finished=True)
        hero = state.get_hero(HeroID(str(hero_id)))
        if not hero:
            return StepResult(is_finished=True)
        coins = context.get(self.amount_key, self.amount) if self.amount_key else self.amount
        hero.gold += coins
        logger.debug(f"   [COINS] {hero_id} gains {coins} gold")
        return StepResult(
            is_finished=True,
            events=[
                GameEvent(
                    event_type=GameEventType.GOLD_GAINED,
                    actor_id=str(hero_id),
                    metadata={"amount": coins, "reason": "effect"},
                )
            ],
        )


class GainItemStep(GameStep):
    """Grants a stat item to a hero identified by a context key."""

    type: StepType = StepType.GAIN_ITEM
    hero_key: str  # context key → hero ID
    stat_type: StatType  # which stat to boost
    amount: int = 1

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)
        hero_id = context.get(self.hero_key)
        if not hero_id:
            return StepResult(is_finished=True)
        hero = state.get_hero(HeroID(str(hero_id)))
        if not hero:
            return StepResult(is_finished=True)
        hero.items[self.stat_type] = hero.items.get(self.stat_type, 0) + self.amount
        logger.debug(f"   [ITEM] {hero_id} gains +{self.amount} {self.stat_type.name} item")
        return StepResult(
            is_finished=True,
            events=[
                GameEvent(
                    event_type=GameEventType.ITEM_GAINED,
                    actor_id=str(hero_id),
                    metadata={
                        "stat_type": self.stat_type.value,
                        "amount": self.amount,
                    },
                )
            ],
        )


class StealCoinsStep(GameStep):
    """Takes coins from an enemy hero and gives them to the current actor."""

    type: StepType = StepType.STEAL_COINS
    victim_key: str  # context key → enemy hero ID
    amount: int = 1  # static amount to steal
    amount_key: str = ""  # context key → dynamic amount (overrides static)
    output_key: str = ""  # if set, stores True in context when coins were stolen

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        victim_id = context.get(self.victim_key)
        if not victim_id:
            return StepResult(is_finished=True)

        victim = state.get_hero(HeroID(str(victim_id)))
        if not victim:
            return StepResult(is_finished=True)

        actor_id = context.get("current_actor_id") or state.current_actor_id
        actor = state.get_hero(HeroID(str(actor_id)))
        if not actor:
            return StepResult(is_finished=True)

        coins_requested = (
            context.get(self.amount_key, self.amount) if self.amount_key else self.amount
        )
        actual_stolen = min(coins_requested, victim.gold)

        if actual_stolen <= 0:
            return StepResult(is_finished=True)

        victim.gold -= actual_stolen
        actor.gold += actual_stolen
        if self.output_key:
            context[self.output_key] = True
        logger.debug(f"   [STEAL] {actor_id} steals {actual_stolen} coin(s) from {victim_id}")
        return StepResult(
            is_finished=True,
            events=[
                GameEvent(
                    event_type=GameEventType.GOLD_GAINED,
                    actor_id=str(actor_id),
                    target_id=str(victim_id),
                    metadata={"amount": actual_stolen, "reason": "steal"},
                ),
            ],
        )


class PerformPrimaryActionStep(GameStep):
    """
    Looks up a card from context, computes its stats, calls its effect's
    build_steps(), and pushes the resulting steps onto the stack.

    Used by Ursafar's Angry Roar, Instinctive Reaction, Evolutionary Response.
    """

    type: StepType = StepType.PERFORM_PRIMARY_ACTION
    card_key: str = "selected_card"
    hero_id: str | None = None

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        card_id = context.get(self.card_key)
        if not card_id:
            return StepResult(is_finished=True)

        actor_id = self.hero_id or (str(state.current_actor_id) if state.current_actor_id else None)
        if not actor_id:
            return StepResult(is_finished=True)

        hero = state.get_hero(HeroID(str(actor_id)))
        if not hero:
            return StepResult(is_finished=True)

        # Find the card anywhere on the hero (played, discard, hand, deck)
        card = None
        for c in hero.played_cards + hero.discard_pile + hero.hand + hero.deck:
            if c is not None and c.id == card_id:
                card = c
                break

        if not card or not card.current_effect_id:
            logger.debug(f"   [PERFORM] Card {card_id} not found or has no effect.")
            return StepResult(is_finished=True)

        from goa2.engine.effects import CardEffectRegistry
        from goa2.engine.stats import compute_card_stats

        effect = CardEffectRegistry.get(card.current_effect_id)
        if not effect:
            logger.debug(f"   [PERFORM] No effect registered for {card.current_effect_id}.")
            return StepResult(is_finished=True)

        stats = compute_card_stats(state, UnitID(str(actor_id)), card)
        steps = effect.build_steps(state, hero, card, stats)

        logger.debug(
            f"   [PERFORM] Performing primary action of {card.name} " f"({len(steps)} steps)"
        )
        return StepResult(is_finished=True, new_steps=steps)


class ConvertCardToItemStep(GameStep):
    """Converts a selected card into a permanent item for its owner hero.

    Reads a card ID from context[card_key], finds it in the hero's deck,
    increments hero.items[card.item], and sets card.state = CardState.ITEM.
    """

    type: StepType = StepType.CONVERT_CARD_TO_ITEM
    card_key: str  # context key → card ID
    hero_id: str = ""  # explicit hero ID (if empty, uses current actor)

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        card_id = context.get(self.card_key)
        if not card_id:
            return StepResult(is_finished=True)

        actor_id = self.hero_id or state.current_actor_id
        hero = state.get_hero(HeroID(str(actor_id)))
        if not hero:
            return StepResult(is_finished=True)

        card = next((c for c in hero.deck if c.id == str(card_id)), None)
        if not card:
            logger.debug(f"   [CONVERT] Card {card_id} not found in {actor_id} deck")
            return StepResult(is_finished=True)

        stat = card.item
        if not stat:
            logger.debug(f"   [CONVERT] Card {card_id} has no item stat")
            return StepResult(is_finished=True)

        hero.items[stat] = hero.items.get(stat, 0) + 1
        card.state = CardState.ITEM
        logger.debug(f"   [CONVERT] {card.name} → permanent item (+1 {stat.name})")

        return StepResult(
            is_finished=True,
            events=[
                GameEvent(
                    event_type=GameEventType.ITEM_GAINED,
                    actor_id=str(actor_id),
                    metadata={
                        "stat_type": stat.value,
                        "amount": 1,
                        "source_card_id": card.id,
                    },
                )
            ],
        )


class ResolveUpgradesStep(GameStep):
    """
    Simultaneous Upgrade loop.
    Waits for players to finish their pending upgrades.
    """

    type: StepType = StepType.RESOLVE_UPGRADES

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        # Process input if provided
        if self.pending_input:
            selection = self.pending_input.get("selection")
            if isinstance(selection, dict):
                hero_id = selection.get("hero_id")
                card_id = selection.get("card_id")
                if hero_id and card_id:
                    apply_hero_upgrade(state, hero_id, card_id)
            self.pending_input = None

        if not state.pending_upgrades:
            logger.debug("   [PHASE] All upgrades complete.")
            return StepResult(is_finished=True, new_steps=[RoundResetStep()])

        broadcast_data = {}
        for h_id, count in state.pending_upgrades.items():
            options = self._get_upgrade_options(state, h_id)
            broadcast_data[str(h_id)] = {"remaining": count, "options": options}

        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.UPGRADE_PHASE,
                player_id="simultaneous",
                prompt="Mandatory Upgrade Phase",
                players=broadcast_data,
            ),
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

        eligible_colors = [c.color for c in hand_non_basics if tier_map.get(c.tier) == min_tier_val]
        next_tier_map = {1: CardTier.II, 2: CardTier.III}
        target_tier = next_tier_map.get(min_tier_val)
        if not target_tier:
            return []

        options = []
        for color in eligible_colors:
            pair = [
                c
                for c in hero.deck
                if c.color == color and c.tier == target_tier and c.state == CardState.DECK
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


class RoundResetStep(GameStep):
    """Resets round state and transitions to Planning."""

    type: StepType = StepType.ROUND_RESET

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        state.round += 1
        state.turn = 1
        state.phase = GamePhase.PLANNING
        state.heroes_defeated_this_round.clear()
        logger.debug(f"   [ROUND START] Round {state.round}, Turn {state.turn}")
        return StepResult(is_finished=True)


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
        logger.debug(f"   [!] Upgrade Error: Chosen card {chosen_card_id} not found in deck.")
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
        logger.debug(
            f"   [UPGRADE] Removing {prev_card.id} (Tier {prev_card.tier.name}) from hand."
        )
        hero.hand.remove(prev_card)
        prev_card.state = CardState.RETIRED

    logger.debug(f"   [UPGRADE] Adding {chosen_card.id} (Tier {chosen_card.tier.name}) to hand.")
    chosen_card.state = CardState.HAND
    chosen_card.is_facedown = False
    hero.hand.append(chosen_card)

    if pair_card:
        stat = pair_card.item
        if stat:
            hero.items[stat] = hero.items.get(stat, 0) + 1
            logger.debug(f"   [UPGRADE] Tucking {pair_card.id} as Item (+1 {stat.name}).")
        pair_card.state = CardState.ITEM

    if hero_id in state.pending_upgrades:
        state.pending_upgrades[HeroID(hero_id)] -= 1
        if state.pending_upgrades[HeroID(hero_id)] <= 0:
            del state.pending_upgrades[HeroID(hero_id)]


def _one_man_army_bonus(state: GameState, zone) -> dict[TeamColor, int]:
    """Check for heroes with active one_man_army ultimate in the zone."""
    bonus = {TeamColor.RED: 0, TeamColor.BLUE: 0}
    for team in state.teams.values():
        for hero in team.heroes:
            if hero.level < 8 or not hero.ultimate_card:
                continue
            if hero.ultimate_card.effect_id != "one_man_army":
                continue
            hero_loc = state.entity_locations.get(hero.id)
            if hero_loc and hero_loc in zone.hexes and hero.team is not None:
                bonus[hero.team] += 1
                logger.debug(f"   [BATTLE] {hero.name} counts as a heavy minion (One Man Army)")
    return bonus

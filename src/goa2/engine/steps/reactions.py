"""Reaction window, defense text, and on-block effect steps."""

from __future__ import annotations

import logging
from typing import Any

from goa2.domain.input import InputOption, InputRequestType, create_input_request
from goa2.domain.models import ActionType, StepType
from goa2.domain.models.enums import StatType
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.engine.stats import get_computed_stat
from goa2.engine.steps.base import GameStep, StepResult

logger = logging.getLogger(__name__)


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

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        target_id = context.get(self.target_player_key)
        if not target_id:
            return StepResult(is_finished=True)  # Should not happen

        target_hero = state.get_hero(target_id)

        # Optimization: Minions/Non-Heroes cannot react.
        if not target_hero:
            logger.debug(f"   [REACTION] Target {target_id} is not a hero. Skipping reaction.")
            context["defense_value"] = None
            context["defense_card_id"] = None
            context["defender_id"] = str(target_id)
            context["is_primary_defense"] = False
            return StepResult(is_finished=True)

        block_primary = context.get("block_primary_defense", False)

        valid_defense_cards = []
        for card in target_hero.hand:
            is_primary_def = card.current_primary_action in (
                ActionType.DEFENSE,
                ActionType.DEFENSE_SKILL,
            )
            has_secondary_def = ActionType.DEFENSE in card.current_secondary_actions

            if block_primary and is_primary_def and not has_secondary_def:
                # Card only usable as primary defense — blocked
                continue

            if is_primary_def or has_secondary_def:
                valid_defense_cards.append(card)

        [c.id for c in valid_defense_cards]

        # Build InputOption objects with computed defense values
        options = []
        for card in valid_defense_cards:
            base_def = card.get_base_stat_value(StatType.DEFENSE)
            total_def = get_computed_stat(state, target_id, StatType.DEFENSE, base_def)
            options.append(
                InputOption(
                    id=card.id,
                    text=f"{card.name} (Def: {total_def})",
                    metadata={"defense_value": total_def, "base_defense": base_def},
                )
            )
        options.append(InputOption(id="PASS", text="PASS"))

        if self.pending_input:
            card_id = self.pending_input.get("selection")

            # Case A: PASS
            if card_id == "PASS":
                logger.debug(f"   [REACTION] Player {target_id} Passed (No Defense).")
                context["defense_value"] = None
                context["defense_card_id"] = None
                context["defender_id"] = str(target_id)
                context["is_primary_defense"] = False
                return StepResult(is_finished=True)

            # Case B: Selected Card
            if card_id:
                def_val = 0
                selected_card = next((c for c in valid_defense_cards if c.id == card_id), None)

                # Get Base Value
                if selected_card:
                    def_val = selected_card.get_base_stat_value(StatType.DEFENSE)
                elif not selected_card:
                    raise ValueError("Selected card is not a valid defense card.")

                # Compute Total Defense (Base + Items + Modifiers)
                total_def = get_computed_stat(state, target_id, StatType.DEFENSE, def_val)

                # Determine if primary defense (triggers effect text)
                # block_primary_defense forces all cards to secondary-only
                is_primary = not block_primary and selected_card.current_primary_action in (
                    ActionType.DEFENSE,
                    ActionType.DEFENSE_SKILL,
                )

                # Discard the defense card from hand
                target_hero.discard_card(selected_card, from_hand=True)

                logger.debug(
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

        # Compute combat info for the input request
        from goa2.engine.stats import calculate_minion_defense_modifier

        attack_value = context.get("attack_damage")
        minion_modifier = calculate_minion_defense_modifier(state, target_id)
        defense_needed = (attack_value - minion_modifier) if attack_value is not None else None

        prompt = f"Player {target_id}, select a Defense card."
        if attack_value is not None:
            prompt = (
                f"Player {target_id}, select a Defense card. "
                f"Attack: {attack_value}, Defense needed: {defense_needed} "
                f"(minion mod: {minion_modifier:+d})"
            )

        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_CARD_OR_PASS,
                player_id=str(target_id),
                prompt=prompt,
                options=options,
                attack_value=attack_value,
                minion_modifier=minion_modifier,
                defense_needed=defense_needed,
            ),
        )


class ResolveDefenseTextStep(GameStep):
    """
    Resolves defense card effect text for primary DEFENSE cards.
    Analogous to ResolveCardTextStep for offense.

    Only triggers for cards where primary_action == DEFENSE.
    For DEFENSE_SKILL cards, falls back to get_steps() if get_defense_steps() returns None.
    """

    type: StepType = StepType.RESOLVE_DEFENSE_TEXT

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.utility import SetActorStep

        card_id = context.get("defense_card_id")
        defender_id = context.get("defender_id")
        is_primary = context.get("is_primary_defense", False)

        logger.debug(
            f"   [DEFENSE TEXT] card_id={card_id}, defender_id={defender_id}, is_primary={is_primary}"
        )

        # Only trigger effects for primary DEFENSE
        if not card_id or not is_primary or not defender_id:
            logger.debug("   [DEFENSE] No primary defense card - skipping effect resolution.")
            return StepResult(is_finished=True)

        defender = state.get_hero(HeroID(str(defender_id)))
        if not defender:
            return StepResult(is_finished=True)

        # Find the card in defender's hand (defense cards are moved to discard after ReactionWindowStep)
        card = next((c for c in defender.hand if c.id == card_id), None)

        # If not in hand, check discard pile
        if not card:
            card = next((c for c in defender.discard_pile if c.id == card_id), None)

        if not card or not card.current_effect_id:
            logger.debug(f"   [DEFENSE] Card {card_id} has no effect_id - using standard defense.")
            return StepResult(is_finished=True)

        logger.debug(f"   [DEFENSE] Looking up effect_id={card.current_effect_id}")

        from goa2.engine.effects import CardEffectRegistry

        effect = CardEffectRegistry.get(card.current_effect_id)
        if effect:
            # Try defense-specific steps first
            defense_steps = effect.get_defense_steps(state, defender, card, context)

            # If None, fall back to get_steps() (for DEFENSE_SKILL cards)
            if defense_steps is None:
                logger.debug(
                    f"   [DEFENSE] Using get_steps() fallback for {card.current_effect_id}"
                )
                defense_steps = effect.get_steps(state, defender, card)

            if defense_steps:
                logger.debug(
                    f"   [DEFENSE] Executing {len(defense_steps)} defense effect steps for {card.current_effect_id}"
                )
                # Wrap steps so current_actor_id is the defender during execution
                wrapped = [
                    SetActorStep(actor_key="defender_id", save_key="_pre_defense_actor"),
                    *defense_steps,
                    SetActorStep(actor_key="_pre_defense_actor", save_key="_discard"),
                ]
                return StepResult(is_finished=True, new_steps=wrapped)
            else:
                if not defense_steps:
                    logger.debug(
                        f"   [DEFENSE] defense_steps is None/empty for {card.current_effect_id}"
                    )
                else:
                    logger.debug(
                        f"   [DEFENSE] No defense_steps returned for {card.current_effect_id}"
                    )

        return StepResult(is_finished=True)


class ResolveOnBlockEffectStep(GameStep):
    """
    Runs 'if you do' effects after a successful block.
    Only called if the defense succeeded (block_succeeded=True in context).

    Example: Wasp's Reflect Projectiles - "if you do, enemy hero discards"
    """

    type: StepType = StepType.RESOLVE_ON_BLOCK_EFFECT

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.utility import SetActorStep

        if not context.get("block_succeeded"):
            logger.debug("   [ON_BLOCK] Block did not succeed - skipping on_block effects.")
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

        if not card or not card.current_effect_id:
            return StepResult(is_finished=True)

        from goa2.engine.effects import CardEffectRegistry

        effect = CardEffectRegistry.get(card.current_effect_id)
        if effect:
            on_block_steps = effect.get_on_block_steps(state, defender, card, context)
            if on_block_steps:
                logger.debug(
                    f"   [ON_BLOCK] Executing {len(on_block_steps)} on_block effect steps for {card.current_effect_id}"
                )
                # Wrap steps so current_actor_id is the defender during execution
                wrapped = [
                    SetActorStep(actor_key="defender_id", save_key="_pre_onblock_actor"),
                    *on_block_steps,
                    SetActorStep(actor_key="_pre_onblock_actor", save_key="_discard"),
                ]
                return StepResult(is_finished=True, new_steps=wrapped)

        return StepResult(is_finished=True)


class ConfirmResolutionStep(GameStep):
    """
    Prompts the acting player to confirm their resolution or rollback.
    Auto-confirms when rollback is disabled (another player was prompted during this turn).
    """

    type: StepType = StepType.CONFIRM_RESOLUTION
    hero_id: str

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        # Auto-confirm when rollback is disabled
        if context.get("rollback_disabled"):
            return StepResult(is_finished=True)

        if self.pending_input:
            # Both CONFIRM and ROLLBACK just finish this step.
            # Rollback is handled via the dedicated endpoint/message, not through input.
            return StepResult(is_finished=True)

        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.CHOOSE_ACTION,
                player_id=self.hero_id,
                prompt="Confirm your action or rollback to choose again.",
                options=[
                    {"id": "CONFIRM", "text": "Confirm"},
                    {"id": "ROLLBACK", "text": "Rollback"},
                ],
            ),
        )

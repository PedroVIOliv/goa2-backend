"""Attack sequence, combat resolution, defeat, respawn, and lane push steps."""

from __future__ import annotations

import logging
from typing import Any, cast

from pydantic import Field

from goa2.domain.events import GameEvent, GameEventType, _hex_dict
from goa2.domain.hex import Hex
from goa2.domain.input import InputOption, InputRequestType, create_input_request
from goa2.domain.models import GamePhase, Hero, StepType, TargetType, TeamColor, Token
from goa2.domain.models.effect import EffectType
from goa2.domain.models.marker import MarkerType
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, HeroID, UnitID
from goa2.engine.effect_manager import EffectManager
from goa2.engine.filters_base import FilterCondition
from goa2.engine.filters_hex import RangeFilter
from goa2.engine.steps.base import GameStep, StepResult

logger = logging.getLogger(__name__)


class AttackSequenceStep(GameStep):
    """
    Composite Step.
    Expands into: Select Target -> Reaction Window -> Defense Effect -> Resolve Combat -> On Block Effect.

    Stores in context for defense effect resolution:
    - attack_is_ranged: True if is_ranged=True
    - attacker_id: The ID of the attacking unit

    If target_id_key is provided, assumes target is already selected in context and skips selection.
    If target_filters is provided, adds those filters to the target selection.
    """

    type: StepType = StepType.ATTACK_SEQUENCE
    damage: int
    range_val: int = 1
    is_ranged: bool = False
    target_id_key: str | None = None  # Optional: Use existing context key instead of selecting
    target_filters: list[FilterCondition] = Field(
        default_factory=list
    )  # Additional filters for target selection
    damage_bonus_key: str | None = None  # Add int from context to damage
    range_bonus_key: str | None = None  # Add int from context to range_val

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.effects import CheckPassiveAbilitiesStep
        from goa2.engine.steps.movement import ResolvePreActionMovementStep
        from goa2.engine.steps.phases import RestoreActionTypeStep
        from goa2.engine.steps.reactions import (
            ReactionWindowStep,
            ResolveDefenseTextStep,
            ResolveOnBlockEffectStep,
        )
        from goa2.engine.steps.selection import SelectStep
        from goa2.engine.steps.utility import SetActorStep

        if self.should_skip(context):
            return StepResult(is_finished=True)

        # Apply dynamic bonuses from context
        effective_damage = (
            self.damage + int(context.get(self.damage_bonus_key, 0))
            if self.damage_bonus_key
            else self.damage
        )
        effective_range = (
            self.range_val + int(context.get(self.range_bonus_key, 0))
            if self.range_bonus_key
            else self.range_val
        )

        logger.debug(
            f"   [MACRO] Expanding Attack Sequence (Dmg: {effective_damage}, Rng: {effective_range})"
        )

        from goa2.engine.filters_units import TeamFilter

        key = self.target_id_key if self.target_id_key else "victim_id"

        # Store attack context for defense effect resolution
        context["attack_is_ranged"] = self.is_ranged
        context["attacker_id"] = str(state.current_actor_id) if state.current_actor_id else None
        context["attack_damage"] = effective_damage
        logger.debug(
            f"   [ATTACK SEQ] Set attack_is_ranged={context['attack_is_ranged']}, is_ranged={self.is_ranged}, range_val={effective_range}"
        )

        new_steps: list[GameStep] = []

        # Only spawn selection if we don't have a pre-selected key or if the key is not already set in context
        if not self.target_id_key or key not in context:
            # Base filters + any custom target_filters
            all_filters: list[FilterCondition] = [
                RangeFilter(max_range=effective_range),
                TeamFilter(relation="ENEMY"),
            ]
            all_filters.extend(self.target_filters)

            new_steps.append(
                SelectStep(
                    target_type=TargetType.UNIT,
                    prompt="Select Attack Target",
                    output_key=key,
                    filters=all_filters,
                    is_mandatory=self.is_mandatory,
                )
            )

        from goa2.domain.models.enums import PassiveTrigger as _PT

        new_steps.extend(
            [
                ReactionWindowStep(target_player_key=key),
                SetActorStep(actor_key="defender_id", save_key="_pre_pam_actor"),
                CheckPassiveAbilitiesStep(trigger=_PT.BEFORE_ACTION.value),
                ResolvePreActionMovementStep(hero_key="defender_id"),
                SetActorStep(actor_key="_pre_pam_actor", save_key="_discard_pam"),
                ResolveDefenseTextStep(),
                ResolveCombatStep(damage=effective_damage, target_key=key),
                ResolveOnBlockEffectStep(),
                RestoreActionTypeStep(),
            ]
        )

        return StepResult(is_finished=True, new_steps=new_steps)


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

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        target_id = context.get(self.target_key)
        if not target_id:
            logger.debug("[COMBAT] No target selected. Combat cancelled.")
            context["block_succeeded"] = False
            return StepResult(is_finished=True)

        # Store under a standard key so passives can reference the combat target
        # regardless of what custom key the effect used (e.g. "blink_victim")
        context["last_combat_target"] = target_id

        defense_card_val = context.get("defense_value")
        attack_val = self.damage
        actor_id = state.current_actor_id

        def _combat_event(outcome: str, defense: int | None = None, modifier: int = 0) -> GameEvent:
            return GameEvent(
                event_type=GameEventType.COMBAT_RESOLVED,
                actor_id=str(actor_id) if actor_id else None,
                target_id=target_id,
                metadata={
                    "attack_value": attack_val,
                    "defense_value": defense,
                    "modifier_value": modifier,
                    "outcome": outcome,
                },
            )

        logger.debug(
            f"   [COMBAT] Checking context flags: auto_block={context.get('auto_block')}, defense_invalid={context.get('defense_invalid')}"
        )

        # Check for defense_invalid (e.g., stop_projectiles vs melee attack)
        if context.get("defense_invalid"):
            logger.debug(
                "   [COMBAT] Defense is invalid (conditions not met) - treating as no defense."
            )
            context["block_succeeded"] = False
            return StepResult(
                is_finished=True,
                new_steps=[DefeatUnitStep(victim_id=target_id, killer_id=actor_id)],
                events=[_combat_event("DEFEATED")],
            )

        # Check for auto_block (e.g., stop_projectiles vs ranged attack)
        if context.get("auto_block"):
            logger.debug(f"   [COMBAT] Auto-block triggered! {target_id} is safe.")
            context["block_succeeded"] = True
            return StepResult(
                is_finished=True,
                events=[_combat_event("BLOCKED")],
            )

        # Calculate Passive Modifiers (unless ignored by defense effect)
        from goa2.engine.stats import calculate_minion_defense_modifier

        mod_val: int
        if context.get("ignore_minion_defense"):
            mod_val = 0
            logger.debug("   [COMBAT] Ignoring minion defense modifiers (effect active).")
        else:
            cached_mod = context.get("minion_defense_modifier")
            if cached_mod is None:
                mod_val = calculate_minion_defense_modifier(state, target_id)
            else:
                mod_val = cached_mod
        if defense_card_val is None:
            # No defense played (minion or passed) - unit is defeated
            logger.debug(f"   [RESULT] No defense! {target_id} is DEFEATED!")
            context["block_succeeded"] = False
            return StepResult(
                is_finished=True,
                new_steps=[DefeatUnitStep(victim_id=target_id, killer_id=actor_id)],
                events=[_combat_event("DEFEATED")],
            )
        defense_bonus = int(context.get("defense_bonus", 0))
        total_defense = defense_card_val + defense_bonus + mod_val

        logger.debug(
            f"   [COMBAT] Attack ({attack_val}) vs Defense "
            f"({defense_card_val} Card + {defense_bonus} Bonus + {mod_val} Mod = {total_defense})"
        )

        if total_defense >= attack_val:
            logger.debug(f"   [RESULT] Attack BLOCKED! {target_id} is safe.")
            context["block_succeeded"] = True
            return StepResult(
                is_finished=True,
                events=[_combat_event("BLOCKED", defense_card_val, mod_val)],
            )
        else:
            logger.debug(f"   [RESULT] Attack HITS! {target_id} is DEFEATED!")
            context["block_succeeded"] = False
            return StepResult(
                is_finished=True,
                new_steps=[DefeatUnitStep(victim_id=target_id, killer_id=actor_id)],
                events=[_combat_event("DEFEATED", defense_card_val, mod_val)],
            )


class RemoveUnitStep(GameStep):
    """
    Purely removes a unit from the board.
    Does NOT grant rewards. Used by 'Remove' effects and as a sub-step of Defeat.
    """

    type: StepType = StepType.REMOVE_UNIT
    unit_id: str | None = None
    unit_key: str | None = None  # Read unit ID from context

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        target_id = self.unit_id
        if self.unit_key:
            target_id = context.get(self.unit_key)
        if not target_id:
            return StepResult(is_finished=True)

        logger.debug(f"   [LOGIC] Removing {target_id} from board.")
        from_hex = state.entity_locations.get(BoardEntityID(target_id))
        state.remove_unit(UnitID(target_id))
        return StepResult(
            is_finished=True,
            new_steps=[CheckLanePushStep()],
            events=[
                GameEvent(
                    event_type=GameEventType.UNIT_REMOVED,
                    target_id=target_id,
                    from_hex=_hex_dict(from_hex),
                )
            ],
        )


class DefeatUnitStep(GameStep):
    """
    Processes the defeat of a unit (Combat/Skill Kill):
    1. Awards Gold (Killer + Assists).
    2. Updates Life Counters (if Hero).
    3. Returns markers from/to the defeated unit.
    4. Spawns RemoveUnitStep.
    """

    type: StepType = StepType.DEFEAT_UNIT
    victim_id: str | None = None  # Direct ID
    victim_key: str | None = None  # Context key for victim ID
    killer_id: str | None = None
    assist_multiplier: int = 1  # Multiplier for assist coins (e.g. 3 for Glorious Triumph)

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        # Resolve victim_id from key if needed
        actual_victim_id = self.victim_id
        if not actual_victim_id and self.victim_key:
            actual_victim_id = context.get(self.victim_key)

        if not actual_victim_id:
            return StepResult(is_finished=True)  # Nothing to defeat

        logger.debug(f"   [DEATH] Processing Defeat of {actual_victim_id}...")

        victim = state.get_unit(UnitID(actual_victim_id))
        if not victim:
            raise ValueError(f"Cannot defeat unknown unit: {actual_victim_id}")

        killer = state.get_unit(UnitID(self.killer_id)) if self.killer_id else None

        if hasattr(victim, "value") and self._has_minion_protection(
            state, actual_victim_id, victim
        ):
            # The minion is under at least one protection. Defer the outcome
            # (kill coins, UNIT_DEFEATED, removal) to CheckMinionProtectionStep,
            # which awards by which protection actually fires.
            return StepResult(
                is_finished=True,
                new_steps=[
                    CheckMinionProtectionStep(minion_id=actual_victim_id, killer_id=self.killer_id)
                ],
            )

        events: list[GameEvent] = [
            GameEvent(
                event_type=GameEventType.UNIT_DEFEATED,
                actor_id=self.killer_id,
                target_id=actual_victim_id,
            )
        ]

        # Check for bounty marker BEFORE markers are returned
        bounty = state.markers.get(MarkerType.BOUNTY)
        has_bounty = (
            bounty is not None and bounty.is_placed and bounty.target_id == actual_victim_id
        )

        # Return markers from the defeated hero
        markers_from = state.return_markers_from_hero(actual_victim_id)
        if markers_from:
            logger.debug(
                f"   [DEATH] Returned {len(markers_from)} marker(s) from defeated {actual_victim_id}"
            )

        # Return markers placed by the defeated hero
        markers_by = state.return_markers_by_source(actual_victim_id)
        if markers_by:
            logger.debug(
                f"   [DEATH] Returned {len(markers_by)} marker(s) placed by defeated {actual_victim_id}"
            )

        # Cancel all active effects created by the defeated unit
        EffectManager.expire_by_source(state, actual_victim_id)

        # If the defeated hero has an unresolved card, resolve it without action
        if hasattr(victim, "current_turn_card") and victim.current_turn_card:
            hero = cast(Hero, victim)
            hero.resolve_current_card()

        # Remove from unresolved pool so they don't get another turn this round
        if HeroID(actual_victim_id) in state.unresolved_hero_ids:
            state.unresolved_hero_ids.remove(HeroID(actual_victim_id))

        # Track hero defeats for round-scoped effects (e.g., War Drummer)
        if hasattr(victim, "level"):
            hero_id = HeroID(actual_victim_id)
            if hero_id not in state.heroes_defeated_this_round:
                state.heroes_defeated_this_round.append(hero_id)

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
            kill_gold, assist_gold, penalty_counters = rewards_table.get(level, (level, 1, 1))

            # Bounty marker: defeated hero spends 1 additional life counter
            if has_bounty:
                penalty_counters += 1
                logger.debug(
                    f"   [BOUNTY] {actual_victim_id} has Bounty marker — +1 Life Counter penalty."
                )

            if killer and hasattr(killer, "gold"):
                killer.gold += kill_gold
                logger.debug(f"   [ECONOMY] Killer {killer.id} gains {kill_gold} Gold.")
                events.append(
                    GameEvent(
                        event_type=GameEventType.GOLD_GAINED,
                        actor_id=killer.id,
                        metadata={"amount": kill_gold, "reason": "kill"},
                    )
                )

            if killer and hasattr(killer, "team"):
                killer_team_color = getattr(killer, "team", None)
                if killer_team_color and killer_team_color in state.teams:
                    killer_team = state.teams[killer_team_color]
                    if killer_team:
                        for ally in killer_team.heroes:
                            if ally.id != killer.id:
                                actual_assist = assist_gold * self.assist_multiplier
                                ally.gold += actual_assist
                                logger.debug(
                                    f"   [ECONOMY] Assist: {ally.id} gains {actual_assist} Gold."
                                )
                                events.append(
                                    GameEvent(
                                        event_type=GameEventType.GOLD_GAINED,
                                        actor_id=ally.id,
                                        metadata={
                                            "amount": actual_assist,
                                            "reason": "assist",
                                        },
                                    )
                                )

            if hasattr(victim, "team"):
                victim_team_color = getattr(victim, "team", None)
                if victim_team_color and victim_team_color in state.teams:
                    victim_team = state.teams[victim_team_color]
                    if victim_team:
                        victim_team.life_counters = max(
                            0, victim_team.life_counters - penalty_counters
                        )
                        logger.debug(
                            f"   [SCORE] Team {victim_team_color.name} loses {penalty_counters} Life Counter(s). Remaining: {victim_team.life_counters}"
                        )
                        events.append(
                            GameEvent(
                                event_type=GameEventType.LIFE_COUNTER_CHANGED,
                                metadata={
                                    "team": victim_team_color.name,
                                    "change": -penalty_counters,
                                    "remaining": victim_team.life_counters,
                                },
                            )
                        )

                        if victim_team.life_counters == 0:
                            logger.debug(
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
                                    RemoveUnitStep(unit_id=actual_victim_id),
                                    TriggerGameOverStep(
                                        winner=winning_team, condition="ANNIHILATION"
                                    ),
                                ],
                                events=events,
                            )

        elif hasattr(victim, "value"):  # Is Minion (unprotected — protected ones
            # are routed to CheckMinionProtectionStep above before reaching here)
            # Record the genuine defeat so post-attack passives (e.g. Reign of
            # Winter) can distinguish a real defeat from a totem save.
            context["last_defeated_minion_id"] = actual_victim_id
            reward = victim.value
            logger.debug(f"   [DEATH] Minion Defeated! Killer gains {reward} Gold.")
            if killer and hasattr(killer, "gold"):
                killer.gold += reward
                events.append(
                    GameEvent(
                        event_type=GameEventType.GOLD_GAINED,
                        actor_id=killer.id,
                        metadata={"amount": reward, "reason": "minion_kill"},
                    )
                )

        return StepResult(
            is_finished=True,
            new_steps=[RemoveUnitStep(unit_id=actual_victim_id)],
            events=events,
        )

    def _has_minion_protection(self, state: GameState, minion_id: str, minion: Any) -> bool:
        """Any active MINION_PROTECTION (totem sacrifice or card-discard) covering
        this minion. Such a minion defers its defeat outcome to
        CheckMinionProtectionStep."""
        from goa2.engine.stats import _is_effect_active, is_unit_in_effect_scope

        for effect in state.active_effects:
            if effect.effect_type != EffectType.MINION_PROTECTION:
                continue
            if not _is_effect_active(effect, state):
                continue
            if not is_unit_in_effect_scope(effect, minion_id, state):
                continue
            if (
                effect.protected_minion_types
                and getattr(minion, "type", None) not in effect.protected_minion_types
            ):
                continue
            return True

        return False


class CheckMinionProtectionStep(GameStep):
    """
    Checks if any MINION_PROTECTION effect can save a defeated minion.
    Asks the protecting hero if they want to discard a qualifying card.
    If yes: discard card, emit MINION_PROTECTED event, minion stays.
    If no/skip: try next effect, or push RemoveUnitStep.
    """

    type: StepType = StepType.CHECK_MINION_PROTECTION
    minion_id: str
    killer_id: str | None = None
    tried_effect_ids: list[str] = Field(default_factory=list)

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.stats import _is_effect_active, is_unit_in_effect_scope

        minion = state.get_unit(UnitID(self.minion_id))
        if not minion:
            return StepResult(is_finished=True)

        # Collect untried active MINION_PROTECTION effects covering this minion.
        # Offer optional (card-discard) protections BEFORE the mandatory totem
        # sacrifice, so a totem only fires as a fallback.
        candidates = [
            e
            for e in state.active_effects
            if e.effect_type == EffectType.MINION_PROTECTION
            and e.id not in self.tried_effect_ids
            and _is_effect_active(e, state)
            and is_unit_in_effect_scope(e, self.minion_id, state)
            and (
                not e.protected_minion_types
                or getattr(minion, "type", None) in e.protected_minion_types
            )
        ]
        candidates.sort(key=lambda e: e.sacrifice_origin_token)
        protection = candidates[0] if candidates else None

        if not protection:
            # No protection fired — a genuine defeat. Award the kill coins,
            # emit UNIT_DEFEATED, and remove the minion.
            return StepResult(
                is_finished=True,
                new_steps=[RemoveUnitStep(unit_id=self.minion_id)],
                events=self._defeat_events(state, minion, context),
            )

        # Check if protector has qualifying cards in hand
        protector = state.get_hero(HeroID(protection.source_id))
        if not protector:
            return self._try_next(protection.id)

        if protection.sacrifice_origin_token:
            token_id = protection.scope.origin_id
            if not token_id:
                return self._try_next(protection.id)
            token = state.misc_entities.get(BoardEntityID(token_id))
            if not isinstance(token, Token):
                return self._try_next(protection.id)

            from goa2.engine.steps.markers import _remove_token_from_board

            from_hex, removed_effects = _remove_token_from_board(state, token_id)
            if not from_hex:
                return self._try_next(protection.id)

            logger.debug(
                f"   [PROTECT] {protector.id}'s Totem protects {self.minion_id} and is removed."
            )
            return StepResult(
                is_finished=True,
                events=[
                    GameEvent(
                        event_type=GameEventType.TOKEN_REMOVED,
                        actor_id=protector.id,
                        target_id=token_id,
                        from_hex=_hex_dict(from_hex),
                        metadata={"effects_removed": removed_effects},
                    ),
                    GameEvent(
                        event_type=GameEventType.MINION_PROTECTED,
                        actor_id=protector.id,
                        target_id=self.minion_id,
                        metadata={
                            "sacrificed_token_id": token_id,
                            "effect_id": protection.id,
                        },
                    ),
                ],
            )

        qualifying_cards = [
            c for c in protector.hand if c.color in protection.allowed_discard_colors
        ]

        if not qualifying_cards:
            logger.debug(f"   [PROTECT] {protector.id} has no qualifying cards for protection.")
            return self._try_next(protection.id)

        # Ask protector if they want to discard
        if self.pending_input is None:
            options = [
                InputOption(
                    id=c.id,
                    text=c.name,
                    metadata={"card_id": c.id, "color": c.color.value if c.color else None},
                )
                for c in qualifying_cards
            ]
            return StepResult(
                is_finished=False,
                requires_input=True,
                input_request=create_input_request(
                    request_type=InputRequestType.SELECT_CARD,
                    prompt=f"Discard a card to protect {self.minion_id}?",
                    options=options,
                    player_id=protector.id,
                    can_skip=True,
                ),
            )

        # Process input
        selection = self.pending_input
        if isinstance(selection, dict):
            selection = selection.get("selected_card_id") or selection.get("selection")

        if selection == "SKIP" or selection is None:
            logger.debug(f"   [PROTECT] {protector.id} declined to protect {self.minion_id}.")
            return self._try_next(protection.id)

        # Find and discard the selected card
        card_to_discard = next((c for c in qualifying_cards if c.id == selection), None)
        if not card_to_discard:
            return self._try_next(protection.id)

        protector.discard_card(card_to_discard, from_hand=True)
        logger.debug(
            f"   [PROTECT] {protector.id} discards {card_to_discard.name} to protect {self.minion_id}!"
        )

        # Card-discard protection (e.g. Brogan): the minion is still defeated for
        # scoring purposes — the killer keeps the coins and UNIT_DEFEATED fires —
        # it simply isn't removed from the board.
        return StepResult(
            is_finished=True,
            events=[
                *self._defeat_events(state, minion, context),
                GameEvent(
                    event_type=GameEventType.MINION_PROTECTED,
                    actor_id=protector.id,
                    target_id=self.minion_id,
                    metadata={
                        "discarded_card_id": card_to_discard.id,
                        "effect_id": protection.id,
                    },
                ),
            ],
        )

    def _defeat_events(
        self, state: GameState, minion: Any, context: dict[str, Any]
    ) -> list[GameEvent]:
        """UNIT_DEFEATED plus the killer's kill coins, for a genuine defeat or a
        card-discard save (totem sacrifices deliberately do NOT call this).

        Records the defeat in context so post-attack passives (Reign of Winter)
        fire for a defeated-but-not-removed minion as well as a real kill."""
        context["last_defeated_minion_id"] = self.minion_id
        events: list[GameEvent] = [
            GameEvent(
                event_type=GameEventType.UNIT_DEFEATED,
                actor_id=self.killer_id,
                target_id=self.minion_id,
            )
        ]
        killer = state.get_unit(UnitID(self.killer_id)) if self.killer_id else None
        if killer and hasattr(killer, "gold"):
            reward = minion.value
            killer.gold += reward
            events.append(
                GameEvent(
                    event_type=GameEventType.GOLD_GAINED,
                    actor_id=killer.id,
                    metadata={"amount": reward, "reason": "minion_kill"},
                )
            )
        return events

    def _try_next(self, effect_id: str) -> StepResult:
        """Try the next protection effect."""
        return StepResult(
            is_finished=True,
            new_steps=[
                CheckMinionProtectionStep(
                    minion_id=self.minion_id,
                    killer_id=self.killer_id,
                    tried_effect_ids=[*self.tried_effect_ids, effect_id],
                )
            ],
        )


class RespawnHeroStep(GameStep):
    """
    Handles the Hero Respawn choice.
    If Hero is defeated, requests player input: Respawn or Pass.
    """

    type: StepType = StepType.RESPAWN_HERO
    hero_id: str

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        hero = state.get_hero(HeroID(self.hero_id))
        if not hero:
            return StepResult(is_finished=True)

        # Only respawn if not on board
        if self.hero_id in state.unit_locations:
            return StepResult(is_finished=True)

        if self.pending_input:
            selection = self.pending_input.get("selection")
            if selection == "PASS":
                logger.debug(f"   [RESPAWN] {self.hero_id} chose NOT to respawn.")
                context["skipped_respawn"] = True
                return StepResult(is_finished=True)

            selected_hex_dict = selection if isinstance(selection, dict) else None
            if selected_hex_dict:
                selected_hex = Hex(**selected_hex_dict)
                logger.debug(f"   [RESPAWN] {self.hero_id} respawning at {selected_hex}")
                state.move_unit(UnitID(self.hero_id), selected_hex)
                return StepResult(is_finished=True)

        # Find hero spawn points for this team that aren't obstacles
        valid_hexes = []
        team_spawn_hexes = []
        for sp in state.board.spawn_points:
            if sp.is_hero_spawn and sp.team == hero.team:
                team_spawn_hexes.append(sp.location)
                if not state.validator.is_obstacle_for_actor(state, sp.location, self.hero_id):
                    valid_hexes.append(sp.location)

        # Fallback: BFS from spawn points to find nearest non-obstacle hex
        if not valid_hexes and team_spawn_hexes:
            from goa2.engine.map_logic import find_nearest_empty_hexes

            for spawn_hex in team_spawn_hexes:
                zone_id = state.board.get_zone_for_hex(spawn_hex)
                if zone_id:
                    candidates = find_nearest_empty_hexes(state, spawn_hex, zone_id)
                    if candidates:
                        valid_hexes.extend(candidates)
                        break

        if not valid_hexes:
            logger.debug(f"   [RESPAWN] No empty spawn points for {self.hero_id}!")
            return StepResult(is_finished=True)

        # If user already chose RESPAWN but hasn't picked hex yet, show hexes
        if self.pending_input and self.pending_input.get("selection") == "RESPAWN":
            return StepResult(
                requires_input=True,
                input_request=create_input_request(
                    request_type=InputRequestType.CHOOSE_RESPAWN_HEX,
                    player_id=self.hero_id,
                    prompt=f"Select spawn location for {self.hero_id}",
                    options=valid_hexes,
                    valid_hexes=valid_hexes,  # Pass raw Hex objects
                ),
            )

        # Otherwise, show YES/NO prompt first
        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.CHOOSE_RESPAWN,
                player_id=self.hero_id,
                prompt=f"Hero {self.hero_id} is defeated. Respawn at an empty spawn point?",
                options=["RESPAWN", "PASS"],
                valid_hexes=valid_hexes,  # Pass raw Hex objects
            ),
        )


class RespawnMinionStep(GameStep):
    """
    Respawns a minion of a certain type/team in the active zone.
    """

    type: StepType = StepType.RESPAWN_MINION
    team: TeamColor
    minion_type: Any  # MinionType enum

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
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
            logger.debug(f"   [RESPAWN] No available {team_name} {self.minion_type} to respawn.")
            return StepResult(is_finished=True)

        if self.pending_input:
            selected_hex_dict = self.pending_input.get("selection")
            if isinstance(selected_hex_dict, dict):
                selected_hex = Hex(**selected_hex_dict)
                tile = state.board.get_tile(selected_hex)
                if tile and tile.is_occupied:
                    logger.debug(
                        f"   [ERROR] Cannot respawn {self.minion_type} at {selected_hex}. Occupied."
                    )
                    return StepResult(is_finished=True)

                state.move_unit(UnitID(target_minion.id), selected_hex)
                logger.debug(f"   [RESPAWN] Respawned {target_minion.id} at {selected_hex}")
                return StepResult(is_finished=True)

        valid_spaces = [h for h in zone.hexes if not state.board.get_tile(h).is_occupied]
        if not valid_spaces:
            return StepResult(is_finished=True)

        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_HEX,
                player_id=(str(state.current_actor_id) if state.current_actor_id else "system"),
                prompt=f"Select space to respawn {self.minion_type}.",
                options=valid_spaces,
            ),
        )


class RespawnMinionAtHexStep(GameStep):
    """
    Respawns a specific minion at a hex chosen from filtered candidates.

    Reads the minion ID from context[unit_key], validates it's in limbo,
    then presents filtered hex options for placement. Emits UNIT_PLACED event.
    """

    type: StepType = StepType.RESPAWN_MINION_AT_HEX
    team: TeamColor
    unit_key: str  # Context key containing minion ID
    hex_filters: list[FilterCondition] = Field(default_factory=list)

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        # Read minion ID from context
        minion_id = context.get(self.unit_key)
        if not minion_id:
            logger.debug(f"   [RESPAWN] No minion ID in context['{self.unit_key}'].")
            return StepResult(is_finished=True)

        # Verify minion exists and is in limbo
        team_obj = state.teams.get(self.team)
        if not team_obj:
            return StepResult(is_finished=True)

        target_minion = None
        for m in team_obj.minions:
            if m.id == minion_id and m.id not in state.entity_locations:
                target_minion = m
                break

        if not target_minion:
            logger.debug(f"   [RESPAWN] Minion {minion_id} not found in limbo.")
            return StepResult(is_finished=True)

        # Handle input
        if self.pending_input:
            selected_hex_dict = self.pending_input.get("selection")
            if isinstance(selected_hex_dict, dict):
                selected_hex = Hex(**selected_hex_dict)
                tile = state.board.get_tile(selected_hex)
                if tile and tile.is_occupied:
                    logger.debug(
                        f"   [ERROR] Cannot respawn {minion_id} at {selected_hex}. Occupied."
                    )
                    return StepResult(is_finished=True)

                state.move_unit(UnitID(target_minion.id), selected_hex)
                logger.debug(f"   [RESPAWN] Respawned {target_minion.id} at {selected_hex}")
                return StepResult(
                    is_finished=True,
                    events=[
                        GameEvent(
                            event_type=GameEventType.UNIT_PLACED,
                            actor_id=str(target_minion.id),
                            from_hex=None,
                            to_hex=_hex_dict(selected_hex),
                        )
                    ],
                )

        # Collect valid hexes using filters
        valid_hexes = []
        for h, tile in state.board.tiles.items():
            if tile.is_occupied:
                continue
            is_valid = True
            for f in self.hex_filters:
                if not f.apply(h, state, context):
                    is_valid = False
                    break
            if is_valid:
                valid_hexes.append(h)

        if not valid_hexes:
            logger.debug("   [RESPAWN] No valid hexes for respawn.")
            return StepResult(is_finished=True)

        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_HEX,
                player_id=(str(state.current_actor_id) if state.current_actor_id else "system"),
                prompt=f"Select space to respawn {target_minion.id}.",
                options=valid_hexes,
            ),
        )


class CheckLanePushStep(GameStep):
    """
    Checks if the active zone meets the condition for a Lane Push (0 minions for one team).
    If so, spawns a LanePushStep.
    """

    type: StepType = StepType.CHECK_LANE_PUSH

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.map_logic import check_lane_push_trigger

        if not state.active_zone_id:
            return StepResult(is_finished=True)

        losing_team = check_lane_push_trigger(state, state.active_zone_id)
        if losing_team:
            logger.debug(f"   [CHECK] Lane Push Condition Met for {losing_team.name}")
            return StepResult(is_finished=True, new_steps=[LanePushStep(losing_team=losing_team)])

        return StepResult(is_finished=True)


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

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.map_logic import get_push_target_zone_id
        from goa2.engine.steps.markers import _remove_token_from_board
        from goa2.engine.steps.movement import ResolveDisplacementStep

        logger.debug(f"   [PUSH] Lane Push Triggered! Losing Team: {self.losing_team.name}")

        state.wave_counter -= 1
        logger.debug(f"   [PUSH] Wave Counter removed. Remaining: {state.wave_counter}")

        if state.wave_counter <= 0:
            logger.debug("   [GAME OVER] Last Push Victory!")
            winning_team = TeamColor.BLUE if self.losing_team == TeamColor.RED else TeamColor.RED
            return StepResult(
                is_finished=True,
                new_steps=[TriggerGameOverStep(winner=winning_team, condition="LAST_PUSH")],
            )

        next_zone_id, is_game_over = get_push_target_zone_id(state, self.losing_team)

        if is_game_over:
            logger.debug(
                f"   [GAME OVER] Lane Push Victory! {self.losing_team.name} Throne reached."
            )
            winning_team = TeamColor.BLUE if self.losing_team == TeamColor.RED else TeamColor.RED
            return StepResult(
                is_finished=True,
                new_steps=[TriggerGameOverStep(winner=winning_team, condition="LANE_PUSH")],
            )

        if not next_zone_id:
            logger.debug("   [ERROR] Could not determine next zone for push.")
            return StepResult(is_finished=True)

        if not state.active_zone_id:
            logger.debug("   [ERROR] No active zone for push.")
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
                    if hasattr(unit, "type") and hasattr(unit, "value"):  # Duck typing Minion
                        to_remove.append(uid)

        for uid in to_remove:
            state.remove_unit(uid)
            logger.debug(f"   [PUSH] Wiped {uid} from old zone.")

        logger.debug(f"   [PUSH] Battle Zone moved: {state.active_zone_id} -> {next_zone_id}")
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
                                if m.type == sp.minion_type and m.id not in state.unit_locations
                            ),
                            None,
                        )

                        if candidate:
                            tile = state.board.get_tile(sp.location)
                            if tile and not tile.is_occupied:
                                state.move_unit(candidate.id, sp.location)
                                logger.debug(f"   [PUSH] Spawning {candidate.id} at {sp.location}")
                            else:
                                occupant_id = None
                                if tile and tile.occupant_id:
                                    occupant_id = str(tile.occupant_id)
                                occupant = (
                                    state.misc_entities.get(BoardEntityID(occupant_id))
                                    if occupant_id
                                    else None
                                )
                                if isinstance(occupant, Token) and occupant_id:
                                    _remove_token_from_board(state, occupant_id)
                                    state.move_unit(candidate.id, sp.location)
                                    logger.debug(
                                        f"   [PUSH] Removed token {occupant_id} and spawned {candidate.id} at {sp.location}"
                                    )
                                else:
                                    logger.debug(
                                        f"   [PUSH] Spawn blocked at {sp.location} (Displacement Queued)"
                                    )
                                    pending_displacements.append((candidate.id, sp.location))

        if pending_displacements:
            # Explicitly type cast the list to match ResolveDisplacementStep's expectation
            # ResolveDisplacementStep expects List[Tuple[str, Hex]] or similar.
            # candidate.id is BoardEntityID (subtype of str).
            return StepResult(
                is_finished=True,
                new_steps=[
                    ResolveDisplacementStep(
                        displacements=cast(list[tuple[str, Hex]], pending_displacements)
                    )
                ],
            )

        return StepResult(is_finished=True)


class MinionBattleStep(GameStep):
    """
    Compare minion counts in active zone and queue removals for the losing team.
    Separated from EndPhaseStep so finishing steps can execute first,
    ensuring battle counts reflect post-finishing-step state.
    """

    type: StepType = StepType.MINION_BATTLE

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        battle_steps = self._resolve_minion_battle(state)
        return StepResult(is_finished=True, new_steps=battle_steps)

    def _resolve_minion_battle(self, state: GameState) -> list[GameStep]:
        from goa2.engine.steps.cards import _one_man_army_bonus
        from goa2.engine.steps.selection import ChooseMinionRemovalStep

        if not state.active_zone_id:
            return []

        zone = state.board.zones.get(state.active_zone_id)
        if not zone:
            return []

        red_count = 0
        blue_count = 0

        for unit_id, loc in state.unit_locations.items():
            if loc in zone.hexes:
                unit = state.get_unit(UnitID(unit_id))
                if unit and hasattr(unit, "type") and hasattr(unit, "is_heavy"):
                    if unit.team == TeamColor.RED:
                        red_count += 1
                    elif unit.team == TeamColor.BLUE:
                        blue_count += 1

        # One Man Army: heroes with active ultimate count as +1 minion
        bonus = _one_man_army_bonus(state, zone)
        red_count += bonus[TeamColor.RED]
        blue_count += bonus[TeamColor.BLUE]

        diff = abs(red_count - blue_count)

        if diff == 0:
            logger.debug("   [BATTLE] Minion count tied. No removals.")
            return []

        loser_team = TeamColor.RED if red_count < blue_count else TeamColor.BLUE
        logger.debug(f"   [BATTLE] {loser_team.name} loses {diff} minion(s).")

        return [
            ChooseMinionRemovalStep(
                losing_team=loser_team.value,
                remaining_to_remove=diff,
                zone_id=state.active_zone_id,
            )
        ]


class ReturnMinionToZoneStep(GameStep):
    """
    Returns minions that ended up outside the active zone.

    Per manual: "If any minion miniature ends up outside the Battle Zone
    after you perform an action, move it by the shortest path of empty
    spaces to an empty space in the same Battle Zone."

    If multiple shortest paths exist, the minion's team chooses.
    Processes minions in tie-breaker coin order.
    """

    type: StepType = StepType.RETURN_MINION_TO_ZONE

    def _get_minions_outside_zone(self, state: GameState) -> list[tuple[str, TeamColor]]:
        """Find all minions outside the active zone."""
        if not state.active_zone_id:
            return []

        zone = state.board.zones.get(state.active_zone_id)
        if not zone:
            return []

        outside = []
        for team in state.teams.values():
            for minion in team.minions:
                loc = state.unit_locations.get(minion.id)
                if loc and loc not in zone.hexes:
                    if not minion.team:
                        logger.debug(
                            f"   [WARNING] Minion {minion.id} has no team, skipping zone return"
                        )
                    else:
                        outside.append((str(minion.id), minion.team))
        return outside

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.movement import PlaceUnitStep

        outside_minions = self._get_minions_outside_zone(state)

        if not outside_minions:
            return StepResult(is_finished=True)

        # Sort by tie-breaker: favored team's minions first
        favored = state.tie_breaker_team
        outside_minions.sort(key=lambda x: (0 if x[1] == favored else 1, str(x[0])))

        # Process first minion
        minion_id, team = outside_minions[0]
        remaining = outside_minions[1:]

        loc = state.entity_locations.get(BoardEntityID(minion_id))
        if not loc:
            # Minion somehow has no location, skip
            if remaining:
                return StepResult(
                    is_finished=True,
                    new_steps=[ReturnMinionToZoneStep()],
                )
            return StepResult(is_finished=True)

        if not state.active_zone_id:
            # No active zone, skip
            if remaining:
                return StepResult(
                    is_finished=True,
                    new_steps=[ReturnMinionToZoneStep()],
                )
            return StepResult(is_finished=True)

        from goa2.engine.map_logic import find_nearest_empty_hexes

        candidates = find_nearest_empty_hexes(state, loc, state.active_zone_id)

        if not candidates:
            logger.debug(f"   [ZONE] No empty space in zone for {minion_id}!")
            # Skip this minion, process remaining
            if remaining:
                return StepResult(
                    is_finished=True,
                    new_steps=[ReturnMinionToZoneStep()],
                )
            return StepResult(is_finished=True)

        # If pending input, process it
        if self.pending_input:
            selection = self.pending_input.get("selection")
            if selection:
                target_hex = Hex(**selection) if isinstance(selection, dict) else selection

                if target_hex in candidates:
                    logger.debug(f"   [ZONE] Returning {minion_id} to zone at {target_hex}")
                    new_steps: list[GameStep] = [
                        PlaceUnitStep(unit_id=minion_id, target_hex_arg=target_hex),
                    ]
                    if remaining:
                        new_steps.append(ReturnMinionToZoneStep())
                    return StepResult(is_finished=True, new_steps=new_steps)

        # Auto-move if only one candidate
        if len(candidates) == 1:
            target = candidates[0]
            logger.debug(f"   [ZONE] Auto-returning {minion_id} to zone at {target}")
            new_steps = [
                PlaceUnitStep(unit_id=minion_id, target_hex_arg=target),
            ]
            if remaining:
                new_steps.append(ReturnMinionToZoneStep())
            return StepResult(is_finished=True, new_steps=new_steps)

        # Multiple candidates - need team input
        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_HEX,
                player_id=f"team:{team.value}",
                prompt=f"Team {team.value}, choose destination for {minion_id} to return to Battle Zone.",
                options=candidates,
            ),
        )


class SpendAdditionalLifeCounterStep(GameStep):
    """
    Decrements the victim's team life counters by 1 (additional penalty).
    Used by Ursafar's Tear: "if you defeated a hero, that hero spends 1
    additional Life counter."
    """

    type: StepType = StepType.SPEND_ADDITIONAL_LIFE_COUNTER
    victim_key: str = "victim_id"
    amount: int = 1

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        victim_id = context.get(self.victim_key)
        if not victim_id:
            return StepResult(is_finished=True)

        victim = state.get_hero(HeroID(str(victim_id)))
        if not victim:
            return StepResult(is_finished=True)

        victim_team_color = getattr(victim, "team", None)
        if not victim_team_color or victim_team_color not in state.teams:
            return StepResult(is_finished=True)

        victim_team = state.teams[victim_team_color]
        victim_team.life_counters = max(0, victim_team.life_counters - self.amount)
        logger.debug(
            f"   [SCORE] Team {victim_team_color.name} loses {self.amount} additional Life Counter(s). "
            f"Remaining: {victim_team.life_counters}"
        )

        events = [
            GameEvent(
                event_type=GameEventType.LIFE_COUNTER_CHANGED,
                target_id=str(victim_id),
                metadata={
                    "team": victim_team_color.name,
                    "change": -self.amount,
                    "remaining": victim_team.life_counters,
                    "reason": "additional_life_counter",
                },
            )
        ]

        if victim_team.life_counters == 0:
            from goa2.domain.models import TeamColor

            winning_team = TeamColor.BLUE if victim_team_color == TeamColor.RED else TeamColor.RED
            events.append(
                GameEvent(
                    event_type=GameEventType.GAME_OVER,
                    metadata={
                        "reason": "annihilation",
                        "winning_team": winning_team.name,
                    },
                )
            )
            return StepResult(
                is_finished=True,
                new_steps=[TriggerGameOverStep(winner=winning_team, condition="ANNIHILATION")],
                events=events,
            )

        return StepResult(is_finished=True, events=events)


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

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        logger.debug(f"   [GAME OVER] Victory for {self.winner.name}! Reason: {self.condition}")

        state.winner = self.winner
        state.victory_condition = self.condition
        state.phase = GamePhase.GAME_OVER

        # Hard Stop: Clear everything pending
        state.execution_stack.clear()
        state.input_stack.clear()

        return StepResult(
            is_finished=True,
            events=[
                GameEvent(
                    event_type=GameEventType.GAME_OVER,
                    metadata={
                        "winner": self.winner.name,
                        "condition": self.condition,
                    },
                )
            ],
        )

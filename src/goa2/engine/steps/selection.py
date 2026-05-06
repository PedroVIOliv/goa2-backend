"""Selection and input choice steps."""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Optional
import logging
from pydantic import Field

from goa2.engine.steps.base import GameStep, StepResult
from goa2.domain.state import GameState
from goa2.domain.types import HeroID, UnitID
from goa2.domain.models import ActionType, Card, CardContainerType, StepType, TargetType, TeamColor
from goa2.domain.hex import Hex
from goa2.domain.input import InputOption, InputRequestType, create_input_request
from goa2.domain.events import GameEvent, GameEventType
from goa2.engine.filters_base import FilterCondition
from goa2.engine.filters_hex import RangeFilter


logger = logging.getLogger(__name__)


class SelectStep(GameStep):
    """
    Unified selection step using the Filter System.
    Replaces SelectTargetStep and SelectHexStep.

    Supports target types: "UNIT", "HEX", "CARD", "NUMBER"
    For NUMBER type, use number_options to specify valid choices.

    Note: For UNIT selections, ImmunityFilter is automatically applied unless
    skip_immunity_filter=True is set. ExcludeIdentityFilter (self-exclusion) is
    also auto-applied unless skip_self_filter=True is set.
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
    card_containers: Optional[List[CardContainerType]] = (
        None  # When set, merges candidates from multiple containers
    )
    number_options: List[int] = Field(default_factory=list)  # For NUMBER target type
    number_labels: Dict[int, str] = Field(
        default_factory=dict
    )  # Display text per number option
    skip_immunity_filter: bool = False  # Set True to disable automatic ImmunityFilter
    skip_self_filter: bool = False  # Set True to allow selecting self (e.g. "yourself")
    override_player_id_key: Optional[str] = (
        None  # Key in context to find player ID who provides input
    )
    # Card property filters (applied before candidate extraction for CARD selections)
    card_action_types: Optional[List[ActionType]] = (
        None  # Only include cards with primary_action in this list
    )
    card_is_basic: Optional[bool] = (
        None  # Only include basic (True) or non-basic (False)
    )
    card_is_active: Optional[bool] = (
        None  # Only include active (True) or inactive (False) cards
    )
    allowed_card_ids: Optional[List[str]] = (
        None  # Whitelist: only include cards with these IDs
    )

    def _get_effective_filters(self) -> List[FilterCondition]:
        """
        Returns the effective filter list, auto-adding filters for UNIT selections:
        - ExcludeIdentityFilter (self-exclusion) unless skip_self_filter is True
        - ImmunityFilter unless skip_immunity_filter is True
        """
        from goa2.engine.filters_units import ExcludeIdentityFilter, ImmunityFilter

        effective = list(self.filters)

        if self.target_type in (TargetType.UNIT, TargetType.UNIT_OR_TOKEN):
            # Auto-add ExcludeIdentityFilter for self-exclusion
            if not self.skip_self_filter:
                has_self_exclusion = any(
                    isinstance(f, ExcludeIdentityFilter) and f.exclude_self
                    for f in effective
                )
                if not has_self_exclusion:
                    effective.append(ExcludeIdentityFilter(exclude_self=True))

            # Auto-add ImmunityFilter
            if not self.skip_immunity_filter:
                has_immunity = any(isinstance(f, ImmunityFilter) for f in effective)
                if not has_immunity:
                    effective.append(ImmunityFilter())

        return effective

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            logger.debug(
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
        elif self.target_type == TargetType.UNIT_OR_TOKEN:
            # Use helper method that filters for Units and Tokens only
            # (excludes future entity types like Structures, Hazards, etc.)
            candidates = state.get_units_and_tokens()
        elif self.target_type == TargetType.HEX:
            # Optimization: If there is a RangeFilter, use it to narrow search area
            # For now, simplistic iteration over all tiles
            candidates = list(state.board.tiles.keys())
        elif self.target_type == TargetType.NUMBER:
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
                containers = self.card_containers or [self.card_container]
                for container in containers:
                    if container == CardContainerType.HAND:
                        source_list.extend(hero.hand)
                    elif container == CardContainerType.PLAYED:
                        source_list.extend(
                            c for c in hero.played_cards if c is not None
                        )
                    elif container == CardContainerType.DISCARD:
                        source_list.extend(hero.discard_pile)
                    elif container == CardContainerType.DECK:
                        source_list.extend(hero.deck)

                # Apply card property filters before extracting IDs
                if self.card_action_types is not None:
                    source_list = [
                        c
                        for c in source_list
                        if c.primary_action in self.card_action_types
                    ]
                if self.card_is_basic is not None:
                    source_list = [
                        c for c in source_list if c.is_basic == self.card_is_basic
                    ]
                if self.card_is_active is not None:
                    source_list = [
                        c for c in source_list if c.is_active == self.card_is_active
                    ]
                if self.allowed_card_ids is not None:
                    source_list = [
                        c for c in source_list if c.id in self.allowed_card_ids
                    ]

                candidates = [c.id for c in source_list]

        valid_candidates = []
        effective_filters = self._get_effective_filters()
        for c in candidates:
            # Intrinsic Validation for UNITS: Check can_be_targeted (LOS, etc.)
            # For UNIT_OR_TOKEN, only validate if the candidate is actually a unit
            if self.target_type == TargetType.UNIT and actor_id:
                val_res = state.validator.can_be_targeted(
                    state, str(actor_id), str(c), context
                )
                if not val_res.allowed:
                    continue
            elif self.target_type == TargetType.UNIT_OR_TOKEN and actor_id:
                # Only apply targeting validation to units, not tokens
                if state.get_unit(UnitID(str(c))):
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
                logger.debug(
                    f"   [ABORT] Mandatory selection '{self.prompt}' failed. No candidates."
                )
                return StepResult(is_finished=True, abort_action=True)
            else:
                logger.debug(
                    f"   [SKIP] Optional selection '{self.prompt}' skipped. No candidates."
                )
                return StepResult(is_finished=True)

        if self.auto_select_if_one and len(valid_candidates) == 1 and self.is_mandatory:
            choice = valid_candidates[0]
            context[self.output_key] = choice
            logger.debug(f"   [AUTO] Only one valid option: {choice}. Selected automatically.")
            return StepResult(is_finished=True)

        if self.pending_input:
            selection = self.pending_input.get("selection")

            if selection == "SKIP" and not self.is_mandatory:
                logger.debug("   [SKIP] Player chose to skip optional selection.")
                return StepResult(is_finished=True)

            # Type Conversion for Hex
            if self.target_type == TargetType.HEX and isinstance(selection, dict):
                selection = Hex(**selection)

            # Type Conversion for NUMBER (ensure int comparison)
            if self.target_type == TargetType.NUMBER and selection is not None:
                selection = int(selection)

            if selection in valid_candidates:
                context[self.output_key] = selection
                logger.debug(f"   [INPUT] Player {actor_id} selected {selection}")
                return StepResult(is_finished=True)
            else:
                # Invalid choice, re-request
                pass

        # Map target_type to InputRequestType
        type_map = {
            TargetType.UNIT: InputRequestType.SELECT_UNIT,
            TargetType.UNIT_OR_TOKEN: InputRequestType.SELECT_UNIT_OR_TOKEN,
            TargetType.HEX: InputRequestType.SELECT_HEX,
            TargetType.CARD: InputRequestType.SELECT_CARD,
            TargetType.NUMBER: InputRequestType.SELECT_NUMBER,
        }
        request_type = type_map.get(self.target_type, InputRequestType.SELECT_UNIT)

        # Apply labels to number options if provided
        options_for_request = valid_candidates
        if self.target_type == TargetType.NUMBER and self.number_labels:
            options_for_request = [
                InputOption(
                    id=str(n),
                    text=self.number_labels.get(n, str(n)),
                    metadata={"raw": n},
                )
                for n in valid_candidates
            ]

        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=request_type,
                player_id=str(actor_id),
                prompt=self.prompt,
                options=options_for_request,
                can_skip=not self.is_mandatory,
            ),
        )


class MultiSelectStep(GameStep):
    """
    Allows selecting up to N targets sequentially.
    Stores results as a list in context.

    The step prompts for selection repeatedly until:
    - Player selects "DONE" (if min_selections met)
    - max_selections is reached
    - No more valid candidates

    Uses the same filtering system as SelectStep.
    """

    type: StepType = StepType.MULTI_SELECT
    target_type: TargetType  # "UNIT", "HEX", etc.
    prompt: str
    output_key: str  # Context key for result list
    max_selections: int
    min_selections: int = 0  # 0 = fully optional
    filters: List[FilterCondition] = Field(default_factory=list)
    skip_immunity_filter: bool = False
    skip_self_filter: bool = False  # Set True to allow selecting self

    # Internal state (preserved when pushed back to stack)
    selections: List[str] = Field(default_factory=list)

    def _get_effective_filters(self) -> List[FilterCondition]:
        """Returns filters, auto-adding ExcludeIdentityFilter and ImmunityFilter for UNIT selections."""
        from goa2.engine.filters_units import ExcludeIdentityFilter, ImmunityFilter

        effective = list(self.filters)
        if self.target_type in (TargetType.UNIT, TargetType.UNIT_OR_TOKEN):
            if not self.skip_self_filter:
                has_self_exclusion = any(
                    isinstance(f, ExcludeIdentityFilter) and f.exclude_self
                    for f in effective
                )
                if not has_self_exclusion:
                    effective.append(ExcludeIdentityFilter(exclude_self=True))

            if not self.skip_immunity_filter:
                has_immunity = any(isinstance(f, ImmunityFilter) for f in effective)
                if not has_immunity:
                    effective.append(ImmunityFilter())
        return effective

    def _get_candidates(self, state: GameState, context: Dict[str, Any]) -> List[str]:
        """Get valid candidates, excluding already-selected items."""
        actor_id = state.current_actor_id

        # Build initial candidate list based on target type
        candidates: List[Any] = []
        if self.target_type == TargetType.UNIT:
            all_entities = list(state.entity_locations.keys())
            candidates = [
                eid for eid in all_entities if state.get_unit(UnitID(str(eid)))
            ]
        elif self.target_type == TargetType.UNIT_OR_TOKEN:
            candidates = state.get_units_and_tokens()
        elif self.target_type == TargetType.HEX:
            candidates = list(state.board.tiles.keys())

        # Apply filters
        valid = []
        effective_filters = self._get_effective_filters()
        for c in candidates:
            # Skip already selected
            if str(c) in self.selections:
                continue

            # Targeting validation for units
            if self.target_type == TargetType.UNIT and actor_id:
                val_res = state.validator.can_be_targeted(
                    state, str(actor_id), str(c), context
                )
                if not val_res.allowed:
                    continue
            elif self.target_type == TargetType.UNIT_OR_TOKEN and actor_id:
                if state.get_unit(UnitID(str(c))):
                    val_res = state.validator.can_be_targeted(
                        state, str(actor_id), str(c), context
                    )
                    if not val_res.allowed:
                        continue

            # Apply custom filters
            is_valid = True
            for f in effective_filters:
                if not f.apply(c, state, context):
                    is_valid = False
                    break
            if is_valid:
                valid.append(str(c))

        return valid

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            context[self.output_key] = []
            return StepResult(is_finished=True)

        actor_id = state.current_actor_id
        if not actor_id:
            context[self.output_key] = self.selections
            return StepResult(is_finished=True)

        # Handle input from previous prompt
        if self.pending_input:
            selection = self.pending_input.get("selection")

            if selection in ("DONE", "SKIP"):
                logger.debug(
                    f"   [MULTI-SELECT] Player chose DONE with {len(self.selections)} selections."
                )
                context[self.output_key] = list(self.selections)
                return StepResult(is_finished=True)

            # Add selection
            self.selections.append(str(selection))
            context[self.output_key] = list(self.selections)
            logger.debug(
                f"   [MULTI-SELECT] Added {selection}. Total: {len(self.selections)}/{self.max_selections}"
            )
            self.pending_input = None

            # Hit max? Done
            if len(self.selections) >= self.max_selections:
                logger.debug("   [MULTI-SELECT] Max reached. Finishing.")
                return StepResult(is_finished=True)

        # Get remaining valid candidates
        candidates = self._get_candidates(state, context)

        # No more candidates? Finish
        if not candidates:
            logger.debug("   [MULTI-SELECT] No more candidates. Finishing.")
            context[self.output_key] = list(self.selections)
            # If mandatory and below min, abort
            if self.is_mandatory and len(self.selections) < self.min_selections:
                logger.debug(
                    f"   [ABORT] MultiSelectStep: Only {len(self.selections)} selected, need {self.min_selections}."
                )
                return StepResult(is_finished=True, abort_action=True)
            return StepResult(is_finished=True)

        # Can player skip/finish early?
        allow_done = len(self.selections) >= self.min_selections

        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_UNIT,
                player_id=str(actor_id),
                prompt=f"{self.prompt} ({len(self.selections)}/{self.max_selections})",
                options=candidates,
                can_skip=allow_done,
            ),
        )


class ChooseMinionRemovalStep(GameStep):
    """
    Self-looping step: the losing team chooses which minion to remove.
    Heavy minions can only be chosen once all non-heavy minions are gone.
    Skips player choice when remaining_to_remove >= total_loser_minions - 1
    (no meaningful choice).
    """

    type: StepType = StepType.CHOOSE_MINION_REMOVAL
    losing_team: str  # "RED" or "BLUE"
    remaining_to_remove: int
    zone_id: str

    def _get_loser_minions(self, state: GameState) -> list:
        """Get losing team's minions in the active zone."""
        zone = state.board.zones.get(self.zone_id)
        if not zone:
            return []
        team_color = TeamColor(self.losing_team)
        minions = []
        for unit_id, loc in state.unit_locations.items():
            if loc in zone.hexes:
                unit = state.get_unit(UnitID(unit_id))
                if unit and hasattr(unit, "type") and hasattr(unit, "is_heavy"):
                    if unit.team == team_color:
                        minions.append(unit)
        return minions

    def _get_valid_choices(self, minions: list) -> list:
        """Return selectable minions: non-heavy first, heavy only when no non-heavy remain."""
        non_heavy = [m for m in minions if not m.is_heavy]
        if non_heavy:
            return non_heavy
        return minions

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        from goa2.engine.steps.combat import RemoveUnitStep
        if self.remaining_to_remove <= 0:
            return StepResult(is_finished=True)

        minions = self._get_loser_minions(state)
        if not minions:
            return StepResult(is_finished=True)

        n = len(minions)

        # Skip condition: no meaningful choice
        if self.remaining_to_remove >= n - 1:
            # Auto-remove all, sorted non-heavy first
            minions.sort(key=lambda m: m.is_heavy)
            removal_steps: List[GameStep] = []
            for m in minions[: self.remaining_to_remove]:
                removal_steps.append(RemoveUnitStep(unit_id=str(m.id)))
            return StepResult(is_finished=True, new_steps=removal_steps)

        # Player choice needed
        if self.pending_input:
            chosen_id = self.pending_input.get("selection")
            if chosen_id:
                logger.debug(f"   [BATTLE] {self.losing_team} chose to remove {chosen_id}.")
                new_steps: List[GameStep] = [
                    RemoveUnitStep(unit_id=str(chosen_id)),
                    ChooseMinionRemovalStep(
                        losing_team=self.losing_team,
                        remaining_to_remove=self.remaining_to_remove - 1,
                        zone_id=self.zone_id,
                    ),
                ]
                return StepResult(is_finished=True, new_steps=new_steps)

        valid = self._get_valid_choices(minions)
        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_UNIT,
                player_id=f"team:{self.losing_team}",
                prompt=f"Team {self.losing_team}, choose a minion to remove ({self.remaining_to_remove} remaining).",
                options=[str(m.id) for m in valid],
            ),
        )


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
            logger.debug(f"   [INPUT] {actor_id} chose {selection} for '{self.prompt}'")
            return StepResult(is_finished=True)

        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_OPTION,
                player_id=str(actor_id),
                prompt=self.prompt,
                options=[
                    InputOption(id="YES", text="Yes"),
                    InputOption(id="NO", text="No"),
                ],
            ),
        )


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
        from goa2.engine.steps.cards import ResolveCardStep
        from goa2.engine.steps.combat import RespawnHeroStep
        from goa2.engine.steps.phases import FinalizeHeroTurnStep
        from goa2.engine.steps.reactions import ConfirmResolutionStep
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
                logger.debug(
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
                winner_id = self.pending_input.get("selection")
                logger.debug(
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
                    input_request=create_input_request(
                        request_type=InputRequestType.CHOOSE_ACTOR,
                        player_id=f"team:{target_team.value}",
                        prompt=f"Team {target_team.name}, choose who acts first between {candidates}.",
                        options=candidates,
                        team=target_team,
                    ),
                )

        # We have a winner!
        if not winner_id:
            raise ValueError("No winner identified in tie breaker.")

        state.get_hero(HeroID(winner_id))

        # CRITICAL: Remove winner from unresolved pool so they don't act again immediately
        if winner_id in state.unresolved_hero_ids:
            state.unresolved_hero_ids.remove(HeroID(winner_id))

        state.current_actor_id = HeroID(winner_id)

        new_steps: List[GameStep] = []
        if winner_id not in state.entity_locations:
            new_steps.append(RespawnHeroStep(hero_id=winner_id))
        new_steps.append(ResolveCardStep(hero_id=winner_id))
        new_steps.append(ConfirmResolutionStep(hero_id=winner_id))
        new_steps.append(FinalizeHeroTurnStep(hero_id=winner_id))

        return StepResult(is_finished=True, new_steps=new_steps)


class GuessCardColorStep(GameStep):
    """Prompts the actor to guess a card color.

    Always offers the 5 standard card colors: BLUE, GOLD, GREEN, RED, SILVER.
    The actor picks one via SELECT_OPTION.
    """

    VALID_COLORS: ClassVar[List[str]] = ["BLUE", "GOLD", "GREEN", "RED", "SILVER"]

    type: StepType = StepType.GUESS_CARD_COLOR
    output_key: str  # where to store the guessed color string

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        if self.pending_input:
            selection = self.pending_input.get("selection")
            context[self.output_key] = selection
            return StepResult(is_finished=True)

        options = [InputOption(id=color, text=color) for color in self.VALID_COLORS]

        return StepResult(
            is_finished=False,
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_OPTION,
                player_id=str(state.current_actor_id),
                prompt="Guess the card's color",
                options=options,
            ),
        )


class RevealAndResolveGuessStep(GameStep):
    """Reveals the chosen card and compares its color to the guessed color.

    Sets correct_output_key to True if correct (None otherwise),
    and wrong_output_key to True if wrong (None otherwise).
    This dual-flag approach works with active_if_key branching.
    """

    type: StepType = StepType.REVEAL_AND_RESOLVE_GUESS
    card_key: str  # context key → chosen card ID
    guess_key: str  # context key → guessed color string
    victim_key: str  # context key → victim hero ID
    correct_output_key: str
    wrong_output_key: str

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        card_id = context.get(self.card_key)
        guessed_color = context.get(self.guess_key)
        victim_id = context.get(self.victim_key)

        if not card_id or not guessed_color or not victim_id:
            return StepResult(is_finished=True)

        victim = state.get_hero(HeroID(str(victim_id)))
        if not victim:
            return StepResult(is_finished=True)

        # Find the card in victim's hand
        target_card = next((c for c in victim.hand if c.id == card_id), None)
        if not target_card:
            return StepResult(is_finished=True)

        actual_color = target_card.color.value
        is_correct = guessed_color == actual_color

        if is_correct:
            context[self.correct_output_key] = True
            context[self.wrong_output_key] = None
            logger.debug(
                f"   [GUESS] Correct! Card is {actual_color}, guessed {guessed_color}"
            )
        else:
            context[self.correct_output_key] = None
            context[self.wrong_output_key] = True
            logger.debug(f"   [GUESS] Wrong! Card is {actual_color}, guessed {guessed_color}")

        return StepResult(
            is_finished=True,
            events=[
                GameEvent(
                    event_type=GameEventType.CARD_REVEALED,
                    actor_id=str(victim_id),
                    metadata={
                        "card_id": card_id,
                        "card_name": target_card.name,
                        "card_color": actual_color,
                        "guessed_color": guessed_color,
                        "guess_correct": is_correct,
                    },
                )
            ],
        )


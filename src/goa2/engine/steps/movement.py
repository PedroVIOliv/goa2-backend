"""Movement, push, place, swap, and displacement steps."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import Field

from goa2.domain.events import GameEvent, GameEventType, _hex_dict
from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType, create_input_request
from goa2.domain.models import (
    ActionType,
    Card,
    Hero,
    StepType,
    TargetType,
    TeamColor,
    Token,
    TokenType,
)
from goa2.domain.models.effect import EffectType
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, HeroID, UnitID
from goa2.engine import rules
from goa2.engine.filters_base import FilterCondition
from goa2.engine.steps.base import GameStep, StepResult
from goa2.engine.topology import are_connected

logger = logging.getLogger(__name__)


class MoveUnitStep(GameStep):
    """
    Moves a unit to a target hex with pathfinding validation.

    Supports:
    - Self-movement (actor moves themselves)
    - Forced movement (actor moves another unit, e.g., Noble Blade nudge)
    """

    type: StepType = StepType.MOVE_UNIT

    unit_id: str | None = None
    unit_key: str | None = None

    destination_key: str = "target_hex"
    target_hex_arg: Hex | None = None

    range_val: int = 1
    is_movement_action: bool = False
    pass_through_obstacles: bool = False

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        target_unit_id = self.unit_id
        if not target_unit_id and self.unit_key:
            target_unit_id = context.get(self.unit_key)
        if not target_unit_id:
            target_unit_id = state.current_actor_id

        dest_val = self.target_hex_arg
        if not dest_val:
            dest_val = context.get(self.destination_key)

        if not target_unit_id:
            logger.debug("   [ERROR] No unit for move.")
            return StepResult(is_finished=True)

        if not dest_val:
            logger.debug("   [ERROR] No destination for move.")
            return StepResult(is_finished=True)

        if isinstance(dest_val, dict):
            dest_hex = Hex(**dest_val)
        else:
            dest_hex = dest_val

        actor_id = state.current_actor_id or target_unit_id

        start_hex = state.entity_locations.get(BoardEntityID(target_unit_id))
        if not start_hex:
            logger.debug(f"   [ERROR] Unit {target_unit_id} has no location on board.")
            return StepResult(is_finished=True)

        displacement_validation = state.validator.can_be_moved(
            state=state,
            unit_id=target_unit_id,
            actor_id=actor_id,
            context=context,
        )
        if not displacement_validation.allowed:
            logger.debug(f"   [BLOCKED] MoveUnitStep: {displacement_validation.reason}")
            if self.is_mandatory:
                return StepResult(is_finished=True, abort_action=True)
            return StepResult(is_finished=True)

        # Calculate actual distance for MOVEMENT_ZONE effect validation
        from goa2.engine.topology import topology_distance

        actual_distance = topology_distance(start_hex, dest_hex, state)
        if actual_distance == float("inf"):
            actual_distance = 0  # Unreachable, will fail pathfinding check below

        move_validation = state.validator.can_move(
            state,
            target_unit_id,
            actual_distance,
            context,
            is_movement_action=self.is_movement_action,
        )
        if not move_validation.allowed:
            logger.debug(f"   [BLOCKED] MoveUnitStep: {move_validation.reason}")
            if self.is_mandatory:
                return StepResult(is_finished=True, abort_action=True)
            return StepResult(is_finished=True)

        if start_hex == dest_hex:
            is_valid = self.range_val >= 0
        else:
            is_valid = rules.validate_movement_path(
                board=state.board,
                start=start_hex,
                end=dest_hex,
                max_steps=self.range_val,
                state=state,
                actor_id=(str(state.current_actor_id) if state.current_actor_id else None),
                pass_through_obstacles=self.pass_through_obstacles,
            )

        if not is_valid:
            logger.debug(
                f"   [ERROR] Invalid move for {target_unit_id} to {dest_hex}. Path blocked or out of range."
            )
            return StepResult(is_finished=True)

        # Mine detection: only enemy heroes trigger mines
        moving_entity = state.get_entity(BoardEntityID(target_unit_id))
        moving_team = moving_entity.team if isinstance(moving_entity, Hero) else None
        if moving_team and "triggered_mine_ids" not in context and start_hex != dest_hex:
            has_enemy_mines = any(
                token.is_passable
                and token.owner_id
                and getattr(state.get_hero(token.owner_id), "team", None) != moving_team
                for tokens in state.token_pool.values()
                for token in tokens
                if BoardEntityID(str(token.id)) in state.entity_locations
            )
            if has_enemy_mines:
                from goa2.engine.rules import find_reachable_with_mines

                current_actor = str(state.current_actor_id) if state.current_actor_id else None
                reachable = find_reachable_with_mines(
                    board=state.board,
                    start=start_hex,
                    max_steps=self.range_val,
                    state=state,
                    actor_id=current_actor,
                    moving_team=moving_team,
                )

                mine_options = reachable.get(dest_hex, [])
                if len(mine_options) > 1:
                    # Multiple paths — need player choice, re-queue
                    return StepResult(
                        is_finished=True,
                        new_steps=[
                            MinePathChoiceStep(
                                destination_key=self.destination_key,
                                range_val=self.range_val,
                                unit_id=target_unit_id,
                            ),
                            self.model_copy(),
                        ],
                    )
                context["triggered_mine_ids"] = (
                    list(mine_options[0].mine_ids) if mine_options else []
                )

        logger.debug(
            f"   [LOGIC] Moving {target_unit_id} from {start_hex} to {dest_hex} (Range {self.range_val})"
        )
        from_hex_dict = _hex_dict(start_hex)
        to_hex_dict = _hex_dict(dest_hex)
        state.move_unit(UnitID(target_unit_id), dest_hex)

        new_steps: list[GameStep] = []
        triggered_mines = context.get("triggered_mine_ids", [])
        if triggered_mines:
            context["mine_victim_id"] = target_unit_id
            new_steps.append(TriggerMineStep())

        return StepResult(
            is_finished=True,
            events=[
                GameEvent(
                    event_type=GameEventType.UNIT_MOVED,
                    actor_id=target_unit_id,
                    from_hex=from_hex_dict,
                    to_hex=to_hex_dict,
                    metadata={"range": self.range_val},
                )
            ],
            new_steps=new_steps,
        )


class MoveSequenceStep(GameStep):
    """
    Composite Step for Movement.
    Expands into: Select Destination Hex -> Move Unit.
    Should ONLY be used for Movement Actions (primary or secondary).
    For other movement purposes, use MoveUnitStep directly.
    """

    type: StepType = StepType.MOVE_SEQUENCE
    unit_id: str | None = None
    range_val: int = 1
    destination_key: str = "target_hex"
    is_mandatory: bool = True
    pass_through_obstacles: bool = False
    force_straight_line: bool = False
    force_full_distance: bool = False

    def _get_effective_range(self, state: GameState, unit_id: str) -> int:
        """Get effective movement range, considering MOVEMENT_ZONE effects."""
        from goa2.domain.models.effect import EffectType

        max_range = self.range_val

        unit_loc = state.entity_locations.get(BoardEntityID(unit_id))
        if not unit_loc:
            return max_range

        for effect in state.active_effects:
            if effect.effect_type != EffectType.MOVEMENT_ZONE:
                continue
            if not state.validator._is_effect_active(effect, state):
                continue
            if not state.validator._is_in_scope(effect, unit_id, unit_loc, state):
                continue
            # Only applies to movement actions (MoveSequenceStep is always a movement action)
            if effect.max_value is not None:
                max_range = min(max_range, effect.max_value)

        return max_range

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.selection import SelectStep

        actor_id = self.unit_id or state.current_actor_id

        # Calculate effective range (capped by MOVEMENT_ZONE effects)
        effective_range = (
            self._get_effective_range(state, str(actor_id)) if actor_id else self.range_val
        )

        # Auto-detect pass_through_obstacles from hero's active movement auras
        pass_through = self.pass_through_obstacles
        if not pass_through and actor_id:
            hero = state.get_hero(HeroID(str(actor_id)))
            if hero:
                from goa2.engine.effects import get_active_aura_effects

                for _, effect in get_active_aura_effects(state, hero):
                    aura = effect.get_movement_aura()
                    if aura and aura.pass_through_obstacles:
                        pass_through = True
                        break

        # Also consult MOVEMENT_AURA_ZONE effects (Silverarrow's Trailblazer):
        # a radius zone that grants pass-through-obstacles to anyone in scope
        # at the start of a MOVEMENT action. Measured at move-start, not
        # per-pathfinding-step (matches other auras).
        if not pass_through and actor_id:
            from goa2.domain.models.effect import EffectType as _EffectType

            actor_loc = state.entity_locations.get(BoardEntityID(str(actor_id)))
            if actor_loc:
                for effect in state.active_effects:
                    if effect.effect_type != _EffectType.MOVEMENT_AURA_ZONE:
                        continue
                    if not effect.grants_pass_through_obstacles:
                        continue
                    if not state.validator._is_effect_active(effect, state):
                        continue
                    if not state.validator._is_in_scope(effect, str(actor_id), actor_loc, state):
                        continue
                    pass_through = True
                    break

        # If we already have the destination in context, just move
        if context.get(self.destination_key):
            return StepResult(
                is_finished=True,
                new_steps=[
                    MoveUnitStep(
                        unit_id=actor_id,
                        destination_key=self.destination_key,
                        range_val=effective_range,
                        is_mandatory=self.is_mandatory,
                        is_movement_action=True,
                        pass_through_obstacles=pass_through,
                    ),
                ],
            )

        from goa2.engine.filters_hex import MovementPathFilter, ObstacleFilter

        # Determine filters.
        # MovementPathFilter now always allows the current hex.
        # We add OccupiedFilter(is_occupied=False, exclude_id=actor_id)
        # to ensure other units block movement but the moving unit doesn't block itself.
        filters: list[FilterCondition] = [
            ObstacleFilter(is_obstacle=False, exclude_id=actor_id),
            MovementPathFilter(
                range_val=effective_range,
                unit_id=actor_id,
                pass_through_obstacles=pass_through,
            ),
        ]

        # Force straight line: add InStraightLineFilter + StraightLinePathFilter
        if self.force_straight_line:
            from goa2.engine.filters_geometry import InStraightLineFilter, StraightLinePathFilter

            filters.append(InStraightLineFilter(origin_id=actor_id))
            filters.append(StraightLinePathFilter(origin_id=actor_id))

        # Force full distance: set min_range = max_range
        if self.force_full_distance:
            from goa2.engine.filters_hex import RangeFilter

            filters.append(RangeFilter(min_range=effective_range, max_range=effective_range))

        # If range is 0, MovementPathFilter will only allow current hex.
        # OccupiedFilter will also allow it because of exclude_id.

        logger.debug(f"   [MACRO] Expanding Move Sequence (Range: {effective_range})")

        return StepResult(
            is_finished=True,
            new_steps=[
                SelectStep(
                    target_type=TargetType.HEX,
                    prompt=f"Select Movement Destination (Range {effective_range})",
                    output_key=self.destination_key,
                    filters=filters,
                    is_mandatory=self.is_mandatory,
                ),
                MoveUnitStep(
                    unit_id=actor_id,
                    destination_key=self.destination_key,
                    range_val=effective_range,
                    is_mandatory=self.is_mandatory,
                    is_movement_action=True,
                    pass_through_obstacles=pass_through,
                ),
            ],
        )


class FastTravelStep(GameStep):
    """
    DEPRECATED: Use FastTravelSequenceStep instead.
    Execution step for Fast Travel.
    """

    type: StepType = StepType.FAST_TRAVEL
    unit_id: str | None = None
    destination_key: str = "target_hex"

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        logger.debug("   [WARNING] FastTravelStep is deprecated. Use FastTravelSequenceStep.")
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
    unit_id: str | None = None
    destination_key: str = "target_hex"

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.selection import SelectStep

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

        from goa2.engine.filters_hex import FastTravelDestinationFilter

        logger.debug("   [MACRO] Expanding Fast Travel Sequence")

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


class MinePathChoiceStep(GameStep):
    """
    Prompts the current actor to choose which mine-path to take when
    multiple routes with different mine combinations exist.

    ``unit_id`` / ``unit_key`` identify the unit being moved (used for
    start-hex lookup).  The input prompt targets ``current_actor_id``
    (the player controlling the movement).
    """

    type: StepType = StepType.MINE_PATH_CHOICE
    destination_key: str = "target_hex"
    range_val: int = 1
    output_key: str = "triggered_mine_ids"
    unit_id: str | None = None
    unit_key: str | None = None

    def _get_moving_unit_id(self, state: GameState, context: dict[str, Any]) -> str | None:
        if self.unit_id:
            return self.unit_id
        if self.unit_key:
            val = context.get(self.unit_key)
            if val:
                return str(val)
        return str(state.current_actor_id) if state.current_actor_id else None

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        dest_val = context.get(self.destination_key)
        if not dest_val:
            context[self.output_key] = []
            return StepResult(is_finished=True)

        dest_hex = Hex(**dest_val) if isinstance(dest_val, dict) else dest_val
        moving_id = self._get_moving_unit_id(state, context)

        if not moving_id:
            context[self.output_key] = []
            return StepResult(is_finished=True)

        # Only enemy heroes trigger mines
        moving_entity = state.get_entity(BoardEntityID(moving_id))
        moving_team = moving_entity.team if isinstance(moving_entity, Hero) else None
        if not moving_team:
            context[self.output_key] = []
            return StepResult(is_finished=True)

        start_hex = state.entity_locations.get(BoardEntityID(moving_id))
        if not start_hex:
            context[self.output_key] = []
            return StepResult(is_finished=True)

        from goa2.engine.rules import find_reachable_with_mines

        current_actor = str(state.current_actor_id) if state.current_actor_id else None
        reachable = find_reachable_with_mines(
            board=state.board,
            start=start_hex,
            max_steps=self.range_val,
            state=state,
            actor_id=current_actor,
            moving_team=moving_team,
        )

        mine_options = reachable.get(dest_hex, [])
        if len(mine_options) <= 1:
            context[self.output_key] = list(mine_options[0].mine_ids) if mine_options else []
            return StepResult(is_finished=True)

        if self.pending_input:
            selection = self.pending_input.get("selection")
            for idx, opt in enumerate(mine_options):
                if selection == str(idx):
                    context[self.output_key] = list(opt.mine_ids)
                    return StepResult(is_finished=True)
            self.pending_input = None

        options = []
        for idx, opt in enumerate(mine_options):
            mine_hexes = []
            for mid in opt.mine_ids:
                loc = state.entity_locations.get(BoardEntityID(mid))
                if loc:
                    mine_hexes.append({"q": loc.q, "r": loc.r, "s": loc.s})
            path_hexes = [{"q": h.q, "r": h.r, "s": h.s} for h in opt.path]
            options.append(
                {
                    "id": str(idx),
                    "text": f"Path through {len(opt.mine_ids)} mine(s)",
                    "metadata": {
                        "mine_count": len(opt.mine_ids),
                        "mine_hexes": mine_hexes,
                        "path": path_hexes,
                    },
                }
            )

        return StepResult(
            is_finished=False,
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_OPTION,
                player_id=str(state.current_actor_id) if state.current_actor_id else "",
                prompt="Choose which mines to move through",
                options=options,
            ),
        )


class TriggerMineStep(GameStep):
    """Triggers mines after movement - removes tokens and emits events.

    For each blast mine, pushes a ForceDiscardStep targeting the moved hero
    (identified by ``victim_key`` in context).
    """

    type: StepType = StepType.TRIGGER_MINE
    mine_ids_key: str = "triggered_mine_ids"
    victim_key: str = "mine_victim_id"

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.cards import ForceDiscardStep
        from goa2.engine.steps.markers import _remove_token_from_board

        mine_ids = context.get(self.mine_ids_key, [])
        if not mine_ids:
            return StepResult(is_finished=True)

        events: list[GameEvent] = []
        blast_count = 0
        for mine_id in mine_ids:
            token = state.get_entity(BoardEntityID(mine_id))
            from_hex, _ = _remove_token_from_board(state, mine_id)
            is_blast = hasattr(token, "token_type") and token.token_type == TokenType.MINE_BLAST
            if is_blast:
                blast_count += 1
            if from_hex and token:
                events.append(
                    GameEvent(
                        event_type=GameEventType.MINE_TRIGGERED,
                        actor_id=(str(state.current_actor_id) if state.current_actor_id else None),
                        target_id=mine_id,
                        from_hex=_hex_dict(from_hex),
                        metadata={
                            "token_type": (
                                token.token_type.value if hasattr(token, "token_type") else None
                            ),
                            "is_blast": is_blast,
                        },
                    )
                )

        context[self.mine_ids_key] = []
        context["rollback_disabled"] = True

        # Each blast mine forces the moved hero to discard a card (if able)
        new_steps: list[GameStep] = []
        for _ in range(blast_count):
            new_steps.append(ForceDiscardStep(victim_key=self.victim_key))

        return StepResult(is_finished=True, events=events, new_steps=new_steps)


class ResolvePreActionMovementStep(GameStep):
    """
    Checks for an active PRE_ACTION_MOVEMENT effect on a hero and, if found,
    spawns an optional SelectStep + MoveUnitStep before the primary action.

    Used by Misa's Focus/Discipline/Mastery green cards.
    """

    type: StepType = StepType.RESOLVE_PRE_ACTION_MOVEMENT
    hero_id: str | None = None
    hero_key: str | None = None

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.selection import SelectStep

        hero_id = self.hero_id
        if not hero_id and self.hero_key:
            hero_id = context.get(self.hero_key)
        if not hero_id:
            return StepResult(is_finished=True)

        effect = next(
            (
                e
                for e in state.active_effects
                if e.effect_type == EffectType.PRE_ACTION_MOVEMENT
                and e.source_id == hero_id
                and e.is_active
            ),
            None,
        )
        if not effect:
            return StepResult(is_finished=True)

        move_range = effect.max_value or 1

        from goa2.engine.filters_hex import MovementPathFilter, ObstacleFilter

        logger.debug(f"   [PRE-ACTION MOVE] Granting {hero_id} optional move up to {move_range}")

        return StepResult(
            is_finished=True,
            new_steps=[
                SelectStep(
                    target_type=TargetType.HEX,
                    prompt=f"Pre-action movement (up to {move_range} space{'s' if move_range > 1 else ''})",
                    output_key="pre_action_move_hex",
                    filters=[
                        ObstacleFilter(is_obstacle=False, exclude_id=hero_id),
                        MovementPathFilter(range_val=move_range, unit_id=hero_id),
                    ],
                    is_mandatory=False,
                ),
                MoveUnitStep(
                    unit_id=hero_id,
                    destination_key="pre_action_move_hex",
                    range_val=move_range,
                    is_mandatory=False,
                    is_movement_action=False,
                ),
            ],
        )


class PlaceUnitStep(GameStep):
    """
    Moves a unit to a target hex directly.
    No pathfinding validation. Used for respawns, swaps, and forced placements.
    """

    type: StepType = StepType.PLACE_UNIT
    unit_id: str | None = None  # If None, checks unit_key, then current_actor
    unit_key: str | None = None  # Look up unit_id in context
    destination_key: str = "target_hex"  # Where to look in context
    target_hex_arg: Hex | None = None  # Explicit argument

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
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
            logger.debug("   [ERROR] No unit for place.")
            return StepResult(is_finished=True)

        if not dest_val:
            logger.debug("   [ERROR] No destination for place.")
            return StepResult(is_finished=True)

        if isinstance(dest_val, dict):
            dest_hex = Hex(**dest_val)
        else:
            dest_hex = dest_val  # Assume it is already a Hex

        # Validation: Check Occupancy (allow if occupied by self)
        tile = state.board.get_tile(dest_hex)
        if tile and tile.is_occupied and str(tile.occupant_id) != target_unit_id:
            logger.debug(
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
            logger.debug(f"   [BLOCKED] PlaceUnitStep: {validation.reason}")
            if self.is_mandatory:
                return StepResult(is_finished=True, abort_action=True)
            return StepResult(is_finished=True)

        logger.debug(f"   [LOGIC] Placing {target_unit_id} at {dest_hex}")
        from_hex = state.entity_locations.get(BoardEntityID(str(target_unit_id)))
        from_hex_dict = _hex_dict(from_hex)
        to_hex_dict = _hex_dict(dest_hex)
        state.move_unit(UnitID(str(target_unit_id)), dest_hex)
        return StepResult(
            is_finished=True,
            events=[
                GameEvent(
                    event_type=GameEventType.UNIT_PLACED,
                    actor_id=str(target_unit_id),
                    from_hex=from_hex_dict,
                    to_hex=to_hex_dict,
                )
            ],
        )


class SwapUnitsStep(GameStep):
    """
    Swaps the positions of two units.
    Updates the board state directly.

    Supports two modes:
    - Direct: Provide unit_a_id and unit_b_id directly
    - Context: Provide unit_a_key and/or unit_b_key to read from context
    """

    type: StepType = StepType.SWAP_UNITS
    unit_a_id: str | None = None
    unit_b_id: str | None = None
    unit_a_key: str | None = None  # Read unit_a from context
    unit_b_key: str | None = None  # Read unit_b from context

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
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
            logger.debug("   [SKIP] SwapUnitsStep: Missing unit ID(s).")
            return StepResult(is_finished=True)

        # Get current locations from Unified Dict
        loc_a = state.entity_locations.get(BoardEntityID(actual_unit_a))
        loc_b = state.entity_locations.get(BoardEntityID(actual_unit_b))

        if not loc_a or not loc_b:
            logger.debug(
                f"   [ERROR] Cannot swap {actual_unit_a} and {actual_unit_b}. One is not on board."
            )
            return StepResult(is_finished=True)

        # Validation
        actor_id = state.current_actor_id
        res_a = state.validator.can_be_swapped(
            state, actual_unit_a, str(actor_id) if actor_id else "system", context
        )
        if not res_a.allowed:
            logger.debug(f"   [BLOCKED] Swap prevented for {actual_unit_a}: {res_a.reason}")
            if self.is_mandatory:
                return StepResult(is_finished=True, abort_action=True)
            return StepResult(is_finished=True)

        res_b = state.validator.can_be_swapped(
            state, actual_unit_b, str(actor_id) if actor_id else "system", context
        )
        if not res_b.allowed:
            logger.debug(f"   [BLOCKED] Swap prevented for {actual_unit_b}: {res_b.reason}")
            if self.is_mandatory:
                return StepResult(is_finished=True, abort_action=True)
            return StepResult(is_finished=True)

        logger.debug(f"   [LOGIC] Swapping {actual_unit_a} ({loc_a}) <-> {actual_unit_b} ({loc_b})")

        # Use Primitive operations to ensure cache consistency
        # 1. Remove both
        state.remove_entity(BoardEntityID(actual_unit_a))
        state.remove_entity(BoardEntityID(actual_unit_b))

        # 2. Place at swapped locations
        state.place_entity(BoardEntityID(actual_unit_a), loc_b)
        state.place_entity(BoardEntityID(actual_unit_b), loc_a)

        return StepResult(
            is_finished=True,
            events=[
                GameEvent(
                    event_type=GameEventType.UNITS_SWAPPED,
                    actor_id=actual_unit_a,
                    target_id=actual_unit_b,
                    from_hex=_hex_dict(loc_a),
                    to_hex=_hex_dict(loc_b),
                )
            ],
        )


class PushUnitStep(GameStep):
    """
    Pushes a unit away from a source location.
    Stops at obstacles or board edge.

    Supports two modes:
    - Direct: Provide target_id and distance directly
    - Context: Provide target_key and/or distance_key to read from context

    If collision_output_key is set, stores True in context if push was stopped
    early by an obstacle (for effects like Kinetic Repulse that trigger on collision).
    """

    type: StepType = StepType.PUSH_UNIT
    target_id: str | None = None  # Direct target ID
    target_key: str | None = None  # Read target from context
    source_hex: Hex | None = None  # If None, uses current actor's location
    distance: int = 1  # Default/fallback distance
    distance_key: str | None = None  # Read distance from context
    collision_output_key: str | None = None  # If set, stores True on collision
    ignore_obstacles: bool = False  # Path passes through obstacles; land on last legal hex

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.effects import CheckPassiveAbilitiesStep

        if self.should_skip(context):
            return StepResult(is_finished=True)

        # Resolve target ID from either direct or context
        actual_target_id = self.target_id
        if not actual_target_id and self.target_key:
            actual_target_id = context.get(self.target_key)

        if not actual_target_id:
            logger.debug("   [SKIP] PushUnitStep: No target specified or found in context.")
            return StepResult(is_finished=True)

        # Resolve distance from context or use default
        actual_distance = self.distance
        if self.distance_key:
            ctx_dist = context.get(self.distance_key)
            if ctx_dist is not None:
                actual_distance = int(ctx_dist)

        target_loc = state.entity_locations.get(BoardEntityID(actual_target_id))
        if not target_loc:
            return StepResult(is_finished=True)

        src_hex = self.source_hex
        if not src_hex:
            if state.current_actor_id:
                src_hex = state.entity_locations.get(BoardEntityID(state.current_actor_id))

        if not src_hex:
            logger.debug("   [ERROR] No source for push.")
            return StepResult(is_finished=True)

        if src_hex == target_loc:
            logger.debug("   [ERROR] Cannot push from same hex.")
            return StepResult(is_finished=True)

        # Validation
        actor_id = state.current_actor_id
        res = state.validator.can_be_pushed(
            state, actual_target_id, str(actor_id) if actor_id else "system", context
        )
        if not res.allowed:
            logger.debug(f"   [BLOCKED] Push prevented for {actual_target_id}: {res.reason}")
            if self.is_mandatory:
                return StepResult(is_finished=True, abort_action=True)
            return StepResult(is_finished=True)

        direction_idx = src_hex.direction_to(target_loc)
        if direction_idx is None:
            logger.debug(
                f"   [ERROR] Push target {actual_target_id} is not in a straight line from source."
            )
            return StepResult(is_finished=True)

        path: list[Hex] = [target_loc]
        was_stopped_by_obstacle = False
        for _ in range(actual_distance):
            prev = path[-1]
            next_hex = prev.neighbor(direction_idx)

            if next_hex not in state.board.tiles:
                logger.debug(f"   [PUSH] {actual_target_id} hit board edge at {prev}")
                was_stopped_by_obstacle = True
                break

            if not are_connected(prev, next_hex, state):
                logger.debug(
                    f"   [PUSH] {actual_target_id} blocked by topology split at {next_hex}"
                )
                was_stopped_by_obstacle = True
                break

            state.board.get_tile(next_hex)
            is_obs = state.validator.is_obstacle_for_actor(
                state,
                next_hex,
                (str(state.current_actor_id) if state.current_actor_id else actual_target_id),
            )
            if is_obs:
                if state.validator.is_passable_token(state, next_hex):
                    path.append(next_hex)
                    continue
                if self.ignore_obstacles:
                    path.append(next_hex)
                    continue
                logger.debug(f"   [PUSH] {actual_target_id} hit obstacle at {next_hex}")
                was_stopped_by_obstacle = True
                break

            path.append(next_hex)

        # Trim trailing passable tokens — units can't land on mines
        trimmed_mines = 0
        while len(path) > 1 and state.validator.is_passable_token(state, path[-1]):
            path.pop()
            trimmed_mines += 1
        if trimmed_mines > 0:
            was_stopped_by_obstacle = True

        # Trim trailing obstacles — units can't land on an obstacle hex
        if self.ignore_obstacles:
            trimmed_obs = 0
            while len(path) > 1 and state.validator.is_obstacle_for_actor(
                state,
                path[-1],
                (str(state.current_actor_id) if state.current_actor_id else actual_target_id),
            ):
                path.pop()
                trimmed_obs += 1
            if trimmed_obs > 0:
                was_stopped_by_obstacle = True

        current_loc = path[-1]
        pushed_dist = len(path) - 1

        if pushed_dist > 0:
            logger.debug(
                f"   [LOGIC] Pushing {actual_target_id} from {target_loc} to {current_loc} ({pushed_dist} spaces)"
            )
            state.place_entity(BoardEntityID(actual_target_id), current_loc)
        else:
            logger.debug(f"   [LOGIC] Push had no effect for {actual_target_id}")

        if self.collision_output_key:
            context[self.collision_output_key] = was_stopped_by_obstacle
            logger.debug(
                f"   [PUSH] Collision detected: {was_stopped_by_obstacle} -> {self.collision_output_key}"
            )

        from goa2.domain.models.enums import PassiveTrigger

        context["push_victim_id"] = actual_target_id
        post_push_steps: list[GameStep] = []

        # Collect enemy mine IDs from the path (hexes between start and landing, exclusive)
        if pushed_dist > 0:
            pushed_entity = state.get_entity(BoardEntityID(actual_target_id))
            pushed_team = pushed_entity.team if isinstance(pushed_entity, Hero) else None
            if pushed_team:
                enemy_mine_ids: list[str] = []
                for hx in path[1:-1]:
                    if state.validator.is_passable_token(state, hx):
                        tile = state.board.get_tile(hx)
                        if tile and tile.occupant_id:
                            tok_entity = state.get_entity(BoardEntityID(str(tile.occupant_id)))
                            if isinstance(tok_entity, Token) and tok_entity.owner_id:
                                owner_hero = state.get_hero(tok_entity.owner_id)
                                if owner_hero and owner_hero.team != pushed_team:
                                    enemy_mine_ids.append(str(tok_entity.id))
                if enemy_mine_ids:
                    context["triggered_mine_ids"] = enemy_mine_ids
                    context["mine_victim_id"] = actual_target_id
                    post_push_steps.append(TriggerMineStep())

        target_misc = state.misc_entities.get(BoardEntityID(actual_target_id))
        is_token_target = isinstance(target_misc, Token)
        if not is_token_target:
            post_push_steps.append(
                CheckPassiveAbilitiesStep(trigger=PassiveTrigger.AFTER_PUSH.value)
            )

        return StepResult(
            is_finished=True,
            new_steps=post_push_steps,
            events=[
                GameEvent(
                    event_type=(
                        GameEventType.TOKEN_PUSHED if is_token_target else GameEventType.UNIT_PUSHED
                    ),
                    actor_id=str(actor_id) if actor_id else None,
                    target_id=actual_target_id,
                    from_hex=_hex_dict(target_loc),
                    to_hex=_hex_dict(current_loc),
                    metadata={
                        "distance": pushed_dist,
                        "collision": was_stopped_by_obstacle,
                    },
                )
            ],
        )


class ResolveDisplacementStep(GameStep):
    """
    Handles the placement of minions that could not spawn due to occupied tiles.
    Uses BFS to find nearest empty hexes and prompts team if multiple options exist.
    """

    type: StepType = StepType.RESOLVE_DISPLACEMENT
    # List of (UnitID, OriginalHex)
    displacements: list[tuple[str, Hex]] = Field(default_factory=list)

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
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
            sel_uid = self.pending_input.get("selection")
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
                input_request=create_input_request(
                    request_type=InputRequestType.SELECT_UNIT,
                    player_id=delegate_id,
                    prompt=f"Team {team.name if team else 'Unknown'}, choose which displaced unit to place first.",
                    options=options,
                ),
            )

        uid, origin = active_group[0]
        remaining = active_group[1:] + (second_group if active_group is first_group else [])

        from goa2.engine.map_logic import find_nearest_empty_hexes

        if not state.active_zone_id:
            # Should be impossible if game is running, but safety check
            return StepResult(is_finished=True)

        candidates = find_nearest_empty_hexes(state, origin, state.active_zone_id)

        if not candidates:
            logger.debug(f"   [DISPLACE] No empty space found for {uid} in zone!")
            return StepResult(
                is_finished=True,
                new_steps=[ResolveDisplacementStep(displacements=remaining)],
            )

        if self.pending_input:
            selection = self.pending_input.get("selection")
            if selection:
                target_hex = Hex(**selection)
                if target_hex in candidates:
                    logger.debug(f"   [DISPLACE] Team chose {target_hex} for {uid}")
                    return StepResult(
                        is_finished=True,
                        new_steps=[
                            PlaceUnitStep(unit_id=uid, target_hex_arg=target_hex),
                            ResolveDisplacementStep(displacements=remaining),
                        ],
                    )

        if len(candidates) == 1:
            target = candidates[0]
            logger.debug(f"   [DISPLACE] Auto-placing {uid} at {target}")
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
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_HEX,
                player_id=delegate_id,
                prompt=f"Team {team.name if team else 'Unknown'}, choose displacement for {unit_obj.name if unit_obj else uid}.",
                options=candidates,
                context_unit_id=uid,
            ),
        )


class ForceDefenseCardMovementStep(GameStep):
    """
    After an attack, forces the defender to perform the movement action
    from the card they defended with, in a straight line at full distance.

    Reads defense_card_id and defender_id from context. Handles 3 cases:
    1. No movement on defense card → nothing
    2. Secondary MOVEMENT → MoveSequenceStep with force_straight_line + force_full_distance
    3. Primary MOVEMENT → calls card effect's build_steps(), injects
       force_straight_line + force_full_distance into any MoveSequenceStep
    """

    type: StepType = StepType.FORCE_DEFENSE_CARD_MOVEMENT
    defender_key: str = "victim_id"

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        from goa2.engine.steps.utility import SetActorStep

        if self.should_skip(context):
            return StepResult(is_finished=True)

        defense_card_id = context.get("defense_card_id")
        defender_id = context.get(self.defender_key) or context.get("defender_id")
        if not defense_card_id or not defender_id:
            return StepResult(is_finished=True)

        hero = state.get_hero(HeroID(str(defender_id)))
        if not hero:
            return StepResult(is_finished=True)

        # Find the defense card (may be in discard or played)
        card = None
        for c in hero.discard_pile:
            if c.id == defense_card_id:
                card = c
                break
        if not card:
            for c in hero.played_cards:
                if c is not None and c.id == defense_card_id:
                    card = c
                    break
        if not card:
            return StepResult(is_finished=True)

        has_secondary_movement = ActionType.MOVEMENT in card.secondary_actions
        has_primary_movement = card.primary_action == ActionType.MOVEMENT

        if has_primary_movement:
            # Case 3: Primary movement — call card effect's build_steps
            movement_steps = self._build_primary_movement_steps(state, hero, card)
        elif has_secondary_movement:
            # Case 2: Secondary movement — MoveSequenceStep
            move_val = card.secondary_actions[ActionType.MOVEMENT]
            movement_steps = [
                MoveSequenceStep(
                    unit_id=str(defender_id),
                    range_val=move_val,
                    destination_key="sj_forced_dest",
                    is_mandatory=False,
                    force_straight_line=True,
                    force_full_distance=True,
                ),
            ]
        else:
            # Case 1: No movement → nothing
            return StepResult(is_finished=True)

        # Wrap in actor switch: set defender as actor, push movement, restore
        new_steps: list[GameStep] = [
            SetActorStep(
                actor_id=str(defender_id),
                save_key="sj_saved_actor",
            ),
            *movement_steps,
            SetActorStep(
                actor_key="sj_saved_actor",
                save_key="sj_saved_actor_unused",
            ),
        ]

        return StepResult(is_finished=True, new_steps=new_steps)

    def _build_primary_movement_steps(
        self,
        state: GameState,
        hero: Hero,
        card: Card,
    ) -> list[GameStep]:
        """Build steps from the card's primary effect, injecting straight-line constraints."""
        from goa2.engine.effects import CardEffectRegistry
        from goa2.engine.stats import compute_card_stats

        effect_id = card.current_effect_id or card.effect_id
        effect = CardEffectRegistry.get(effect_id) if effect_id else None
        if not effect:
            return []

        stats = compute_card_stats(state, hero.id, card)
        steps = effect.build_steps(state, hero, card, stats)

        # Inject force_straight_line + force_full_distance into any MoveSequenceStep
        for step in steps:
            if isinstance(step, MoveSequenceStep):
                step.force_straight_line = True
                step.force_full_distance = True

        return steps

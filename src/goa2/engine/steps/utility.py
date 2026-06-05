"""Context, counting, checking, and control flow helper steps."""

from __future__ import annotations

import copy
import logging
from typing import Any

from pydantic import Field

from goa2.domain.hex import Hex
from goa2.domain.input import InputOption, InputRequestType, create_input_request
from goa2.domain.models import StepType, TargetType
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, HeroID, UnitID
from goa2.engine.filters_base import FilterCondition
from goa2.engine.steps.base import GameStep, StepResult
from goa2.engine.topology import get_topology_service

logger = logging.getLogger(__name__)


class LogMessageStep(GameStep):
    """Debugging step to print messages."""

    type: StepType = StepType.LOG_MESSAGE
    message: str

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        # Interpolate context variables
        msg = self.message.format(**context)
        logger.debug(f"   [STEP] {msg}")
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

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)
        context[self.key] = self.value
        logger.debug(f"   [CONTEXT] Set {self.key} = {self.value}")
        return StepResult(is_finished=True)


class AddContextValueStep(GameStep):
    """Adds a numeric amount to a value in execution context."""

    type: StepType = StepType.ADD_CONTEXT_VALUE
    key: str
    amount: int = 1

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)
        current = context.get(self.key, 0)
        if not isinstance(current, (int, float)):
            current = 0
        context[self.key] = current + self.amount
        logger.debug(f"   [CONTEXT] Added {self.amount} to {self.key} = {context[self.key]}")
        return StepResult(is_finished=True)


class SetActorStep(GameStep):
    """
    Swaps current_actor_id, saving the previous value to context.

    Used to temporarily change the acting player for defense card effects,
    so that filters like TeamFilter(relation="ENEMY") resolve relative to
    the defender rather than the attacker.
    """

    type: StepType = StepType.SET_ACTOR
    actor_key: str | None = None  # context key to read new actor from
    actor_id: str | None = None  # literal new actor ID
    save_key: str = "saved_actor_id"  # context key to save previous actor

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        # Save current actor
        context[self.save_key] = str(state.current_actor_id) if state.current_actor_id else None
        # Determine new actor
        new_id = self.actor_id
        if self.actor_key:
            new_id = context.get(self.actor_key)
        if new_id:
            state.current_actor_id = HeroID(str(new_id))
            logger.debug(
                f"   [SET_ACTOR] Set current_actor_id={new_id} (saved previous to {self.save_key})"
            )
        return StepResult(is_finished=True)


class RecordTargetStep(GameStep):
    """
    Appends a target ID (from context) to a list (in context).
    Used to track history for 'different target' filters.
    """

    type: StepType = StepType.RECORD_TARGET
    input_key: str  # The key holding the current target ID
    output_list_key: str  # The key for the list of IDs

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        target_id = context.get(self.input_key)
        if target_id:
            if self.output_list_key not in context:
                context[self.output_list_key] = []
            if isinstance(context[self.output_list_key], list):
                context[self.output_list_key].append(target_id)
                logger.debug(f"   [LOGIC] Recorded {target_id} to {self.output_list_key}")
        return StepResult(is_finished=True)


class RecordHexStep(GameStep):
    """
    Records a unit's current hex position to context.
    Used to remember a unit's position before it moves or is defeated,
    so that another unit can move into that space later (e.g., Onslaught).

    The hex is stored as a dict (q, r, s) for JSON serialization.
    """

    type: StepType = StepType.RECORD_HEX
    unit_id: str | None = None  # Literal unit ID
    unit_key: str | None = None  # Or read from context
    output_key: str  # The key where hex dict will be stored

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        unit_id = self.unit_id
        if not unit_id and self.unit_key:
            unit_id = context.get(self.unit_key)
        if not unit_id:
            logger.debug("   [RECORD_HEX] No unit_id provided")
            return StepResult(is_finished=True)

        entity_hex = state.entity_locations.get(BoardEntityID(unit_id))
        if not entity_hex:
            logger.debug(f"   [RECORD_HEX] Unit {unit_id} not on board")
            return StepResult(is_finished=True)

        context[self.output_key] = entity_hex.model_dump()
        logger.debug(f"   [RECORD_HEX] Recorded hex for {unit_id} at {entity_hex}")
        return StepResult(is_finished=True)


class CheckDistanceStep(GameStep):
    """
    Checks topology-aware distance between two units and stores the result
    (True/None) in context based on operator/threshold.

    Stores True when the distance comparison passes, and None when it fails
    (matching CheckContextConditionStep semantics for active_if_key).

    Used by Misa's RED ranged cards to gate a conditional push based on
    whether the target is at max range (==range) or not adjacent (>1).
    """

    type: StepType = StepType.CHECK_DISTANCE
    unit_a_id: str | None = None
    unit_a_key: str | None = None
    unit_b_id: str | None = None
    unit_b_key: str | None = None
    operator: str = "=="  # ">=", ">", "==", "<=", "<", "!="
    threshold: int = 1
    output_key: str = "distance_check"

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        u_a = self.unit_a_id or (context.get(self.unit_a_key) if self.unit_a_key else None)
        u_b = self.unit_b_id or (context.get(self.unit_b_key) if self.unit_b_key else None)
        if not u_a or not u_b:
            context[self.output_key] = None
            return StepResult(is_finished=True)

        loc_a = state.entity_locations.get(BoardEntityID(str(u_a)))
        loc_b = state.entity_locations.get(BoardEntityID(str(u_b)))
        if not loc_a or not loc_b:
            context[self.output_key] = None
            return StepResult(is_finished=True)

        topology = get_topology_service()
        dist = topology.distance(loc_a, loc_b, state)

        ops = {
            ">=": dist >= self.threshold,
            ">": dist > self.threshold,
            "==": dist == self.threshold,
            "<=": dist <= self.threshold,
            "<": dist < self.threshold,
            "!=": dist != self.threshold,
        }
        result = ops.get(self.operator, False)
        context[self.output_key] = True if result else None
        logger.debug(
            f"   [CHECK_DISTANCE] {u_a}<->{u_b} dist={dist} {self.operator} {self.threshold} -> {result}"
        )
        return StepResult(is_finished=True)


class ComputeDistanceStep(GameStep):
    """
    Computes the topology-aware distance between a unit and either another
    unit or a previously recorded hex (via RecordHexStep). Stores the integer
    distance in context[output_key].

    Used by Silverarrow's Lead Astray family: snapshot the dragged unit's
    starting hex, drag it, then compute how far it actually moved so the
    follow-up self-move is bounded by that same distance.
    """

    type: StepType = StepType.COMPUTE_DISTANCE
    unit_id: str | None = None
    unit_key: str | None = None
    other_unit_id: str | None = None
    other_unit_key: str | None = None
    hex_key: str | None = None  # Read a recorded hex dict from context
    output_key: str = "distance"

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        u_id = self.unit_id or (context.get(self.unit_key) if self.unit_key else None)
        if not u_id:
            context[self.output_key] = 0
            return StepResult(is_finished=True)
        loc_a = state.entity_locations.get(BoardEntityID(str(u_id)))
        if not loc_a:
            context[self.output_key] = 0
            return StepResult(is_finished=True)

        loc_b: Hex | None = None
        if self.hex_key:
            hex_data = context.get(self.hex_key)
            if isinstance(hex_data, dict):
                loc_b = Hex(**hex_data)
            elif isinstance(hex_data, Hex):
                loc_b = hex_data
        else:
            other_id = self.other_unit_id or (
                context.get(self.other_unit_key) if self.other_unit_key else None
            )
            if other_id:
                loc_b = state.entity_locations.get(BoardEntityID(str(other_id)))

        if not loc_b:
            context[self.output_key] = 0
            return StepResult(is_finished=True)

        topology = get_topology_service()
        dist = topology.distance(loc_a, loc_b, state)
        context[self.output_key] = dist
        logger.debug(f"   [COMPUTE_DISTANCE] {u_id} -> stored {dist} in {self.output_key}")
        return StepResult(is_finished=True)


class MayRepeatNTimesStep(GameStep):
    """
    Allows repeating a sequence of steps up to N times.
    Each repeat is optional (player can decline).
    Tracks state via repeats_done internal counter.
    """

    type: StepType = StepType.MAY_REPEAT_ONCE
    steps_template: list[GameStep] = Field(default_factory=list)
    max_repeats: int = 1
    prompt: str = "Repeat action?"

    # Internal state, preserved when pushed back to stack
    repeats_done: int = 0

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        # Check if we've hit the limit
        if self.repeats_done >= self.max_repeats:
            return StepResult(is_finished=True)

        if self.should_skip(context):
            return StepResult(is_finished=True)

        actor_id = state.current_actor_id
        if not actor_id:
            return StepResult(is_finished=True)

        # 1. Validation Check (Early exit if blocked)
        res = state.validator.can_repeat_action(state, str(actor_id), context)
        if not res.allowed:
            logger.debug(f"   [REPEAT] Blocked by validation: {res.reason}")
            return StepResult(is_finished=True)

        # 2. Input Handling
        if self.pending_input:
            selection = self.pending_input.get("selection")
            self.pending_input = None
            if selection == "YES":
                self.repeats_done += 1
                logger.debug(
                    f"   [REPEAT] Confirmed ({self.repeats_done}/{self.max_repeats}). Spawning steps."
                )
                # Deepcopy template steps
                new_steps = [copy.deepcopy(s) for s in self.steps_template]

                # Push ourselves back onto the stack to handle potential subsequent repeats
                # BUT only if we haven't reached the max yet
                if self.repeats_done < self.max_repeats:
                    return StepResult(is_finished=False, new_steps=new_steps)
                else:
                    return StepResult(is_finished=True, new_steps=new_steps)
            else:
                logger.debug("   [REPEAT] Declined.")
                return StepResult(is_finished=True)

        # 3. Request Input
        return StepResult(
            requires_input=True,
            input_request=create_input_request(
                request_type=InputRequestType.SELECT_OPTION,
                player_id=str(actor_id),
                prompt=f"{self.prompt} ({self.repeats_done}/{self.max_repeats} done)",
                options=[
                    InputOption(id="YES", text="Yes"),
                    InputOption(id="NO", text="No"),
                ],
            ),
        )


class MayRepeatOnceStep(MayRepeatNTimesStep):
    """
    Backward compatibility wrapper.
    """

    max_repeats: int = 1


class ValidateRepeatStep(GameStep):
    """
    Checks if the actor is allowed to repeat an action.
    Consults ValidationService.can_repeat_action().
    Can optionally AND the result with an existing context flag.
    """

    type: StepType = StepType.VALIDATE_REPEAT
    actor_id: str | None = None
    and_with_key: str | None = None  # If set, combines with this boolean key
    output_key: str = "can_repeat"

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        act_id = self.actor_id or state.current_actor_id
        if not act_id:
            context[self.output_key] = False
            return StepResult(is_finished=True)

        res = state.validator.can_repeat_action(state, str(act_id), context)
        val = res.allowed

        if self.and_with_key:
            prev_val = context.get(self.and_with_key, False)
            val = val and prev_val
            logger.debug(
                f"   [CHECK] Repeat Validation: Validator={res.allowed}, Context({self.and_with_key})={prev_val} -> Result={val}"
            )
        else:
            logger.debug(f"   [CHECK] Repeat Validation: Result={val}")

        context[self.output_key] = val
        return StepResult(is_finished=True)


class CheckAdjacencyStep(GameStep):
    """
    Checks if two units are adjacent and sets a context flag.
    Used for conditional effects (e.g. Ebb and Flow).
    """

    type: StepType = StepType.CHECK_ADJACENCY
    unit_a_id: str | None = None
    unit_b_id: str | None = None
    unit_a_key: str | None = None
    unit_b_key: str | None = None
    output_key: str = "is_adjacent"

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
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

        # Use topology-aware adjacency (respects reality splits)
        topology = get_topology_service()
        is_adjacent = topology.are_adjacent(loc_a, loc_b, state)
        context[self.output_key] = is_adjacent
        logger.debug(f"   [CHECK] Adjacency between {u_a} and {u_b}: {is_adjacent}")

        return StepResult(is_finished=True)


class CountAdjacentEnemiesStep(GameStep):
    """
    Counts enemy units adjacent to the current actor and stores a computed
    bonus value in context.

    Formula: bonus = max(0, count - subtract) * multiplier

    where:
    - count = number of adjacent enemy units
    - subtract = typically 1 to exclude the attack target from the bonus
    - multiplier = per-unit bonus value

    Used by Xargatha's adjacency-scaling cards (Threatening Slash, Long Thrust, etc.).
    """

    type: StepType = StepType.COUNT_ADJACENT_ENEMIES
    output_key: str = "adjacent_enemy_bonus"
    multiplier: int = 1
    subtract: int = 0  # Subtract from count before multiplying (e.g. 1 for "other" enemies)

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        actor_id = state.current_actor_id
        if not actor_id:
            context[self.output_key] = 0
            return StepResult(is_finished=True)

        actor = state.get_unit(UnitID(str(actor_id)))
        actor_hex = state.entity_locations.get(BoardEntityID(str(actor_id)))

        if not actor or not actor_hex or not hasattr(actor, "team"):
            context[self.output_key] = 0
            return StepResult(is_finished=True)

        count = 0
        for neighbor in actor_hex.neighbors():
            tile = state.board.get_tile(neighbor)
            if tile and tile.occupant_id:
                entity = state.get_unit(tile.occupant_id)
                if entity and hasattr(entity, "team") and entity.team != actor.team:
                    count += 1

        bonus = max(0, count - self.subtract) * self.multiplier
        context[self.output_key] = bonus
        logger.debug(
            f"   [COUNT] Adjacent enemies: {count}, subtract={self.subtract}, "
            f"multiplier={self.multiplier}, bonus={bonus}"
        )

        return StepResult(is_finished=True)


class CheckUnitTypeStep(GameStep):
    """
    Checks if a unit is a specific type (HERO or MINION) and stores boolean result.
    Used for conditional effects that behave differently for heroes vs minions.
    """

    type: StepType = StepType.CHECK_UNIT_TYPE
    unit_id: str | None = None  # Direct unit ID
    unit_key: str | None = None  # Read from context
    expected_type: str = "HERO"  # "HERO" or "MINION"
    output_key: str = "is_expected_type"

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        # Resolve unit ID
        actual_id = self.unit_id
        if not actual_id and self.unit_key:
            actual_id = context.get(self.unit_key)

        if not actual_id:
            logger.debug(f"   [CHECK-TYPE] No unit specified. Setting {self.output_key}=False")
            context[self.output_key] = False
            return StepResult(is_finished=True)

        # Check type
        is_hero = state.get_hero(HeroID(str(actual_id))) is not None

        if self.expected_type == "HERO":
            result = is_hero
        elif self.expected_type == "MINION":
            result = not is_hero
        else:
            logger.debug(f"   [CHECK-TYPE] Unknown type '{self.expected_type}'. Defaulting False.")
            result = False

        context[self.output_key] = result
        logger.debug(
            f"   [CHECK-TYPE] Unit {actual_id} is_hero={is_hero}, expected={self.expected_type} -> {result}"
        )
        return StepResult(is_finished=True)


class CombineBooleanContextStep(GameStep):
    """
    Combines two boolean context values using AND or OR.
    Used for conditional effects that require multiple conditions to be true.

    Example: Kinetic Repulse needs both collision=True AND is_hero=True
    """

    type: StepType = StepType.COMBINE_BOOLEAN_CONTEXT
    key_a: str  # First boolean context key
    key_b: str  # Second boolean context key
    output_key: str  # Where to store result
    operation: str = "AND"  # "AND" or "OR"

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        val_a = bool(context.get(self.key_a, False))
        val_b = bool(context.get(self.key_b, False))

        if self.operation == "AND":
            result = val_a and val_b
        elif self.operation == "OR":
            result = val_a or val_b
        else:
            logger.debug(f"   [COMBINE] Unknown operation '{self.operation}'. Defaulting AND.")
            result = val_a and val_b

        context[self.output_key] = result
        logger.debug(
            f"   [COMBINE] {self.key_a}={val_a} {self.operation} {self.key_b}={val_b} -> {result}"
        )
        return StepResult(is_finished=True)


class CountStep(GameStep):
    """
    Counts entities matching filters and stores the count in context.
    Uses the same target_type + filters system as SelectStep.
    No input prompt, no mandatory/optional logic — just counts and stores.
    """

    type: StepType = StepType.COUNT
    target_type: TargetType = TargetType.UNIT
    filters: list[FilterCondition] = Field(default_factory=list)
    output_key: str = "count_result"
    skip_immunity_filter: bool = True
    skip_self_filter: bool = False  # Set True to count self

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:

        if self.should_skip(context):
            context[self.output_key] = 0
            return StepResult(is_finished=True)

        # Gather candidates by target_type (same logic as SelectStep)
        candidates: list[Any] = []
        if self.target_type == TargetType.UNIT:
            all_entities = list(state.entity_locations.keys())
            candidates = [eid for eid in all_entities if state.get_unit(UnitID(str(eid)))]
        elif self.target_type == TargetType.UNIT_OR_TOKEN:
            candidates = state.get_units_and_tokens()
        elif self.target_type == TargetType.HEX:
            candidates = list(state.board.tiles.keys())

        # Build effective filters
        from goa2.engine.filters_units import ExcludeIdentityFilter, ImmunityFilter

        effective_filters = list(self.filters)
        if self.target_type in (TargetType.UNIT, TargetType.UNIT_OR_TOKEN):
            # Auto-add ExcludeIdentityFilter for self-exclusion
            if not self.skip_self_filter:
                has_self_exclusion = any(
                    isinstance(f, ExcludeIdentityFilter) and f.exclude_self
                    for f in effective_filters
                )
                if not has_self_exclusion:
                    effective_filters.append(ExcludeIdentityFilter(exclude_self=True))

            # Auto-add ImmunityFilter
            if not self.skip_immunity_filter:
                has_immunity = any(isinstance(f, ImmunityFilter) for f in effective_filters)
                if not has_immunity:
                    effective_filters.append(ImmunityFilter())

        # Apply filters
        count = 0
        for c in candidates:
            is_valid = True
            for f in effective_filters:
                if not f.apply(c, state, context):
                    is_valid = False
                    break
            if is_valid:
                count += 1

        context[self.output_key] = count
        logger.debug(f"   [COUNT] {self.target_type.value} matching filters: {count}")
        return StepResult(is_finished=True)


class CheckContextConditionStep(GameStep):
    """
    Evaluates context[input_key] against a threshold using an operator.
    Stores True/False in context[output_key].
    """

    type: StepType = StepType.CHECK_CONTEXT_CONDITION
    input_key: str
    operator: str = ">="  # ">=", ">", "==", "<=", "<", "!="
    threshold: int = 1
    output_key: str = "condition_met"

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        value = context.get(self.input_key, 0)
        if not isinstance(value, (int, float)):
            value = 0

        ops = {
            ">=": value >= self.threshold,
            ">": value > self.threshold,
            "==": value == self.threshold,
            "<=": value <= self.threshold,
            "<": value < self.threshold,
            "!=": value != self.threshold,
        }
        result = ops.get(self.operator, False)
        # Store True or None so active_if_key skips failed conditions.
        context[self.output_key] = True if result else None
        logger.debug(
            f"   [CHECK] {self.input_key}={value} {self.operator} {self.threshold} -> {result}"
        )
        return StepResult(is_finished=True)


class CheckHeroDefeatedThisRoundStep(GameStep):
    """Sets context[output_key] to True if any hero was defeated this round, else None."""

    type: StepType = StepType.CHECK_HERO_DEFEATED_THIS_ROUND
    output_key: str

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if state.heroes_defeated_this_round:
            context[self.output_key] = True
        else:
            context[self.output_key] = None
        return StepResult(is_finished=True)


class ComputeHexStep(GameStep):
    """
    Generic hex vector arithmetic step.

    Computes a hex position relative to two reference points:
      result = target + normalize(target - origin) * scale

    Used by Blink Strike to compute the hex behind an enemy.
    """

    type: StepType = StepType.COMPUTE_HEX
    origin_key: str | None = None  # context key for origin; None = current actor
    target_key: str = ""  # context key for reference unit
    scale: int = 1  # multiplier for direction vector
    output_key: str = "computed_hex"

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        # Resolve origin hex
        origin_uid = context.get(self.origin_key) if self.origin_key else state.current_actor_id
        if not origin_uid:
            return StepResult(is_finished=True)

        origin_hex = state.entity_locations.get(BoardEntityID(str(origin_uid)))
        if not origin_hex:
            return StepResult(is_finished=True)

        # Resolve target hex (from unit position)
        target_uid = context.get(self.target_key)
        if not target_uid:
            return StepResult(is_finished=True)

        target_hex = state.entity_locations.get(BoardEntityID(str(target_uid)))
        if not target_hex:
            return StepResult(is_finished=True)

        # Compute direction: normalize(target - origin)
        diff = target_hex - origin_hex
        dist = origin_hex.distance(target_hex)
        if dist == 0:
            return StepResult(is_finished=True)

        unit_dir = Hex(
            q=diff.q // dist,
            r=diff.r // dist,
            s=diff.s // dist,
        )

        # Compute result: target + direction * scale
        result = target_hex + Hex(
            q=unit_dir.q * self.scale,
            r=unit_dir.r * self.scale,
            s=unit_dir.s * self.scale,
        )

        context[self.output_key] = result
        return StepResult(is_finished=True)


class ForEachStep(GameStep):
    """
    Executes a template of steps for each item in a context list.

    For each item in the list:
    1. Sets context[item_key] = current item
    2. Spawns deep-copied template steps

    Uses is_finished=False to stay on stack until all items processed.
    """

    type: StepType = StepType.FOR_EACH
    list_key: str  # Context key containing the list
    item_key: str  # Context key to store current item
    steps_template: list[GameStep] = Field(default_factory=list)

    # Internal state
    current_index: int = 0

    def resolve(self, state: GameState, context: dict[str, Any]) -> StepResult:
        items = context.get(self.list_key, [])

        # All items processed?
        if self.current_index >= len(items):
            logger.debug(f"   [FOR-EACH] All {len(items)} items processed.")
            return StepResult(is_finished=True)

        # Set current item in context
        current_item = items[self.current_index]
        context[self.item_key] = current_item
        logger.debug(
            f"   [FOR-EACH] Processing item {self.current_index + 1}/{len(items)}: {current_item}"
        )

        # Advance index for next iteration
        self.current_index += 1

        # Deep copy template for this iteration
        new_steps = [copy.deepcopy(s) for s in self.steps_template]

        # More items remaining? Stay on stack
        if self.current_index < len(items):
            return StepResult(is_finished=False, new_steps=new_steps)
        else:
            # Last item - finish after these steps
            return StepResult(is_finished=True, new_steps=new_steps)

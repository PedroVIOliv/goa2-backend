# Just updated filters.py to add PreserveDistanceFilter
from __future__ import annotations
from typing import Optional, List, Any, Literal
from pydantic import BaseModel

from goa2.domain.models.enums import MinionType
from goa2.domain.state import GameState
from goa2.domain.models import Minion, Hero, Unit, FilterType
from goa2.domain.models.token import Token
from goa2.domain.hex import Hex
from goa2.domain.types import BoardEntityID, UnitID
from goa2.engine.topology import get_topology_service

# -----------------------------------------------------------------------------
# Base Filter
# -----------------------------------------------------------------------------


class FilterCondition(BaseModel):
    """
    Base class for all selection filters.
    """

    type: FilterType

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        """
        Returns True if the candidate passes the filter.
        Candidate can be a UnitID (str) or a Hex.
        """
        raise NotImplementedError


# -----------------------------------------------------------------------------
# Hex Filters
# -----------------------------------------------------------------------------


class ObstacleFilter(FilterCondition):
    type: FilterType = FilterType.OCCUPIED
    is_obstacle: bool = False  # False = Must be empty, True = Must be occupied
    exclude_id: Optional[str] = (
        None  # If set, ignore this entity when checking occupancy
    )

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if isinstance(candidate, Hex):
            tile = state.board.get_tile(candidate)

            # Get actor for context-aware check (Static Barrier)
            actor_id = str(state.current_actor_id) if state.current_actor_id else None

            # Use validation service for context-aware obstacle check
            is_obs = state.validator.is_obstacle_for_actor(
                state, candidate, actor_id, context
            )

            # Handle exclude_id (for "ignore self" scenarios)
            if self.exclude_id and tile.occupant_id == self.exclude_id:
                return True

            return is_obs == self.is_obstacle
        return self.is_obstacle


class TerrainFilter(FilterCondition):
    type: FilterType = FilterType.TERRAIN
    is_terrain: bool = True

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if isinstance(candidate, Hex):
            tile = state.board.get_tile(candidate)
            if not tile:
                return self.is_terrain
            is_t = (
                state.validator.is_terrain_hex(state, candidate)
                if state.validator
                else tile.is_terrain
            )
            return is_t == self.is_terrain
        return self.is_terrain


class RangeFilter(FilterCondition):
    """
    Checks distance from an origin.
    Origin is usually the current actor, but can be customized.
    """

    type: FilterType = FilterType.RANGE
    max_range: int
    min_range: int = 0
    origin_id: Optional[str] = None  # Literal ID
    origin_key: Optional[str] = None  # Key in context to find ID

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        origin_uid = None

        if self.origin_id:
            origin_uid = self.origin_id
        elif self.origin_key:
            origin_uid = context.get(self.origin_key)

        if not origin_uid:
            origin_uid = state.current_actor_id

        if not origin_uid:
            return False

        # Use Unified Location
        origin_hex = state.entity_locations.get(BoardEntityID(str(origin_uid)))
        if not origin_hex:
            return False

        target_hex = None
        if isinstance(candidate, Hex):
            target_hex = candidate
        elif isinstance(candidate, str):  # EntityID
            target_hex = state.entity_locations.get(BoardEntityID(candidate))

        if not target_hex:
            return False

        # Use topology-aware distance (respects reality splits)
        topology = get_topology_service()
        dist = topology.distance(origin_hex, target_hex, state)
        return self.min_range <= dist <= self.max_range


# -----------------------------------------------------------------------------
# Unit Filters
# -----------------------------------------------------------------------------


class TeamFilter(FilterCondition):
    type: FilterType = FilterType.TEAM
    relation: Literal["FRIENDLY", "ENEMY", "SELF"]
    # RELATIVE to the actor executing the step

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        actor_id = state.current_actor_id
        if not actor_id:
            return False

        actor = state.get_entity(BoardEntityID(actor_id))
        target = (
            state.get_entity(BoardEntityID(candidate))
            if isinstance(candidate, str)
            else None
        )

        if not actor or not target:
            # Only warn if strict logic required. For now, fail silently (filter mismatch)
            return False

        # Ensure both have 'team' attribute (Tokens might not)
        if not hasattr(actor, "team") or not hasattr(target, "team"):
            return False

        # Explicitly check if attributes are not None for Mypy
        actor_team = getattr(actor, "team", None)
        target_team = getattr(target, "team", None)

        if actor_team is None or target_team is None:
            return False

        if self.relation == "SELF":
            return actor.id == target.id

        is_same_team = actor_team == target_team

        if self.relation == "FRIENDLY":
            return is_same_team and (actor.id != target.id)
        elif self.relation == "ENEMY":
            return not is_same_team

        return False


class UnitTypeFilter(FilterCondition):
    type: FilterType = FilterType.UNIT_TYPE
    unit_type: Literal["HERO", "MINION", "TOKEN"]

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        entity = (
            state.get_entity(BoardEntityID(candidate))
            if isinstance(candidate, str)
            else None
        )
        if not entity:
            return False

        if self.unit_type == "HERO":
            return isinstance(entity, Hero)
        elif self.unit_type == "MINION":
            return isinstance(entity, Minion)
        elif self.unit_type == "TOKEN":
            return isinstance(entity, Token)
        return False


class MinionTypesFilter(FilterCondition):
    type: FilterType = FilterType.MINION_TYPES
    minion_types: List[MinionType]

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        entity = (
            state.get_entity(BoardEntityID(candidate))
            if isinstance(candidate, str)
            else None
        )
        if not entity or not isinstance(entity, Minion):
            return False

        return entity.type in self.minion_types


class AdjacencyFilter(FilterCondition):
    """
    Requires the target to be adjacent to a unit matching specific tags.
    E.g. "Adjacent to a Friendly Hero"
    """

    type: FilterType = FilterType.ADJACENCY
    target_tags: List[Literal["FRIENDLY", "ENEMY", "HERO", "MINION"]] 

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        cand_hex = None
        if isinstance(candidate, Hex):
            cand_hex = candidate
        elif isinstance(candidate, str):
            cand_hex = state.entity_locations.get(BoardEntityID(candidate))

        if not cand_hex:
            return False

        # Use topology-aware neighbors (respects reality splits)
        topology = get_topology_service()
        neighbors = topology.get_connected_neighbors(cand_hex, state)

        for n in neighbors:
            tile = state.board.get_tile(n)
            if not tile or not tile.occupant_id:
                continue

            # Use Unified Lookup
            occupant = state.get_entity(tile.occupant_id)
            if not occupant:
                continue

            actor_id = state.current_actor_id
            actor = state.get_entity(BoardEntityID(str(actor_id))) if actor_id else None

            if not actor:
                continue

            matches = True
            for tag in self.target_tags:
                if tag == "FRIENDLY":
                    # Mypy safety checks
                    occ_team = getattr(occupant, "team", None)
                    act_team = getattr(actor, "team", None)
                    if occ_team is None or act_team is None:
                        matches = False
                    elif occ_team != act_team or occupant.id == actor.id:
                        matches = False
                elif tag == "ENEMY":
                    occ_team = getattr(occupant, "team", None)
                    act_team = getattr(actor, "team", None)
                    if occ_team is None or act_team is None:
                        matches = False
                    elif occ_team == act_team:
                        matches = False
                elif tag == "HERO":
                    if not isinstance(occupant, Hero):
                        matches = False
                elif tag == "MINION":
                    if not isinstance(occupant, Minion):
                        matches = False

            if matches:
                return True

        return False


class ImmunityFilter(FilterCondition):
    """
    Filters out candidates that are Immune.

    Checks two sources of immunity:
    1. Standard minion immunity (Heavy minions with friendly support)
    2. ATTACK_IMMUNITY effects (e.g., Expert Duelist - immune to attacks except from specific attacker)
    """

    type: FilterType = FilterType.IMMUNITY

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        from goa2.engine import rules  # Import inside to be safe
        from goa2.domain.models.effect import EffectType
        from goa2.domain.models.enums import ActionType

        target = (
            state.get_entity(BoardEntityID(candidate))
            if isinstance(candidate, str)
            else None
        )
        if not target:
            return False

        # Check 1: Standard minion immunity (Heavy with support)
        if isinstance(target, Unit):
            if rules.is_immune(target, state):
                return False  # Immune = fails filter

        # Check 2: ATTACK_IMMUNITY effects
        # Only applies when current action is ATTACK
        current_action = context.get("current_action_type")
        if current_action == ActionType.ATTACK:
            current_actor_id = (
                str(state.current_actor_id) if state.current_actor_id else None
            )

            # Look for ATTACK_IMMUNITY effects where target is the protected unit
            for effect in state.active_effects:
                if effect.effect_type != EffectType.ATTACK_IMMUNITY:
                    continue
                if not effect.is_active:
                    continue

                # The effect protects its source_id (the hero who played the defense card)
                if effect.source_id != candidate:
                    continue

                # Check if current attacker is in the exception list
                if current_actor_id and current_actor_id in effect.except_attacker_ids:
                    continue  # This attacker is allowed to target

                # Target is immune to this attack
                return False

        return True  # Passes filter (not immune)


class SpawnPointFilter(FilterCondition):
    """
    Filters hexes based on whether they have a spawn point.
    """

    type: FilterType = FilterType.SPAWN_POINT
    has_spawn_point: bool = False

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if isinstance(candidate, Hex):
            tile = state.board.get_tile(candidate)
            if not tile:
                return False
            return (tile.spawn_point is not None) == self.has_spawn_point
        return False


class AdjacentSpawnPointFilter(FilterCondition):
    """
    Filters hexes based on proximity to spawn points.
    """

    type: FilterType = FilterType.ADJACENT_SPAWN_POINT
    is_empty: bool = True
    must_not_have: bool = (
        True  # True means "not adjacent to", False means "must be adjacent to"
    )

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        cand_hex = None
        if isinstance(candidate, Hex):
            cand_hex = candidate
        elif isinstance(candidate, str):
            cand_hex = state.entity_locations.get(BoardEntityID(candidate))

        if not cand_hex:
            return False

        # Use topology-aware neighbors (respects reality splits)
        topology = get_topology_service()
        neighbors = topology.get_connected_neighbors(cand_hex, state)
        has_adj = False
        for n in neighbors:
            tile = state.board.get_tile(n)
            if tile and tile.spawn_point:
                if self.is_empty:
                    if not state.validator.is_obstacle_for_actor(
                        state,
                        n,
                        str(state.current_actor_id) if state.current_actor_id else None,
                        context,
                    ):
                        has_adj = True
                        break
                else:
                    has_adj = True
                    break

        if self.must_not_have:
            return not has_adj
        return has_adj


class AdjacencyToContextFilter(FilterCondition):
    """
    Selects units adjacent to the entity ID stored in a context variable.
    """

    type: FilterType = FilterType.ADJACENCY_TO_CONTEXT
    target_key: str

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        target_id = context.get(self.target_key)

        if not target_id:
            return False

        target_hex = state.entity_locations.get(BoardEntityID(target_id))

        if not target_hex:
            return False

        cand_hex = None

        if isinstance(candidate, Hex):
            cand_hex = candidate
        elif isinstance(candidate, str):
            cand_hex = state.entity_locations.get(BoardEntityID(candidate))

        if not cand_hex:
            return False

        # "Check via tile": Ensure both are valid board positions
        if not state.board.is_on_map(target_hex) or not state.board.is_on_map(cand_hex):
            return False
        # Use topology-aware adjacency (respects reality splits)
        topology = get_topology_service()
        return topology.are_adjacent(cand_hex, target_hex, state)


class ExcludeIdentityFilter(FilterCondition):
    """
    Excludes specific unit IDs from selection.
    Can exclude self and/or IDs found in context keys.
    """

    type: FilterType = FilterType.EXCLUDE_IDENTITY
    exclude_self: bool = True
    exclude_keys: List[str] = []

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, str):
            return True  # Only applies to Units (IDs)
        if self.exclude_self:
            if candidate == state.current_actor_id:
                return False
        for key in self.exclude_keys:
            val = context.get(key)
            if val is None:
                continue
            if isinstance(val, list):
                if candidate in val:
                    return False
            elif val == candidate:
                return False
        return True


class HasEmptyNeighborFilter(FilterCondition):
    """
    Ensures the candidate unit has at least one valid empty neighbor to move to.
    Prevents selecting 'trapped' units for movement effects.
    """

    type: FilterType = FilterType.HAS_EMPTY_NEIGHBOR

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        cand_hex = None
        if isinstance(candidate, str):
            cand_hex = state.entity_locations.get(BoardEntityID(candidate))
        elif isinstance(candidate, Hex):
            cand_hex = candidate
        if not cand_hex:
            return False
        # Use topology-aware neighbors (respects reality splits)
        topology = get_topology_service()
        neighbors = topology.get_connected_neighbors(cand_hex, state)

        # Get actor for context-aware obstacle check (Static Barrier support)
        actor_id = str(state.current_actor_id) if state.current_actor_id else None

        for n in neighbors:
            # Use context-aware obstacle check to respect Static Barrier effects
            is_obs = state.validator.is_obstacle_for_actor(state, n, actor_id)
            if not is_obs:
                return True
        return False


class ForcedMovementByEnemyFilter(FilterCondition):
    """
    Checks if the candidate is protected from forced movement by enemies.
    Delegates to ValidationService.
    """

    type: FilterType = FilterType.FORCED_MOVEMENT_BY_ENEMY

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, str):
            return False

        actor_id = state.current_actor_id
        if not actor_id:
            return True

        result = state.validator.can_be_placed(
            state=state, unit_id=candidate, actor_id=actor_id, context=context
        )

        return result.allowed


class CanBePlacedByActorFilter(FilterCondition):
    """
    Filters out units that cannot be placed by the current actor.
    Delegates to ValidationService for actual logic.
    """

    type: FilterType = FilterType.CAN_BE_PLACED_BY_ACTOR

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, str):
            return False

        actor_id = state.current_actor_id
        if not actor_id:
            return True  # No actor context, allow selection

        result = state.validator.can_be_placed(
            state=state, unit_id=candidate, actor_id=actor_id, context=context
        )

        return result.allowed


class MovementPathFilter(FilterCondition):
    """
    Filters hexes to only those reachable via valid movement path.
    """

    type: FilterType = FilterType.MOVEMENT_PATH
    range_val: int
    unit_id: Optional[str] = None
    unit_key: Optional[str] = None
    pass_through_obstacles: bool = False

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, Hex):
            return False

        uid = self.unit_id
        if not uid and self.unit_key:
            uid = context.get(self.unit_key)

        if not uid:
            uid = state.current_actor_id

        if not uid:
            return False

        start_hex = state.entity_locations.get(BoardEntityID(str(uid)))
        if not start_hex:
            return False

        # Always allow selecting the current hex (staying put)
        if candidate == start_hex:
            return True

        # If range is 0 or less, only the current hex was allowed (handled above)
        if self.range_val <= 0:
            return False

        from goa2.engine import rules

        return rules.validate_movement_path(
            board=state.board,
            start=start_hex,
            end=candidate,
            max_steps=self.range_val,
            state=state,
            actor_id=str(state.current_actor_id) if state.current_actor_id else None,
            pass_through_obstacles=self.pass_through_obstacles,
        )


class LineBehindTargetFilter(FilterCondition):
    """
    Selects hexes (or units on hexes) that are in a straight line directly BEHIND a target.
    Direction is defined by Origin -> Target.
    """

    type: FilterType = FilterType.LINE_BEHIND_TARGET
    target_key: str
    length: int = 1
    origin_id: Optional[str] = None

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        # Resolve Target Location
        target_id = context.get(self.target_key)
        if not target_id:
            return False

        target_hex = state.entity_locations.get(BoardEntityID(target_id))
        if not target_hex:
            return False
        if isinstance(target_id, Hex):
            target_hex = target_id
        # Resolve Origin Location
        origin_uid = self.origin_id or state.current_actor_id
        if not origin_uid:
            return False

        origin_hex = state.entity_locations.get(BoardEntityID(str(origin_uid)))
        if not origin_hex:
            return False

        # Resolve Candidate Location
        cand_hex = None
        if isinstance(candidate, Hex):
            cand_hex = candidate
        elif isinstance(candidate, str):
            cand_hex = state.entity_locations.get(BoardEntityID(candidate))

        if not cand_hex:
            return False

        # Logic:
        # 1. Origin and Target must be in straight line to establish direction.
        direction_idx = origin_hex.direction_to(target_hex)
        if direction_idx is None:
            return False

        # 2. Target and Candidate must be in same direction from Target
        # Note: Candidate must be strictly BEHIND target, not AT target.
        if cand_hex == target_hex:
            return False

        cand_dir = target_hex.direction_to(cand_hex)
        if cand_dir != direction_idx:
            return False

        # 3. Distance check (topology-aware)
        topology = get_topology_service()
        dist = topology.distance(target_hex, cand_hex, state)
        return dist <= self.length


class NotInStraightLineFilter(FilterCondition):
    """
    Excludes targets in a straight line from the actor.
    Uses topology-aware is_straight_line() (respects reality splits).

    Per card text: "Units adjacent to you are in a straight line from you."
    Adjacent hexes are always in a straight line in cube coordinates.

    Used by: Charged Boomerang, Telekinesis, Mass Telekinesis, Thunder Boomerang
    """

    type: FilterType = FilterType.NOT_IN_STRAIGHT_LINE
    origin_id: Optional[str] = None  # Literal ID (defaults to current actor)
    origin_key: Optional[str] = None  # Key in context to find ID

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        # Resolve origin
        origin_uid = None
        if self.origin_id:
            origin_uid = self.origin_id
        elif self.origin_key:
            origin_uid = context.get(self.origin_key)

        if not origin_uid:
            origin_uid = state.current_actor_id

        if not origin_uid:
            return False

        origin_hex = state.entity_locations.get(BoardEntityID(str(origin_uid)))
        if not origin_hex:
            return False

        # Resolve candidate hex
        target_hex = None
        if isinstance(candidate, Hex):
            target_hex = candidate
        elif isinstance(candidate, str):
            target_hex = state.entity_locations.get(BoardEntityID(candidate))

        if not target_hex:
            return False

        # Use topology-aware is_straight_line (respects reality splits)
        # Returns True if NOT in straight line (i.e., valid target)
        return not get_topology_service().is_straight_line(
            origin_hex, target_hex, state
        )


class InStraightLineFilter(FilterCondition):
    """
    Includes targets in a straight line from the actor.
    Uses topology-aware is_straight_line() (respects reality splits).

    Per card text: "Units adjacent to you are in a straight line from you."
    Adjacent hexes are always in a straight line in cube coordinates.

    Used by: Cards that require targets to be aligned with the actor
    """

    type: FilterType = FilterType.IN_STRAIGHT_LINE
    origin_id: Optional[str] = None  # Literal ID (defaults to current actor)
    origin_key: Optional[str] = None  # Key in context to find ID

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        # Resolve origin
        origin_uid = None
        if self.origin_id:
            origin_uid = self.origin_id
        elif self.origin_key:
            origin_uid = context.get(self.origin_key)

        if not origin_uid:
            origin_uid = state.current_actor_id

        if not origin_uid:
            return False

        origin_hex = state.entity_locations.get(BoardEntityID(str(origin_uid)))
        if not origin_hex:
            return False

        # Resolve candidate hex
        target_hex = None
        if isinstance(candidate, Hex):
            target_hex = candidate
        elif isinstance(candidate, str):
            target_hex = state.entity_locations.get(BoardEntityID(candidate))

        if not target_hex:
            return False

        # Use topology-aware is_straight_line (respects reality splits)
        # Returns True if IN straight line (i.e., valid target)
        return get_topology_service().is_straight_line(origin_hex, target_hex, state)


class FastTravelDestinationFilter(FilterCondition):
    """
    Filters hexes to only valid Fast Travel destinations.
    Rules:
    - Unit must be in a safe zone (no enemies)
    - Destination must be in same zone or adjacent safe zone
    - Destination must be empty
    """

    type: FilterType = FilterType.FAST_TRAVEL_DESTINATION
    unit_id: Optional[str] = None

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, Hex):
            return False

        uid = self.unit_id or state.current_actor_id
        if not uid:
            return False

        # Check validation first
        if not state.validator.can_fast_travel(state, str(uid)).allowed:
            return False

        unit = state.get_unit(UnitID(str(uid)))
        if not unit:
            return False

        current_hex = state.entity_locations.get(BoardEntityID(str(uid)))
        if not current_hex:
            return False

        current_zone_id = state.board.get_zone_for_hex(current_hex)
        if not current_zone_id:
            return False

        from goa2.engine.rules import get_safe_zones_for_fast_travel

        if unit.team is None:
            return False

        safe_zones = get_safe_zones_for_fast_travel(state, unit.team, current_zone_id)

        if not safe_zones:
            return False

        # Check if candidate is in a safe zone and empty
        cand_zone_id = state.board.get_zone_for_hex(candidate)
        if cand_zone_id not in safe_zones:
            return False

        tile = state.board.get_tile(candidate)
        # Note: SelectStep already filters for candidates.
        # But we must ensure it is empty.
        if not tile or tile.is_occupied:
            # Exception: if it's the unit's own hex, it might be "occupied" by itself
            # but usually Fast Travel wants a NEW empty hex.
            return False

        return True


class PreserveDistanceFilter(FilterCondition):
    """
    Ensures that the candidate hex is at the same distance from the origin
    as a reference unit (specified by target_key) is from the origin.

    Used for "Orbit" mechanics (move without moving closer or further).
    """

    type: FilterType = FilterType.PRESERVE_DISTANCE
    target_key: str
    origin_id: Optional[str] = None  # Literal ID

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        # 1. Resolve Origin
        origin_uid = self.origin_id or state.current_actor_id
        if not origin_uid:
            return False
        origin_hex = state.entity_locations.get(BoardEntityID(str(origin_uid)))
        if not origin_hex:
            return False

        # 2. Resolve Reference Unit
        ref_uid = context.get(self.target_key)
        if not ref_uid:
            return False
        ref_hex = state.entity_locations.get(BoardEntityID(str(ref_uid)))
        if not ref_hex:
            return False

        # 3. Resolve Candidate Hex
        cand_hex = None
        if isinstance(candidate, Hex):
            cand_hex = candidate
        elif isinstance(candidate, str):
            cand_hex = state.entity_locations.get(BoardEntityID(candidate))
        if not cand_hex:
            return False

        # 4. Compare Distances
        topology = get_topology_service()
        current_dist = topology.distance(origin_hex, ref_hex, state)
        new_dist = topology.distance(origin_hex, cand_hex, state)

        return current_dist == new_dist


class OrFilter(FilterCondition):
    """Passes if ANY child filter passes (logical OR)."""

    type: FilterType = FilterType.OR_FILTER
    filters: List["FilterCondition"] = []

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        return any(f.apply(candidate, state, context) for f in self.filters)


class AndFilter(FilterCondition):
    """Passes if ALL child filters pass (logical AND)."""

    type: FilterType = FilterType.AND_FILTER
    filters: List["FilterCondition"] = []

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        return all(f.apply(candidate, state, context) for f in self.filters)

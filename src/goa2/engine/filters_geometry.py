from __future__ import annotations
from typing import Optional, Any, Literal

from goa2.domain.state import GameState
from goa2.domain.models import FilterType
from goa2.domain.hex import Hex
from goa2.domain.types import BoardEntityID, UnitID
from goa2.engine.topology import get_topology_service

# -----------------------------------------------------------------------------
# Base Filter
# -----------------------------------------------------------------------------
from goa2.engine.filters_base import FilterCondition


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

class StraightLinePathFilter(FilterCondition):
    """
    Validates that the straight-line path between origin and candidate is
    traversable — every intermediate hex must exist on the board and be clear.

    Unlike MovementPathFilter (BFS-based), this checks only the direct
    straight-line path, blocking if any intermediate hex is occupied or missing.
    """

    type: FilterType = FilterType.STRAIGHT_LINE_PATH
    origin_id: Optional[str] = None
    origin_key: Optional[str] = None
    pass_through_obstacles: bool = False

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, Hex):
            return False

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

        # Not in straight line → reject
        if not origin_hex.is_straight_line(candidate):
            return False

        # Get intermediate hexes (line_to returns origin-exclusive, destination-inclusive)
        try:
            path = origin_hex.line_to(candidate)
        except ValueError:
            return False

        actor_id = str(origin_uid) if origin_uid else None

        # Check all intermediate hexes (everything except the final destination)
        for hex_pos in path[:-1]:
            if hex_pos not in state.board.tiles:
                return False

            if self.pass_through_obstacles:
                continue

            if state.validator.is_obstacle_for_actor(state, hex_pos, actor_id, context):
                return False

        return True

class SpaceBehindEmptyFilter(FilterCondition):
    """
    For unit targeting: validates that the hex directly behind the candidate
    (from the origin's perspective) exists on the board and is not an obstacle.

    Used by Blink Strike to ensure the hero can land behind the selected enemy.
    """

    type: FilterType = FilterType.SPACE_BEHIND_EMPTY
    origin_id: Optional[str] = None
    origin_key: Optional[str] = None

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        # Candidate is a unit ID string
        if not isinstance(candidate, str):
            return False

        # Resolve origin (hero position)
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

        # Get candidate unit's hex
        candidate_hex = state.entity_locations.get(BoardEntityID(str(candidate)))
        if not candidate_hex:
            return False

        # Compute behind hex: candidate + (candidate - origin)
        diff = candidate_hex - origin_hex
        behind = candidate_hex + diff

        # Must be on the board
        if behind not in state.board.tiles:
            return False

        # Must not be an obstacle for the actor
        actor_id = str(origin_uid)
        is_obs = state.validator.is_obstacle_for_actor(state, behind, actor_id, context)
        return not is_obs

class RelativeDistanceFilter(FilterCondition):
    """
    Compares the distance(origin, candidate) against the distance(origin, reference)
    using a configurable operator.

    General-purpose replacement for PreserveDistanceFilter (operator="==").
    Also supports "farther away" (operator=">"), "closer" (operator="<"), etc.
    """

    type: FilterType = FilterType.RELATIVE_DISTANCE
    reference_key: str
    origin_id: Optional[str] = None
    operator: Literal[">", ">=", "==", "<=", "<"] = ">"
    origin_key: Optional[str] = None

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        origin_uid = self.origin_id
        if not origin_uid and self.origin_key:
            origin_uid = context.get(self.origin_key)
        if not origin_uid:
            origin_uid = state.current_actor_id
        if not origin_uid:
            return False
        origin_hex = state.entity_locations.get(BoardEntityID(str(origin_uid)))
        if not origin_hex:
            return False

        ref_uid = context.get(self.reference_key)
        if not ref_uid:
            return False
        ref_hex = state.entity_locations.get(BoardEntityID(str(ref_uid)))
        if not ref_hex:
            return False

        cand_hex = None
        if isinstance(candidate, Hex):
            cand_hex = candidate
        elif isinstance(candidate, str):
            cand_hex = state.entity_locations.get(BoardEntityID(candidate))
        if not cand_hex:
            return False

        topology = get_topology_service()
        current_dist = topology.distance(origin_hex, ref_hex, state)
        new_dist = topology.distance(origin_hex, cand_hex, state)

        ops = {
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
            "==": lambda a, b: a == b,
            "<=": lambda a, b: a <= b,
            "<": lambda a, b: a < b,
        }
        return ops[self.operator](new_dist, current_dist)

class ClearLineOfSightFilter(FilterCondition):
    """
    Validates that the straight-line path between origin and candidate has no
    blocking hexes in between.  Only intermediate hexes are checked — the
    destination itself is never a blocker.  Candidates not in a straight line
    from the origin are rejected outright.

    Configurable blockers:
    - blocked_by_units: occupied hexes block the line
    - blocked_by_terrain: terrain hexes block the line (uses validator for
      PETRIFY-awareness)

    Works with both Hex and unit-ID candidates (resolves unit → hex).
    """

    type: FilterType = FilterType.CLEAR_LINE_OF_SIGHT
    blocked_by_units: bool = True
    blocked_by_terrain: bool = True
    blocked_by_obstacles: bool = False
    origin_id: Optional[str] = None
    origin_key: Optional[str] = None

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        # Resolve candidate hex
        cand_hex: Hex | None = None
        if isinstance(candidate, Hex):
            cand_hex = candidate
        elif isinstance(candidate, str):
            cand_hex = state.entity_locations.get(BoardEntityID(candidate))
        if not cand_hex:
            return False

        # Resolve origin
        origin_uid = self.origin_id
        if not origin_uid and self.origin_key:
            origin_uid = context.get(self.origin_key)
        if not origin_uid:
            origin_uid = state.current_actor_id
        if not origin_uid:
            return False

        origin_hex = state.entity_locations.get(BoardEntityID(str(origin_uid)))
        if not origin_hex:
            return False

        if not origin_hex.is_straight_line(cand_hex):
            return False

        try:
            path = origin_hex.line_to(cand_hex)
        except ValueError:
            return False

        # Check only intermediate hexes (exclude destination)
        for hex_pos in path[:-1]:
            if hex_pos not in state.board.tiles:
                return False

            tile = state.board.tiles[hex_pos]

            if self.blocked_by_terrain:
                is_terrain = (
                    state.validator.is_terrain_hex(state, hex_pos)
                    if state.validator
                    else tile.is_terrain
                )
                if is_terrain:
                    return False

            if self.blocked_by_units and tile.occupant_id is not None:
                # Only units (heroes/minions) block — not tokens
                if state.get_unit(UnitID(str(tile.occupant_id))) is not None:
                    return False

            if self.blocked_by_obstacles and state.validator:
                actor_uid = str(origin_uid) if origin_uid else None
                if state.validator.is_obstacle_for_actor(state, hex_pos, actor_uid):
                    return False

        return True

class BetweenHexesFilter(FilterCondition):
    """
    Unit filter: passes if the candidate unit sits on the straight-line path
    between two hexes stored in context (exclusive of both endpoints).

    Used by Misa's BLUE cards to find enemies crossed during a straight-line
    move through: select the destination, then find any enemy who was between
    the origin and destination.
    """

    type: FilterType = FilterType.BETWEEN_HEXES
    from_hex_key: str
    to_hex_key: str

    def _resolve_hex(self, context: dict, key: str) -> Optional[Hex]:
        raw = context.get(key)
        if isinstance(raw, Hex):
            return raw
        if isinstance(raw, dict):
            try:
                return Hex(**raw)
            except Exception:
                return None
        return None

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        from_hex = self._resolve_hex(context, self.from_hex_key)
        to_hex = self._resolve_hex(context, self.to_hex_key)
        if from_hex is None or to_hex is None:
            return False
        if from_hex == to_hex:
            return False
        if not from_hex.is_straight_line(to_hex):
            return False

        # Resolve candidate's current hex
        cand_hex: Optional[Hex] = None
        if isinstance(candidate, Hex):
            cand_hex = candidate
        elif isinstance(candidate, str):
            cand_hex = state.entity_locations.get(BoardEntityID(candidate))
        if cand_hex is None:
            return False

        # line_to returns [next, next, ..., to_hex]; strip the endpoint so we
        # only keep strictly intermediate hexes.
        try:
            path = from_hex.line_to(to_hex)
        except ValueError:
            return False
        intermediate = path[:-1]
        return cand_hex in intermediate

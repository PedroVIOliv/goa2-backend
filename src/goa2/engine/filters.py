from __future__ import annotations
from abc import ABC
from typing import Optional, List, Any, Literal
from pydantic import BaseModel

from goa2.domain.state import GameState
from goa2.domain.models import Minion, Hero, Unit
from goa2.domain.hex import Hex
from goa2.domain.types import BoardEntityID, UnitID, HeroID

# -----------------------------------------------------------------------------
# Base Filter
# -----------------------------------------------------------------------------


class FilterCondition(BaseModel, ABC):
    """
    Base class for all selection filters.
    """

    type: str

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        """
        Returns True if the candidate passes the filter.
        Candidate can be a UnitID (str) or a Hex.
        """
        raise NotImplementedError


# -----------------------------------------------------------------------------
# Hex Filters
# -----------------------------------------------------------------------------


class OccupiedFilter(FilterCondition):
    type: str = "occupied_filter"
    is_occupied: bool = False  # False = Must be empty, True = Must be occupied
    exclude_id: Optional[str] = (
        None  # If set, ignore this entity when checking occupancy
    )

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if isinstance(candidate, Hex):
            tile = state.board.get_tile(candidate)
            if not tile:
                return False

            occ_id = tile.occupant_id
            if occ_id and self.exclude_id and occ_id == self.exclude_id:
                occ_id = None

            is_occ = occ_id is not None
            return is_occ == self.is_occupied
        return False


class TerrainFilter(FilterCondition):
    type: str = "terrain_filter"
    is_terrain: bool = True

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if isinstance(candidate, Hex):
            tile = state.board.get_tile(candidate)
            if not tile:
                return False
            return tile.is_terrain == self.is_terrain
        return False


class RangeFilter(FilterCondition):
    """
    Checks distance from an origin.
    Origin is usually the current actor, but can be customized.
    """

    type: str = "range_filter"
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

        dist = origin_hex.distance(target_hex)
        return self.min_range <= dist <= self.max_range


# -----------------------------------------------------------------------------
# Unit Filters
# -----------------------------------------------------------------------------


class TeamFilter(FilterCondition):
    type: str = "team_filter"
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
    type: str = "unit_type_filter"
    unit_type: Literal["HERO", "MINION"]

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
        return False


class AdjacencyFilter(FilterCondition):
    """
    Requires the target to be adjacent to a unit matching specific tags.
    E.g. "Adjacent to a Friendly Hero"
    """

    type: str = "adjacency_filter"
    target_tags: List[str]  # ["FRIENDLY", "HERO"]

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        cand_hex = None
        if isinstance(candidate, Hex):
            cand_hex = candidate
        elif isinstance(candidate, str):
            cand_hex = state.entity_locations.get(BoardEntityID(candidate))

        if not cand_hex:
            return False

        neighbors = cand_hex.neighbors()

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
    """

    type: str = "immunity_filter"

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        from goa2.engine import rules  # Import inside to be safe

        target = (
            state.get_entity(BoardEntityID(candidate))
            if isinstance(candidate, str)
            else None
        )
        if not target:
            return False

        # If Immune, it fails the filter (returns False)
        if isinstance(target, Unit):
            return not rules.is_immune(target, state)
        return True  # Non-units (Tokens) typically don't have "Immunity" logic yet, so pass default.


class SpawnPointFilter(FilterCondition):
    """
    Filters hexes based on whether they have a spawn point.
    """

    type: str = "spawn_point_filter"
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

    type: str = "adjacent_spawn_point_filter"
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

        neighbors = cand_hex.neighbors()
        has_adj = False
        for n in neighbors:
            tile = state.board.get_tile(n)
            if tile and tile.spawn_point:
                if self.is_empty:
                    if not tile.is_occupied:
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

    type: str = "adjacency_to_context_filter"
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
        return cand_hex.distance(target_hex) == 1


class ExcludeIdentityFilter(FilterCondition):
    """
    Excludes specific unit IDs from selection.
    Can exclude self and/or IDs found in context keys.
    """

    type: str = "exclude_identity_filter"
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
            if val == candidate:
                return False
        return True


class HasEmptyNeighborFilter(FilterCondition):
    """
    Ensures the candidate unit has at least one valid empty neighbor to move to.
    Prevents selecting 'trapped' units for movement effects.
    """

    type: str = "has_empty_neighbor_filter"

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        cand_hex = None
        if isinstance(candidate, str):
            cand_hex = state.entity_locations.get(BoardEntityID(candidate))
        elif isinstance(candidate, Hex):
            cand_hex = candidate
        if not cand_hex:
            return False
        neighbors = cand_hex.neighbors()
        for n in neighbors:
            # Check if hex exists on board
            tile = state.board.get_tile(n)
            if tile and not tile.is_obstacle:
                return True
        return False


class ForcedMovementByEnemyFilter(FilterCondition):
    """
    Checks if the candidate is protected from forced movement by enemies.
    Delegates to ValidationService.
    """

    type: str = "forced_movement_by_enemy_filter"

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

    type: str = "can_be_placed_filter"

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

    type: str = "movement_path_filter"
    range_val: int
    unit_id: Optional[str] = None
    unit_key: Optional[str] = None

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
            board=state.board, start=start_hex, end=candidate, max_steps=self.range_val
        )


class FastTravelDestinationFilter(FilterCondition):
    """
    Filters hexes to only valid Fast Travel destinations.
    Rules:
    - Unit must be in a safe zone (no enemies)
    - Destination must be in same zone or adjacent safe zone
    - Destination must be empty
    """

    type: str = "fast_travel_destination_filter"
    unit_id: Optional[str] = None

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, Hex):
            return False

        uid = self.unit_id or state.current_actor_id
        if not uid:
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

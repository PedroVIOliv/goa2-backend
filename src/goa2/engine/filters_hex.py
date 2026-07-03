from __future__ import annotations

from typing import Any, Literal

from goa2.domain.hex import Hex
from goa2.domain.models import FilterType
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID, UnitID

# -----------------------------------------------------------------------------
# Base Filter
# -----------------------------------------------------------------------------
from goa2.engine.filters_base import FilterCondition
from goa2.engine.topology import get_topology_service


class ObstacleFilter(FilterCondition):
    type: FilterType = FilterType.OCCUPIED
    is_obstacle: bool = False  # False = Must be empty, True = Must be occupied
    exclude_id: str | None = None  # If set, ignore this entity when checking occupancy

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if isinstance(candidate, Hex):
            tile = state.board.get_tile(candidate)

            # Get actor for context-aware check (Static Barrier)
            actor_id = str(state.current_actor_id) if state.current_actor_id else None

            # Use validation service for context-aware obstacle check
            is_obs = state.validator.is_obstacle_for_actor(state, candidate, actor_id, context)

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


class AdjacentToTerrainFilter(FilterCondition):
    """Filters units (or hexes) by whether they neighbour a terrain hex.

    "Terrain" means an impassable terrain tile OR the off-map board edge: the
    board edge counts as terrain, matching the canonical board convention
    (``Board.get_tile`` returns a virtual ``is_terrain=True`` tile off-map). A
    unit against the board edge is therefore treated as adjacent to terrain.

    Set ``is_adjacent=False`` for "not adjacent to terrain" targeting.
    """

    type: FilterType = FilterType.ADJACENT_TO_TERRAIN
    is_adjacent: bool = True

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if isinstance(candidate, Hex):
            cand_hex: Hex | None = candidate
        else:
            cand_hex = state.entity_locations.get(BoardEntityID(str(candidate)))
        if cand_hex is None:
            return False

        # Topology-aware neighbours (respects reality splits), consistent with
        # AdjacencyFilter / AdjacencyToContextFilter. get_connected_neighbors
        # does not filter obstacles or boundaries, so terrain hexes are still
        # included for us to detect.
        topology = get_topology_service()
        has_terrain = False
        for neighbor in topology.get_connected_neighbors(cand_hex, state):
            # Off-map hexes are the board edge, which counts as terrain.
            if not state.board.is_on_map(neighbor):
                has_terrain = True
                break
            if state.validator is not None:
                is_t = state.validator.is_terrain_hex(state, neighbor)
            else:
                tile = state.board.get_tile(neighbor)
                is_t = bool(tile and tile.is_terrain)
            if is_t:
                has_terrain = True
                break

        return has_terrain == self.is_adjacent


class AdjacentToObstaclesFilter(FilterCondition):
    """Brynn's signature check: candidate is adjacent to `min_count`+ obstacles.

    Counts the candidate's connected neighbour hexes that are obstacles per
    ``is_obstacle_for_actor`` — terrain, board edge (off-map hexes report as
    obstacles), and any hex occupied by a unit or token (including Brynn
    herself). Passes when that count reaches ``min_count`` (default 3).

    Brynn's ultimate "Over the Top" overrides the count: while she is the
    acting hero (level >= 8 with the over_the_top ultimate face-up), every
    enemy HERO counts as adjacent to 3+ obstacles regardless of the board.
    The override never applies to minions.
    """

    type: FilterType = FilterType.ADJACENT_TO_OBSTACLES
    min_count: int = 3

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if isinstance(candidate, Hex):
            cand_hex: Hex | None = candidate
        else:
            cand_hex = state.entity_locations.get(BoardEntityID(str(candidate)))
        if cand_hex is None:
            return False

        # Ultimate override: enemy heroes auto-qualify while Brynn acts.
        if not isinstance(candidate, Hex) and self._over_the_top_applies(candidate, state):
            return True

        actor_id = str(state.current_actor_id) if state.current_actor_id else None
        topology = get_topology_service()
        count = 0
        for neighbor in topology.get_connected_neighbors(cand_hex, state):
            if state.validator is not None:
                is_obs = state.validator.is_obstacle_for_actor(state, neighbor, actor_id, context)
            else:
                tile = state.board.get_tile(neighbor)
                is_obs = bool(tile and tile.is_obstacle)
            if is_obs:
                count += 1
                if count >= self.min_count:
                    return True
        return count >= self.min_count

    def _over_the_top_applies(self, candidate: Any, state: GameState) -> bool:
        actor = state.get_hero(state.current_actor_id) if state.current_actor_id else None
        if actor is None or actor.level < 8:
            return False
        ult = actor.ultimate_card
        if ult is None or ult.current_effect_id != "over_the_top":
            return False
        target = state.get_unit(UnitID(str(candidate)))
        from goa2.domain.models import is_hero_unit

        if not is_hero_unit(target):
            return False
        return target.team != actor.team


class RangeFilter(FilterCondition):
    """
    Checks distance from an origin.
    Origin is usually the current actor, but can be customized.
    """

    type: FilterType = FilterType.RANGE
    max_range: int | None = None
    min_range: int | None = 0
    origin_id: str | None = None  # Literal ID
    origin_key: str | None = None  # Key in context to find ID
    origin_hex_key: str | None = None  # Key in context holding a Hex (or dict)
    max_range_key: str | None = None  # Read upper bound from context[int]
    min_range_key: str | None = None  # Read lower bound from context[int]

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        # Resolve runtime bounds from context if keys are provided, otherwise
        # fall back to the static min_range/max_range literals. None on either
        # bound means "unbounded" on that side.
        max_r = self.max_range
        if self.max_range_key:
            raw_max = context.get(self.max_range_key)
            if isinstance(raw_max, int):
                max_r = raw_max
        min_r = self.min_range
        if self.min_range_key:
            raw_min = context.get(self.min_range_key)
            if isinstance(raw_min, int):
                min_r = raw_min

        origin_hex: Hex | None = None

        # Priority: origin_hex_key (direct hex) > origin_id > origin_key > actor
        if self.origin_hex_key:
            raw = context.get(self.origin_hex_key)
            if isinstance(raw, Hex):
                origin_hex = raw
            elif isinstance(raw, dict):
                origin_hex = Hex(**raw)

        if origin_hex is None:
            origin_uid = None
            if self.origin_id:
                origin_uid = self.origin_id
            elif self.origin_key:
                origin_uid = context.get(self.origin_key)

            if not origin_uid:
                origin_uid = state.current_actor_id

            if not origin_uid:
                return False

            origin_hex = state.get_position(str(origin_uid))
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
        if min_r is not None and dist < min_r:
            return False
        return max_r is None or dist <= max_r


class SpawnPointFilter(FilterCondition):
    """
    Filters hexes based on whether they have a spawn point.
    """

    type: FilterType = FilterType.SPAWN_POINT
    has_spawn_point: bool = False
    minion_only: bool = False  # when True, only MINION spawn points qualify

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if isinstance(candidate, Hex):
            tile = state.board.get_tile(candidate)
            if not tile:
                return False
            spawn = tile.spawn_point
            if self.minion_only and spawn is not None and not spawn.is_minion_spawn:
                spawn = None
            return (spawn is not None) == self.has_spawn_point
        return False


class AdjacentSpawnPointFilter(FilterCondition):
    """
    Filters hexes based on proximity to spawn points.
    """

    type: FilterType = FilterType.ADJACENT_SPAWN_POINT
    is_empty: bool = True
    must_not_have: bool = True  # True means "not adjacent to", False means "must be adjacent to"
    battle_zone_only: bool = False
    minion_only: bool = False  # when True, only MINION spawn points count as adjacent

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
                if self.minion_only and not tile.spawn_point.is_minion_spawn:
                    continue
                if self.battle_zone_only:
                    from goa2.scripts.dodger_effects import _has_tide_of_darkness

                    if not _has_tide_of_darkness(state):
                        active_zone_id = state.active_zone_id
                        if not active_zone_id or tile.zone_id != active_zone_id:
                            continue
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


class BattleZoneFilter(FilterCondition):
    """
    Filters hexes to the active battle zone only.
    """

    type: FilterType = FilterType.BATTLE_ZONE

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if isinstance(candidate, Hex):
            tile = state.board.get_tile(candidate)
            if not tile:
                return False
            # Tide of Darkness: all spaces count as battle zone
            from goa2.scripts.dodger_effects import _has_tide_of_darkness

            if _has_tide_of_darkness(state):
                return True
            active_zone_id = state.active_zone_id
            if not active_zone_id:
                return False
            return tile.zone_id == active_zone_id
        return False


class SpawnPointTeamFilter(FilterCondition):
    """
    Filters hexes that have a minion spawn point belonging to a friendly or enemy team.
    Relation is relative to the current actor.
    """

    type: FilterType = FilterType.SPAWN_POINT_TEAM
    relation: Literal["FRIENDLY", "ENEMY"] = "FRIENDLY"

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        from goa2.domain.models.spawn import SpawnType

        if not isinstance(candidate, Hex):
            return False

        tile = state.board.get_tile(candidate)
        if not tile:
            return False

        # Tide of Darkness: all spaces have friendly minion spawn point
        from goa2.scripts.dodger_effects import _has_tide_of_darkness

        if _has_tide_of_darkness(state):
            if self.relation == "FRIENDLY":
                return not tile.is_terrain
            return False

        if not tile.spawn_point:
            return False

        sp = tile.spawn_point
        if sp.type != SpawnType.MINION:
            return False

        actor_id = state.current_actor_id
        if not actor_id:
            return False

        actor = state.get_entity(BoardEntityID(actor_id))
        if not actor or not hasattr(actor, "team"):
            return False

        actor_team = getattr(actor, "team", None)
        if actor_team is None:
            return False

        is_same_team = sp.team == actor_team
        if self.relation == "FRIENDLY":
            return is_same_team
        return not is_same_team


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


class MovementPathFilter(FilterCondition):
    """
    Filters hexes to only those reachable via valid movement path.
    Uses a single BFS to compute all reachable hexes, then does O(1) lookups.
    """

    type: FilterType = FilterType.MOVEMENT_PATH
    range_val: int
    unit_id: str | None = None
    unit_key: str | None = None
    pass_through_obstacles: bool = False

    def _get_reachable(self, state: GameState, context: dict) -> set:
        cache = getattr(self, "_reachable_cache", None)
        if cache is not None:
            return cache

        uid = self.unit_id
        if not uid and self.unit_key:
            uid = context.get(self.unit_key)
        if not uid:
            uid = state.current_actor_id
        if not uid:
            object.__setattr__(self, "_reachable_cache", set())
            return set()

        start_hex = state.entity_locations.get(BoardEntityID(str(uid)))
        if not start_hex:
            object.__setattr__(self, "_reachable_cache", set())
            return set()

        from goa2.engine import rules

        result = rules.find_reachable_hexes(
            board=state.board,
            start=start_hex,
            max_steps=self.range_val,
            state=state,
            actor_id=str(state.current_actor_id) if state.current_actor_id else None,
            pass_through_obstacles=self.pass_through_obstacles,
        )
        object.__setattr__(self, "_reachable_cache", result)
        return result

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, Hex):
            return False

        return candidate in self._get_reachable(state, context)


class FastTravelDestinationFilter(FilterCondition):
    """
    Filters hexes to only valid Fast Travel destinations.
    Rules:
    - Unit must be in a safe zone (no enemies)
    - Destination must be in same zone or adjacent safe zone
    - Destination must be empty
    """

    type: FilterType = FilterType.FAST_TRAVEL_DESTINATION
    unit_id: str | None = None

    def apply(self, candidate: Any, state: GameState, context: dict) -> bool:
        if not isinstance(candidate, Hex):
            return False

        uid = self.unit_id or state.current_actor_id
        if not uid:
            return False

        # Check validation first
        if not state.validator.can_fast_travel(state, str(uid), context).allowed:
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
        # Exception: if it's the unit's own hex, it might be "occupied" by itself
        # but usually Fast Travel wants a NEW empty hex.
        return not (not tile or tile.is_occupied)

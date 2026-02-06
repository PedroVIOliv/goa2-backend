from typing import Set, Optional, List, Deque
from collections import deque
from goa2.domain.hex import Hex
from goa2.domain.board import Board
from goa2.domain.state import GameState
from goa2.domain.models import ActionType, Minion, TeamColor
from goa2.domain.models.unit import Unit
from goa2.engine.topology import get_topology_service


def validate_movement_path(
    board: Board,
    start: Hex,
    end: Hex,
    max_steps: int,
    ignore_obstacles: bool = False,
    active_zone_id: Optional[str] = None,
    state: Optional[GameState] = None,
    actor_id: Optional[str] = None,
) -> bool:
    """
    Validates if a unit can move from start to end within max_steps.
    Standard rules:
    - Cannot move through Obstacles (Static or Units).
    - Cannot end on Obstacle.
    - Path length <= max_steps.
    - Respects topology constraints (reality splits) if state is provided.
    - Respects STATIC_BARRIER effects if state and actor_id are provided.
    """
    if max_steps <= 0:
        return False

    if start == end:
        return False

    if not ignore_obstacles:
        # Check destination obstacle - use context-aware check if state is available
        if state and state.validator:
            if state.validator.is_obstacle_for_actor(state, end, actor_id):
                return False
        elif board.get_tile(end).is_obstacle:
            return False

    queue: Deque[tuple[Hex, int]] = deque([(start, 0)])
    visited: Set[Hex] = {start}

    # Use topology service if state is available for topology-aware pathfinding
    topology = get_topology_service() if state else None

    while queue:
        current, dist = queue.popleft()

        if current == end:
            return True

        if dist >= max_steps:
            continue

        # Get neighbors - topology-aware if state provided, otherwise geometric
        if topology and state:
            neighbors = topology.get_traversable_neighbors(
                current, state, end, actor_id
            )
        else:
            neighbors = board.get_neighbors(current)

        for neighbor in neighbors:
            if neighbor not in visited:
                # Skip obstacles (unless using topology which already filters)
                if not (topology and state):
                    # Use context-aware check if state is available, otherwise base check
                    if state and state.validator:
                        is_obs = state.validator.is_obstacle_for_actor(
                            state, neighbor, actor_id
                        )
                    else:
                        is_obs = board.get_tile(neighbor).is_obstacle

                    if is_obs and neighbor != end:
                        continue

                visited.add(neighbor)
                queue.append((neighbor, dist + 1))

    return False


def is_immune(target: Unit, state: GameState) -> bool:
    """
    Checks if a target unit has Immunity.
    Rule 3.2: "Heavy Immunity: Immune to all Actions... until no more friendly minions are present."
    """
    if isinstance(target, Minion) and target.is_heavy:
        # "until no more friendly minions are present" (Usually implies in the battle)
        zone_id = state.active_zone_id
        if not zone_id:
            return False

        zone = state.board.zones.get(zone_id)
        if not zone:
            return False

        if target.team is None:
            return False

        team = state.teams.get(target.team)
        if not team:
            return False

        # Optimization: We only care about Minions.
        # Iterate team.minions instead of entity_locations to filter by Type first.
        for m in team.minions:
            if m.id == target.id:
                continue

            # Use unified lookup
            if m.id in state.entity_locations:
                loc = state.entity_locations[m.id]
                if loc in zone.hexes:
                    return True

    return False


def validate_target(
    source: Unit,
    target: Unit,
    action_type: ActionType,
    state: GameState,
    range_val: int,
    ignore_los: bool = True,  # Default per rules (4.1)
    requires_straight_line: bool = False,
) -> bool:
    """
    Central validation for targeting.
    Checks:
    1. Distance (Range)
    2. Line of Sight (if needed)
    3. Immunity (Heavies, etc.)
    """

    if is_immune(target, state):
        return False

    s_loc = state.entity_locations.get(source.id)
    t_loc = state.entity_locations.get(target.id)

    if not s_loc or not t_loc:
        return False

    if requires_straight_line:
        if not s_loc.is_straight_line(t_loc):
            return False

    # Use topology-aware distance (respects reality splits)
    topology = get_topology_service()
    dist = topology.distance(s_loc, t_loc, state)
    if dist > range_val:
        return False

    # Rule 4.1: "No 'Line of Sight' obstructions" is standard for Range/Radius.
    # However, some specific rules might require it.
    # For now, default ignores it.

    return True


def validate_attack_target(
    attacker_pos: Hex,  # Legacy
    target_pos: Hex,  # Legacy
    range_val: int,
    requires_line_of_sight: bool = True,
    requires_straight_line: bool = False,
    state: Optional[GameState] = None,
    attacker: Optional[Unit] = None,
    target: Optional[Unit] = None,
) -> bool:
    """
    Validates if an attack is legal.
    Wrapper around validate_target if full context is provided.
    Else falls back to geometry check.
    """
    if state and attacker and target:
        return validate_target(
            source=attacker,
            target=target,
            action_type=ActionType.ATTACK,
            state=state,
            range_val=range_val,
            ignore_los=not requires_line_of_sight,
            requires_straight_line=requires_straight_line,
        )

    # Legacy Fallback (Geometry Only - no topology without state)
    # Note: This branch cannot use topology since state is not available
    if requires_straight_line:
        if not attacker_pos.is_straight_line(target_pos):
            return False

    # Use topology if state is available, otherwise pure geometry
    if state:
        topology = get_topology_service()
        dist = topology.distance(attacker_pos, target_pos, state)
    else:
        dist = attacker_pos.distance(target_pos)
    if dist > range_val:
        return False

    return True


def get_safe_zones_for_fast_travel(
    state: GameState, team: TeamColor, current_zone_id: str
) -> List[str]:
    """
    Identifies zones eligible for Fast Travel.
    Rule 6.1 (Fast Travel):
    - Start Zone must be Empty of Enemies.
    - Dest Zone must be Empty of Enemies.
    - Dest Zone must match Start Zone OR be Adjacent to Start Zone.
    """
    safe_zones = []

    # If Start Zone has enemies, Fast Travel is impossible.
    start_zone = state.board.zones.get(current_zone_id)
    if not start_zone:
        return []

    start_has_enemies = False
    for entity_id, loc in state.entity_locations.items():
        if loc in start_zone.hexes:
            # We use get_entity because it might be a Unit or a Token
            entity = state.get_entity(entity_id)
            if entity and hasattr(entity, "team") and entity.team != team:
                start_has_enemies = True
                break

    if start_has_enemies:
        return []

    candidates = [current_zone_id] + start_zone.neighbors

    for z_id in candidates:
        zone = state.board.zones.get(z_id)
        if not zone:
            continue

        has_enemies = False
        for entity_id, loc in state.entity_locations.items():
            if loc in zone.hexes:
                entity = state.get_entity(entity_id)
                # Note: Tokens are obstacles, not enemies. Rules specify "Empty of Enemies".
                if entity and hasattr(entity, "team") and entity.team != team:
                    has_enemies = True
                    break

        if not has_enemies:
            safe_zones.append(z_id)

    return safe_zones

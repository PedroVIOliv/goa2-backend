from typing import List, Optional, Tuple
from collections import deque
from goa2.domain.state import GameState
from goa2.domain.models import TeamColor
from goa2.domain.hex import Hex
from goa2.engine.topology import get_connected_neighbors


def check_lane_push_trigger(
    state: GameState, active_zone_id: str
) -> Optional[TeamColor]:
    """
    Checks if a Lane Push should occur in the active zone.
    Condition: Minion Count for a Team in BattleZone == 0.
    Returns the LOSING team (the one with 0 minions), or None.
    """
    if not active_zone_id:
        return None

    zone = state.board.zones.get(active_zone_id)
    if not zone:
        return None

    red_minions = 0
    blue_minions = 0

    for team_color, team in state.teams.items():
        count = 0
        for minion in team.minions:
            loc = state.unit_locations.get(minion.id)
            if loc and loc in zone.hexes:
                count += 1

        if team_color == TeamColor.RED:
            red_minions = count
        elif team_color == TeamColor.BLUE:
            blue_minions = count

    # If Red has 0 and Blue > 0 -> Red Loses Zone (Blue Pushes)
    # If Blue has 0 and Red > 0 -> Blue Loses Zone (Red Pushes)

    if red_minions == 0 and blue_minions > 0:
        return TeamColor.RED  # Red lost control
    elif blue_minions == 0 and red_minions > 0:
        return TeamColor.BLUE  # Blue lost control

    return None


def get_push_target_zone_id(
    state: GameState, losing_team: TeamColor
) -> Tuple[Optional[str], bool]:
    """
    Calculates the next zone ID based on the losing team.
    Returns (next_zone_id, is_game_over).
    """
    current_id = state.active_zone_id
    if not current_id:
        return None, False

    lane = state.board.lane
    if not lane or current_id not in lane:
        return None, False

    idx = lane.index(current_id)

    # Lane is ordered RedBase -> BlueBase
    # Red Loses -> Index - 1 (Towards Red Base)
    # Blue Loses -> Index + 1 (Towards Blue Base)

    if losing_team == TeamColor.RED:
        new_idx = idx - 1
        if new_idx <= 0:
            return None, True  # Reached Red Base — game over
    else:  # BLUE
        new_idx = idx + 1
        if new_idx >= len(lane) - 1:
            return None, True  # Reached Blue Base — game over

    return lane[new_idx], False


def count_enemies(state: GameState, zone_id: str, team: TeamColor) -> int:
    """
    Counts HOSTILE units (Minions + Heroes) in a zone.
    """
    zone = state.board.zones.get(zone_id)
    if not zone:
        return 0

    count = 0
    for team_obj in state.teams.values():
        if team_obj.color != team:  # Hostile Team
            for minion in team_obj.minions:
                loc = state.unit_locations.get(minion.id)
                if loc and loc in zone.hexes:
                    count += 1

    for t_color, t_obj in state.teams.items():
        if t_color != team:
            for hero in t_obj.heroes:
                loc = state.unit_locations.get(hero.id)
                if loc and loc in zone.hexes:
                    count += 1

    return count


def find_nearest_empty_hexes(
    state: GameState, start_hex: Hex, zone_id: str
) -> List[Hex]:
    """
    Finds the nearest empty hex(es) to start_hex within the specified zone.
    Used for displacement/collision resolution.
    Returns a list of equally-distant hexes.
    """
    zone = state.board.zones.get(zone_id)
    if not zone:
        return []

    queue = deque([(start_hex, 0)])
    visited = {start_hex}

    candidates = []
    found_distance = None

    while queue:
        current, dist = queue.popleft()

        # Optimization: If we found candidates at distance X,
        # stop processing anything at distance X+1
        if found_distance is not None and dist > found_distance:
            break

        # Check Validity (Only if not start hex)
        if dist > 0:
            if current in zone.hexes:
                tile = state.board.get_tile(current)
                # Check for Obstacle/Occupancy
                # Note: Token is an obstacle. Unit is an occupant.
                # Valid = Not Obstacle AND Not Occupied.
                if tile and not tile.is_occupied:
                    candidates.append(current)
                    found_distance = dist

        # Expand (only if we haven't found a closer layer yet)
        if found_distance is None:
            # Use topology-aware neighbors to respect board splits
            for neighbor in get_connected_neighbors(current, state):
                if neighbor not in visited:
                    # SAFETY: Only expand to hexes that exist on the board
                    if state.board.is_on_map(neighbor):
                        visited.add(neighbor)
                        queue.append((neighbor, dist + 1))

    return candidates

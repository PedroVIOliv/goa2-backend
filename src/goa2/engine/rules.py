from typing import Dict, Set, Optional, List, Deque
from collections import deque
from goa2.domain.hex import Hex
from goa2.domain.board import Board
from goa2.domain.types import UnitID

def validate_movement_path(
    board: Board, 
    unit_locations: Dict[UnitID, Hex], 
    start: Hex, 
    end: Hex, 
    max_steps: int, 
    ignore_obstacles: bool = False
) -> bool:
    """
    Validates if a unit can move from start to end within max_steps.
    Standard rules:
    - Cannot move through Obstacles (Static or Units).
    - Cannot end on Obstacle.
    - Path length <= max_steps.
    """
    # 0. Trivial check
    if start == end:
        return True # Moving 0 steps is valid? usually.
        
    # 1. Check if destination is strictly valid (on board?) 
    # For now, if board has zones, check connectivity? 
    # MVP: Just check if destination is blocked.
    
    # Destination cannot be occupied (in standard rules, unless displacing)
    if not ignore_obstacles:
        if board.is_obstacle(end):
            return False
        if end in unit_locations.values():
            return False

    # 2. Pathfinding (BFS)
    # Blocked set includes static obstacles and all units
    blocked: Set[Hex] = set()
    if not ignore_obstacles:
        blocked.update(board.obstacles)
        blocked.update(unit_locations.values())
        
        # We start at 'start', which is occupied by self. 
        # But we leave it, so don't treat 'start' as blocked for neighbors? 
        # BFS won't visit start again anyway if we track visited.
    
    queue: Deque[tuple[Hex, int]] = deque([(start, 0)])
    visited: Set[Hex] = {start}
    
    while queue:
        current, dist = queue.popleft()
        
        if current == end:
            return True
            
        if dist >= max_steps:
            continue
            
        for neighbor in current.neighbors():
            if neighbor not in visited:
                # If neighbor is blocked, we cannot Enter it.
                # So we can't traverse it.
                if neighbor in blocked and neighbor != end:
                    # Exception: If 'end' was in blocked, we caught it in step 1.
                    # But if we were allowing 'attack' or 'push', this might vary.
                    # For pure MOVE, checked in step 1.
                    continue
                
                visited.add(neighbor)
                queue.append((neighbor, dist + 1))
                
    return False

def validate_attack_target(
    unit_locations: Dict[UnitID, Hex],
    attacker_pos: Hex,
    target_pos: Hex,
    range_val: int,
    requires_line_of_sight: bool = True, # Walls block
    requires_straight_line: bool = False
) -> bool:
    """
    Validates if an attack is legal.
    """
    # 1. Geometry Check
    if requires_straight_line:
        if not attacker_pos.is_straight_line(target_pos):
            return False
            
    dist = attacker_pos.distance(target_pos)
    if dist > range_val:
        return False
        
    # 2. Line of Sight
    # Rule 4.1 Stats: "No 'Line of Sight' obstructions (target through obstacles)."
    # Therefore, we do NOT check for walls or units blocking the path.
    # Distance check is sufficient.
    
    return True

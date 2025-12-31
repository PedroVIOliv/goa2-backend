from typing import Dict, Set, Optional, List, Deque
from collections import deque
from goa2.domain.hex import Hex
from goa2.domain.board import Board
from goa2.domain.types import UnitID
from goa2.domain.state import GameState
from goa2.domain.models import ActionType, Minion, TeamColor
from goa2.domain.models.unit import Unit

def validate_movement_path(
    board: Board, 
    unit_locations: Dict[UnitID, Hex], 
    start: Hex, 
    end: Hex, 
    max_steps: int, 
    ignore_obstacles: bool = False,
    active_zone_id: Optional[str] = None
) -> bool:
    """
    Validates if a unit can move from start to end within max_steps.
    Standard rules:
    - Cannot move through Obstacles (Static or Units).
    - Cannot end on Obstacle.
    - Path length <= max_steps.
    """
    if start == end:
        return False
        
    if not ignore_obstacles:
        if board.get_tile(end).is_obstacle:
            return False
            
        elif end in unit_locations.values():
            return False

    queue: Deque[tuple[Hex, int]] = deque([(start, 0)])
    visited: Set[Hex] = {start}
    
    while queue:
        current, dist = queue.popleft()
        
        if current == end:
            return True
            
        if dist >= max_steps:
            continue
            
        for neighbor in board.get_neighbors(current):
            if neighbor not in visited:
                # Note: Virtual tiles are handled in the loop via get_tile(neighbor).is_obstacle
                if board.get_tile(neighbor).is_obstacle and neighbor != end:
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
            
        team = state.teams.get(target.team)
        if not team:
            return False
            
        for m in team.minions:
            if m.id == target.id:
                continue
                
            loc = state.unit_locations.get(m.id)
            if loc and loc in zone.hexes:
                return True
                
    return False

def validate_target(
    source: Unit,
    target: Unit,
    action_type: ActionType,
    state: GameState,
    range_val: int,
    ignore_los: bool = True, # Default per rules (4.1)
    requires_straight_line: bool = False
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
        
    s_loc = state.unit_locations.get(source.id)
    t_loc = state.unit_locations.get(target.id)
    
    if not s_loc or not t_loc:
        return False
            
    if requires_straight_line:
        if not s_loc.is_straight_line(t_loc):
            return False
            
    dist = s_loc.distance(t_loc)
    if dist > range_val:
        return False
        
    # Rule 4.1: "No 'Line of Sight' obstructions" is standard for Range/Radius.
    # However, some specific rules might require it. 
    # For now, default ignores it.
    
    return True

def validate_attack_target(
    unit_locations: Dict[UnitID, Hex], # Legacy arg, kept for compatibility if needed, but we prefer GameState
    attacker_pos: Hex, # Legacy
    target_pos: Hex,   # Legacy
    range_val: int,
    requires_line_of_sight: bool = True,
    requires_straight_line: bool = False,
    
    state: Optional[GameState] = None,
    attacker: Optional[Unit] = None,
    target: Optional[Unit] = None
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
            requires_straight_line=requires_straight_line
        )

    # Legacy Fallback (Geometry Only)
    if requires_straight_line:
        if not attacker_pos.is_straight_line(target_pos):
            return False
            
    dist = attacker_pos.distance(target_pos)
    if dist > range_val:
        return False
        
    return True

def get_safe_zones_for_fast_travel(state: GameState, team: TeamColor, current_zone_id: str) -> List[str]:
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
    for unit_id, loc in state.unit_locations.items():
        if loc in start_zone.hexes:
            unit = state.get_unit(unit_id)
            if unit and hasattr(unit, 'team') and unit.team != team:
                start_has_enemies = True
                break
    
    if start_has_enemies:
        return []

    candidates = [current_zone_id] + start_zone.neighbors
    
    for z_id in candidates:
        zone = state.board.zones.get(z_id)
        if not zone: continue
        
        has_enemies = False
        for unit_id, loc in state.unit_locations.items():
            if loc in zone.hexes:
                unit = state.get_unit(unit_id)
                # Note: Tokens are obstacles, not enemies. Rules specify "Empty of Enemies".
                if unit and hasattr(unit, 'team') and unit.team != team:
                    has_enemies = True
                    break
        
        if not has_enemies:
            safe_zones.append(z_id)
            
    return safe_zones
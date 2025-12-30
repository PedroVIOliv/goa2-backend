from typing import List, Optional, Tuple
from goa2.domain.state import GameState
from goa2.domain.models import TeamColor
from goa2.domain.types import UnitID

def check_lane_push_trigger(state: GameState, active_zone_id: str) -> Optional[TeamColor]:
    """
    Checks if a Lane Push should occur in the active zone.
    Condition: Minion Count for a Team in BattleZone == 0.
    Returns the LOSING team (the one with 0 minions), or None.
    """
    # Defensive check
    if not active_zone_id:
        return None
        
    zone = state.board.zones.get(active_zone_id)
    if not zone:
        return None
    
    # Count Minions in Zone
    red_minions = 0
    blue_minions = 0
    
    # Iterate Teams
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
                
    # Logic:
    # If Red has 0 and Blue > 0 -> Red Loses Zone (Blue Pushes)
    # If Blue has 0 and Red > 0 -> Blue Loses Zone (Red Pushes)
    
    if red_minions == 0 and blue_minions > 0:
        return TeamColor.RED # Red lost control
    elif blue_minions == 0 and red_minions > 0:
        return TeamColor.BLUE # Blue lost control
        
    return None

def get_push_target_zone_id(state: GameState, losing_team: TeamColor) -> Tuple[Optional[str], bool]:
    """
    Calculates the next zone ID based on the losing team.
    Returns (next_zone_id, is_game_over).
    """
    current_id = state.active_zone_id
    if not current_id: return None, False
    
    lane = state.board.lane
    if not lane or current_id not in lane:
        return None, False
        
    idx = lane.index(current_id)
    
    # Direction Logic:
    # Lane is ordered RedBase -> BlueBase
    # Red Loses -> Index - 1 (Towards Red Base)
    # Blue Loses -> Index + 1 (Towards Blue Base)
    
    if losing_team == TeamColor.RED:
        new_idx = idx - 1
        if new_idx < 0:
            return None, True # Red Base Lost
    else: # BLUE
        new_idx = idx + 1
        if new_idx >= len(lane):
            return None, True # Blue Base Lost
            
    return lane[new_idx], False

def count_enemies(state: GameState, zone_id: str, team: TeamColor) -> int:
    """
    Counts HOSTILE units (Minions + Heroes) in a zone.
    """
    zone = state.board.zones.get(zone_id)
    if not zone:
        return 0
        
    count = 0
    # Check Minions (Iterate Teams)
    for team_obj in state.teams.values():
        if team_obj.color != team: # Hostile Team
            for minion in team_obj.minions:
                loc = state.unit_locations.get(minion.id)
                if loc and loc in zone.hexes:
                     count += 1
                
    # Check Heroes (Iterate Teams -> Heroes)
    for t_color, t_obj in state.teams.items():
        if t_color != team:
            for hero in t_obj.heroes:
                loc = state.unit_locations.get(hero.id)
                if loc and loc in zone.hexes:
                    count += 1
                    
    return count

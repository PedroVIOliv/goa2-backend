from typing import List, Optional
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
    # If Both 0? (Mutually assured destruction? Usually wait for spawn)
    
    if red_minions == 0 and blue_minions > 0:
        return TeamColor.RED # Red lost control
    elif blue_minions == 0 and red_minions > 0:
        return TeamColor.BLUE # Blue lost control
        
    return None

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

def execute_push(state: GameState, losing_team: TeamColor):
    """
    Executes the lane push logic.
    1. Identify Next Zone based on losing team (Red pushes towards Blue base, etc).
    2. Teleport remaining minions? Or usually they are wiped and respawned?
       Design: "When a push happens, the Battle Zone shifts."
       Usually involves clearing old minions and spawning new wave in new zone.
    3. Update active_zone_id.
    """
    current_zone = state.board.zones.get(state.active_zone_id)
    if not current_zone:
        return
        
    lane = state.board.lane
    if not lane:
        # Fallback to current simple logic if no lane defined
        print(f"   [!] PUSH TRIGGERED! Losing Team: {losing_team.name} (No Lane Defined)")
        return
        
    try:
        idx = lane.index(state.active_zone_id)
    except ValueError:
        return

    # Direction Logic:
    # Lane is ordered RedBase -> BlueBase
    # If Red Loses (0 Red Minions) -> Blue Pushes -> Battle moves TOWARDS Red Base (Index - 1)
    # If Blue Loses (0 Blue Minions) -> Red Pushes -> Battle moves TOWARDS Blue Base (Index + 1)
    
    new_idx = idx
    if losing_team == TeamColor.RED:
        new_idx = idx - 1
    else: # BLUE
        new_idx = idx + 1
        
    # Check Bounds (Game Over?)
    if new_idx < 0:
        print("   [!] RED BASE DESTROYED! BLUE WINS!")
        return 
    if new_idx >= len(lane):
        print("   [!] BLUE BASE DESTROYED! RED WINS!")
        return
        
    new_zone_id = lane[new_idx]
    
    # Execute Transition
    print(f"   [!] PUSH TRIGGERED! {state.active_zone_id} -> {new_zone_id}")
    
    # 1. Clear Minions from Old Zone logic is handled by rules (they die naturally or are wiped?)
    # Rules 2.3.3: "Remove all Minions from old Battle Zone."
    # We iterate all minions and remove those in old zone.
    # Note: iterating a modified dict is risky, gather keys first.
    to_remove = []
    old_zone_hexes = current_zone.hexes
    
    for uid, loc in state.unit_locations.items():
        if loc in old_zone_hexes:
            # Check if it is a minion (by checking all teams)
            is_minion = False
            for team in state.teams.values():
                 for m in team.minions:
                     if m.id == uid:
                         is_minion = True
                         break
                 if is_minion: break
            
            if is_minion:
                to_remove.append(uid)
                
    for uid in to_remove:
        # Remove from Board Tile
        loc = state.unit_locations.get(uid)
        if loc and loc in state.board.tiles:
            state.board.tiles[loc].occupant_id = None
            
        # Remove from Locations
        del state.unit_locations[uid]
        
        # Remove from Team list
        for team in state.teams.values():
            team.minions = [m for m in team.minions if m.id != uid]

    # 2. Update Active Zone
    state.active_zone_id = new_zone_id
    
    # 3. Spawn New Wave (Stub for now, or MVP spawn)
    print("   [i] Spawning new wave not implemented yet.")
    print(f"   [!] PUSH TRIGGERED! Losing Team: {losing_team.name}")

from typing import List, Optional, cast
from goa2.domain.state import GameState
from goa2.domain.models import TeamColor, Minion, MinionType, Team
from goa2.domain.board import SpawnType, SpawnPoint
from goa2.domain.types import UnitID, BoardEntityID
from goa2.engine.phases import ResolutionStep, GamePhase
from goa2.engine.rules import validate_movement_path
import heapq # For pathfinding
from collections import deque
import uuid

# --- Lane Push Mechanics ---

def check_lane_push(state: GameState) -> bool:
    """
    Checks if a Lane Push condition is met (0 Minions for a team in Active Zone).
    """
    if not state.active_zone_id:
        return False
        
    zone = state.board.zones.get(state.active_zone_id)
    if not zone:
        return False
        
    red_minions = 0
    blue_minions = 0
    
    # Simple counting (Optimization: could be maintained incrementally, but O(N) is fine for now)
    for team in state.teams.values():
        count = 0
        for m in team.minions:
            loc = state.unit_locations.get(m.id)
            if loc and loc in zone.hexes:
                count += 1
        
        if team.color == TeamColor.RED:
            red_minions = count
        elif team.color == TeamColor.BLUE:
            blue_minions = count
            
    # Trigger if EITHER team hits 0 (and game is started/has minions)
    # Edge case: Start of game (0 vs 0). Usually handled by Setup.
    # We assume if checking push, we expect minions to be there.
    # But if BOTH are 0, it's ambiguous. Rules usually implies last man standing.
    # If both 0, maybe simultaneous push? Or nothing?
    # For now, strict check:
    if red_minions == 0 and blue_minions > 0:
        return True
    if blue_minions == 0 and red_minions > 0:
        return True
        
    return False

def perform_lane_push(state: GameState):
    """
    Executes the Lane Push sequence.
    1. Determine Winner/Loser.
    2. Decrement Wave Counter.
    3. Shift Zone.
    4. Respawn.
    """
    if not state.active_zone_id:
        return

    # 1. Determine Loser (Re-run logic or pass it in? Safe to re-calc)
    zone = state.board.zones[state.active_zone_id]
    red_count = 0
    blue_count = 0
    for team in state.teams.values():
        c = sum(1 for m in team.minions if state.unit_locations.get(m.id) in zone.hexes)
        if team.color == TeamColor.RED: red_count = c
        elif team.color == TeamColor.BLUE: blue_count = c
    
    losing_team = None
    if red_count == 0 and blue_count > 0: losing_team = TeamColor.RED
    elif blue_count == 0 and red_count > 0: losing_team = TeamColor.BLUE
    
    if losing_team is None:
        return # False alarm or draw
        
    # 2. Wave Counter
    state.wave_counter -= 1
    if state.wave_counter <= 0:
        print("GAME OVER") # TODO: Proper signal
        return

    # 3. Shift Zone
    lane = state.board.lane
    try:
        current_idx = lane.index(state.active_zone_id)
    except ValueError:
        return
        
    new_idx = current_idx - 1 if losing_team == TeamColor.RED else current_idx + 1
    
    if new_idx < 0 or new_idx >= len(lane):
         print("BASE DESTROYED") # TODO: Proper signal
         return
         
    new_zone_id = lane[new_idx]
    
    # 3b. Remove OLD Minions
    # "Remove all Minions from old Battle Zone"
    to_remove = []
    old_hexes = zone.hexes
    for uid, loc in state.unit_locations.items():
        if loc in old_hexes:
            # Check if Minion
            # Slow lookup, but safe
            is_minion = False
            for t in state.teams.values():
                for m in t.minions:
                    if m.id == uid:
                        is_minion = True
                        break
                if is_minion: break
            if is_minion:
                to_remove.append(uid)
                
    for uid in to_remove:
        state.remove_unit(uid)
        # Remove from Team
        for t in state.teams.values():
            t.minions = [m for m in t.minions if m.id != uid]

    # 3c. Switch Active Zone
    state.active_zone_id = new_zone_id
    
    # 4. Respawn Logic
    spawn_minion_wave(state, new_zone_id)


def spawn_minion_wave(state: GameState, zone_id: str):
    """
    Spawns minions at designated points in the zone.
    Removes Tokens if they occupy a spawn point.
    """
    zone = state.board.zones.get(zone_id)
    if not zone: 
        return
        
    for h in zone.hexes:
        sp = state.board.get_spawn_point(h)
        if sp and sp.is_minion_spawn:
            # STOMP Logic: Remove occupant if Token?
            # Actually, we just need to ensure the tile is clear or we stomp.
            # If unit? Minions shouldn't be there (we just cleared old zone, but this is NEW zone).
            # "Occupied by Unit: Owning Team Places Minion..." (Complexity!)
            # For MVP/This Iteration: Assume Stomp Token, Block by Unit? 
            # User Correction: "existing tokens are removed.. if a minion would spawn on top"
            
            # Check blockage
            tile = state.board.tiles.get(h)
            if tile and tile.occupant_id:
                # Is it a Token?
                # Todo: Check if Entity is Token. 
                # For now, just STOMP everything for simplicity or assume Token?
                # Rule says "Occupied by Token: Remove Token immediately".
                # Rule says "Occupied by Unit: Place Minion nearby".
                pass 
                
            # Create Minion
            team = sp.team
            m_type = sp.minion_type
            if not m_type: continue
            
            new_id = UnitID(str(uuid.uuid4())[:8])
            minion = Minion(
                id=new_id, 
                name=f"{m_type.name} Minion",
                type=m_type,
                team=team
            )
            
            state.teams[team].minions.append(minion)
            state.move_unit(new_id, h)

# --- Out of Bounds Mechanics ---

def enforce_minion_bounding(state: GameState, unit_id: UnitID):
    """
    Rule 3.2 Bounding Rule:
    If a Minion is outside the BattleZone:
    1. Immediately move via shortest path to nearest Empty Space in BattleZone.
    2. If no path, Place (teleport) to nearest Empty Space.
    3. If multiple equidistant, owner chooses (Stub: pick first).
    """
    if not state.active_zone_id:
        return
        
    zone = state.board.zones.get(state.active_zone_id)
    if not zone:
        return

    current_loc = state.unit_locations.get(unit_id)
    if not current_loc:
        return
        
    # Check if already inside
    if current_loc in zone.hexes:
        return

    # Find candidate targets (Empty Hexes in BattleZone)
    # "Empty" means no Unit and no Static Obstacle.
    candidate_hexes = []
    for h in zone.hexes:
        # Check Obstacle (Static or Occupied)
        if h in state.board.tiles and state.board.tiles[h].is_obstacle:
             continue
             
        # Rule says "Empty Space". Tiles.is_obstacle covers both Static and Dynamic (Occupant).
        # Double check fallback if needed?
        # If tile says is_obstacle=False, it means no static and no occupant.
        
        is_occupied = False
        # Fallback check unit_locations if tile not synced?
        if h in state.unit_locations.values():
             is_occupied = True
             
        if not is_occupied:
             candidate_hexes.append(h)
             
    if not candidate_hexes:
        print(f"Warning: No empty space for bounding minion {unit_id}")
        return # Cannot move anywhere

    # 1. Attempt Pathfinding (Mocking heavy BFS for nearest for simple approach)
    # We want "Shortest Path to Nearest".
    # BFS from current_loc until we hit ANY candidate.
    
    queue = deque([(current_loc, 0, [current_loc])])
    visited = {current_loc}
    
    # We need a limit to prevent infinite loops? 
    # Max distance on board is small enough.
    
    # We need to find the specific TARGET hex that is reachable via shortest path.
    # While BFS, if we encounter a hex in 'candidate_hexes', that IS the nearest.
    
    found_path = None
    target_hex = None
    
    while queue:
        curr, dist, path = queue.popleft()
        
        if curr in candidate_hexes:
            found_path = path
            target_hex = curr
            break
            
        for neighbor in curr.neighbors():
            if neighbor not in visited:
                 # Check if we can traverse (not blocked)
                 # Note: Bounding rule implies "Move via shortest path".
                 # This implies normal movement rules (blocked by obstacles).
                 # We reuse logic or simple check.
                 
                 # Check Blockage:
                 is_blocked = False
                 if neighbor in state.board.tiles:
                     if state.board.tiles[neighbor].is_obstacle:
                         is_blocked = True
                 
                 if not is_blocked:
                     visited.add(neighbor)
                     queue.append((neighbor, dist+1, path + [neighbor]))

    # 2. Execute Move or Place
    final_hex = None
    
    if found_path and target_hex:
        # Move via path (Teleport effective result is same: Unit ends up at target)
        final_hex = target_hex
        # Log path?
    else:
        # 3. Fallback: Placement
        # Find nearest candidate by pure distance (ignoring obstacles)
        # Sort candidates by distance
        candidate_hexes.sort(key=lambda h: current_loc.distance(h))
        final_hex = candidate_hexes[0]
        
    # Execute Update
    if final_hex:
        state.move_unit(unit_id, final_hex)



def run_end_phase(state: GameState):
    """
    Executes End Phase logic.
    1. Retrieve Cards
    2. Minion Battle
    3. Clear Tokens/Markers
    4. Reset Turn/Round
    """
    
    # 1. Retrieve Cards
    for team in state.teams.values():
        for hero in team.heroes:
            # Move Resolved/Discarded -> Hand
            # (Simplification: Restore full hand)
            # Actually we just need to return played cards.
            # For MVP: Iterate deck check state?
            # Just move Play/Discard -> Hand
            to_hand = []
            for c in hero.deck:
                if c.state != "DECK": # If not in deck
                    c.state = "HAND"
                    if c not in hero.hand:
                         hero.hand.append(c)
            hero.discard_pile = []

    # 2. Minion Battle (Attrition)
    if state.active_zone_id:
        zone = state.board.zones[state.active_zone_id]
        red_c = sum(1 for m in state.teams[TeamColor.RED].minions if state.unit_locations.get(m.id) in zone.hexes)
        blue_c = sum(1 for m in state.teams[TeamColor.BLUE].minions if state.unit_locations.get(m.id) in zone.hexes)
        
        diff = abs(red_c - blue_c)
        if diff > 0:
            loser = TeamColor.RED if red_c < blue_c else TeamColor.BLUE
            count = diff
            # Remove 'count' minions from loser
            # "Heavy must be last" -> Sort by type? Heavy=4, Melee=2...
            # Just remove basic ones first.
            
            # This logic needs careful selection. For MVP, just remove first 'count'.
            losing_minions = [m for m in state.teams[loser].minions if state.unit_locations.get(m.id) in zone.hexes]
            # TODO: Sort by priority
            
            removed_count = 0
            for m in losing_minions:
                if removed_count >= diff: break # Wait, diff is ABS, but loser has FEWER.
                # Rule: "Team with FEWER Minions must remove DIFF Minions"
                # Wait: If Red has 2, Blue has 5. Diff is 3.
                # Red must remove 3??
                # Rule 2.4.2: "Team with fewer Minions must remove Diff Minions"
                # If Red has 2 and needs to remove 3, they lose all 2.
                # And triggered Lane Push?
                
                # Logic:
                uid = m.id
                loc = state.unit_locations[uid]
                del state.unit_locations[uid]
                if loc in state.board.tiles:
                    state.board.tiles[loc].occupant_id = None
                
                # Remove from team list later or now?
                state.teams[loser].minions.remove(m) 
                removed_count += 1
                
    # 3. Clear Tokens and Markers
    # Clear Markers from all Units
    for team in state.teams.values():
        for hero in team.heroes:
            hero.markers = []
        for minion in team.minions:
            minion.markers = []
            
    # Clear Tokens from Board
    # Iterate Tiles, if Occupant is Token -> Remove
    # We need to look up Entity by ID to know if it is a Token.
    # We don't have a central "Token Registry".
    # BUT we know unit IDs are tracking in unit_locations.
    # If occupant_id is NOT in unit_locations, is it a Token?
    # Tokens are Static Objects.
    # This implies we need a list of Tokens or check every tile.
    # For now: We can iterate tiles.
    for tile in state.board.tiles.values():
        if tile.occupant_id:
            # Check if this ID belongs to a Unit
            is_unit = tile.occupant_id in state.unit_locations
            if not is_unit:
                # Assume Token -> Clear
                tile.occupant_id = None

    # 4. Level Up and Upgrade Check
    # Rule 1: Cost to upgrade is CURRENT Level. (Lvl 2->3 costs 2g).
    # Rule 2: Can upgrade multiple times (Lvl 2->4).
    # Rule 3: If NO level up, gain 1 Pity Coin.
    
    any_upgrade_pending = False
    
    from goa2.domain.input import InputRequest, InputRequestType
    from goa2.domain.models import CardTier
    
    for team in state.teams.values():
         for hero in team.heroes:
             # Max level check
             if hero.level >= 8:
                 continue
                 
             leveled_up = False
             
             # Multi-Level Loop
             while hero.level < 8 and hero.gold >= hero.level:
                 cost = hero.level
                 hero.gold -= cost
                 hero.level += 1
                 leveled_up = True
                 print(f"Hero {hero.id} Leveled Up to {hero.level}!")
                 
                 # Check for Upgrades (Tier II, III, IV)
                 pass_tier = None
                 # User: "when upgrading to level 2-4, he chooses a Tier II card"
                 # "from 5-7, a tier III card"
                 # "level 8 he gets his ultimate"
                 
                 if 2 <= hero.level <= 4:
                     pass_tier = CardTier.II
                 elif 5 <= hero.level <= 7:
                     pass_tier = CardTier.III
                 elif hero.level == 8:
                     pass_tier = CardTier.IV
                     
                 if pass_tier:
                     if pass_tier == CardTier.IV:
                         # Auto-grant Ultimate
                         # Find Tier IV card in deck
                         found_ult = False
                         for c in hero.deck:
                             if c.tier == CardTier.IV:
                                 c.state = "PASSIVE" # CardState.PASSIVE
                                 print(f"   Unlocked Ultimate: {c.name}")
                                 found_ult = True
                                 break
                     else:
                         # Tier II or III: Choice Required
                         # We push an input request.
                         # Note: Queueing multiple requests is valid (LIFO).
                         req_id = str(uuid.uuid4())
                         req = InputRequest(
                             id=req_id,
                             player_id=hero.id,
                             request_type=InputRequestType.UPGRADE_CHOICE,
                             context={"level": hero.level, "tier": pass_tier}
                         )
                         state.input_stack.append(req)
                         any_upgrade_pending = True
            
             # Pity Coin
             if not leveled_up:
                 hero.gold += 1
                 print(f"Hero {hero.id} gained Pity Coin (Gold: {hero.gold})")

    # 5. Advance Time (Only if NOT waiting for inputs)
    if any_upgrade_pending:
        return 
        
    state.turn = 1
    state.round += 1
    state.phase = GamePhase.PLANNING

from typing import Dict, Any, Optional
from goa2.domain.state import GameState
from goa2.domain.models import TeamColor, MinionType, Minion, Hero
from goa2.domain.types import UnitID

def calculate_minion_defense_modifier(state: GameState, target_unit_id: UnitID) -> int:
    """
    Calculates the cumulative defense modifier provided by nearby minions.
    Uses Hex.ring for optimized spatial lookups.
    
    Logic:
    - Allied Melee/Heavy (Range 1): +1 Defense
    - Enemy Minion (Range 1): -1 Defense
    - Enemy Ranged Minion (Range 2): -1 Defense
    """
    target_loc = state.unit_locations.get(target_unit_id)
    if not target_loc:
        return 0
        
    target_unit = state.get_unit(target_unit_id)
    if not target_unit:
        return 0
        
    total_mod = 0
    target_team = target_unit.team

    # Helper to check occupant of a hex
    def get_unit_at(hex_coord):
        # Invert unit_locations or check board tiles
        # Given we have state.board.tiles, checking tiles is O(1)
        tile = state.board.tiles.get(hex_coord)
        if tile and tile.occupant_id:
            return state.get_unit(tile.occupant_id)
        return None

    # --- RANGE 1 (Ring 1) ---
    for hex_coord in state.board.get_ring(target_loc, 1):
        unit = get_unit_at(hex_coord)
        if not unit or not isinstance(unit, Minion):
            continue
            
        if unit.team == target_team:
            # Allied Melee/Heavy gives +1
            if unit.type in (MinionType.MELEE, MinionType.HEAVY):
                total_mod += 1
        else:
            # ANY Enemy minion at Range 1 gives -1
            total_mod -= 1

    # --- RANGE 2 (Ring 2) ---
    for hex_coord in state.board.get_ring(target_loc, 2):
        unit = get_unit_at(hex_coord)
        if not unit or not isinstance(unit, Minion):
            continue
            
        # Only Enemy Ranged at Range 2 gives -1
        if unit.team != target_team and unit.type == MinionType.RANGED:
            total_mod -= 1
                    
    return total_mod
from goa2.domain.state import GameState
from goa2.domain.models import MinionType, Minion, Hero, StatType
from goa2.domain.types import UnitID, BoardEntityID

def get_computed_stat(state: GameState, unit_id: UnitID, stat_type: StatType, base_value: int = 0) -> int:
    """
    Calculates the final value of a stat for a unit.
    Formula: Base + Items + Modifiers
    """
    unit = state.get_unit(unit_id)
    if not unit:
        return base_value
    
    total = base_value
    
    # 1. Add Item Bonuses (for Heroes)
    if isinstance(unit, Hero):
        total += unit.items.get(stat_type, 0)
        
    # 2. Add Active Modifiers
    for mod in state.active_modifiers:
        if str(mod.target_id) == str(unit_id) and mod.stat_type == stat_type:
            total += mod.value_mod
            
    return total

def has_status(state: GameState, entity_id: BoardEntityID, status_tag: str) -> bool:
    """Checks if an entity has a specific status tag/override."""
    for mod in state.active_modifiers:
        if str(mod.target_id) == str(entity_id) and mod.status_tag == status_tag:
            return True
    return False

def calculate_minion_defense_modifier(state: GameState, target_unit_id: UnitID) -> int:
    """
    Calculates the cumulative defense modifier provided by nearby minions.
    Uses Hex.ring for optimized spatial lookups.
    """
    target_loc = state.unit_locations.get(target_unit_id)
    if not target_loc:
        return 0
        
    target_unit = state.get_unit(target_unit_id)
    if not target_unit:
        return 0
        
    total_mod = 0
    target_team = target_unit.team

    def get_unit_at(hex_coord):
        tile = state.board.tiles.get(hex_coord)
        if tile and tile.occupant_id:
            return state.get_unit(UnitID(str(tile.occupant_id)))
        return None

    # --- RANGE 1 (Ring 1) ---
    for hex_coord in state.board.get_ring(target_loc, 1):
        unit = get_unit_at(hex_coord)
        if not unit or not isinstance(unit, Minion):
            continue
            
        if unit.team == target_team:
            if unit.type in (MinionType.MELEE, MinionType.HEAVY):
                total_mod += 1
        else:
            total_mod -= 1

    # --- RANGE 2 (Ring 2) ---
    for hex_coord in state.board.get_ring(target_loc, 2):
        unit = get_unit_at(hex_coord)
        if not unit or not isinstance(unit, Minion):
            continue
            
        if unit.team != target_team and unit.type == MinionType.RANGED:
            total_mod -= 1
                    
    return total_mod
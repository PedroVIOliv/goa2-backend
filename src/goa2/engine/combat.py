from typing import Optional, List, Dict
from goa2.domain.models import Card, StatType, Unit, Hero
from goa2.domain.hex import Hex

from goa2.domain.state import GameState
from goa2.domain.models import TeamColor

def calculate_attack_power(card: Optional[Card], attacker: Hero) -> int:
    """
    Calculates total attack power.
    Base (from Card?? No field yet, assume 4) + Hero Items.
    """
    base_power = 0
    if card and card.primary_action_value is not None:
        base_power = card.primary_action_value
    elif not card:
        base_power = 4 # Fallback for tests passing None
    
    # Add Item Bonuses
    item_bonus = attacker.items.get(StatType.ATTACK, 0)
    
    return base_power + item_bonus

def calculate_defense_power(defender: Hero, state: GameState) -> int:
    """
    Calculates total defense power.
    Base (3) + Hero Items + Minion Auras.
    """
    base_defense = 3
    
    # Item Bonuses
    item_bonus = defender.items.get(StatType.DEFENSE, 0)
    
    # Minion Auras (Adjacent Friendly Minions)
    aura_bonus = 0
    defender_loc = state.unit_locations.get(defender.id)
    
    if defender_loc:
        # Check all adjacent hexes
        for neighbor in defender_loc.neighbors():
            # Check for Minion in Board Tile
            tile = state.board.tiles.get(neighbor)
            if tile and tile.occupant_id:
                # Resolve Occupant
                # Is it a minion?
                unit_id = str(tile.occupant_id) # BoardEntityID -> str
                unit_id = str(tile.occupant_id)
                # Lookup Minion in Teams
                minion_obj = None
                for t in state.teams.values():
                     for m in t.minions:
                         if m.id == unit_id:
                             minion_obj = m
                             break
                     if minion_obj: break
                
                if minion_obj and minion_obj.team == defender.team:
                    # Friendly Minion Aura: +1 Defense
                    aura_bonus += 1
                        
    return base_defense + item_bonus + aura_bonus

def resolve_combat(attack_power: int, defense_power: int) -> bool:
    """
    Returns True if Attacker wins (Target Defeated).
    """
    return attack_power > defense_power

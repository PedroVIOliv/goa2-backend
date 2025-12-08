from goa2.domain.models import Card, StatType, Unit, Hero, MinionType
from goa2.engine.effects import EffectContext, EffectRegistry
from typing import Optional, List, Dict
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

def calculate_defense_power(defender: Hero, state: GameState, card: Optional[Card] = None, ctx: Optional[EffectContext] = None) -> int:
    """
    Calculates total defense power.
    Base (3 or Card Value) + Hero Items + Minion Auras.
    """
    base_defense = 3
    if card:
        if card.primary_action == StatType.DEFENSE and card.primary_action_value is not None:
             base_defense = card.primary_action_value
        elif StatType.DEFENSE in card.secondary_actions:
             base_defense = card.secondary_actions[StatType.DEFENSE]
    
    # Item Bonuses
    item_bonus = 0
    if getattr(defender, 'items', None):
         item_bonus = defender.items.get(StatType.DEFENSE, 0)
    
    # Minion Auras
    aura_bonus = 0
    defender_loc = state.unit_locations.get(defender.id)
    
    if defender_loc:
        # --- Ring 1 Check (Distance 1) ---
        # Melee/Heavy Friend: +1
        # Melee/Heavy Enemy: -1
        # Ranged Enemy: -1
        for hex_loc in defender_loc.ring(1):
             tile = state.board.tiles.get(hex_loc)
             if tile and tile.occupant_id:
                  # Check Occupant
                  unit_id = str(tile.occupant_id)
                  minion_obj = None
                  # Find minion
                  for t in state.teams.values():
                       for m in t.minions:
                           if m.id == unit_id:
                               minion_obj = m
                               break
                       if minion_obj: break
                  
                  if minion_obj:
                       # Friend
                       if minion_obj.team == defender.team:
                           if not minion_obj.type == MinionType.RANGED: # Melee or Heavy
                               aura_bonus += 1
                       # Enemy
                       else:
                           if not minion_obj.type == MinionType.RANGED: # Melee or Heavy
                               aura_bonus -= 1
                           else: # Ranged
                               aura_bonus -= 1
                               
        # --- Ring 2 Check (Distance 2) ---
        # Ranged Enemy: -1
        for hex_loc in defender_loc.ring(2):
             tile = state.board.tiles.get(hex_loc)
             if tile and tile.occupant_id:
                  unit_id = str(tile.occupant_id)
                  minion_obj = None
                  for t in state.teams.values():
                       for m in t.minions:
                           if m.id == unit_id:
                               minion_obj = m
                               break
                       if minion_obj: break
                  
                  if minion_obj and minion_obj.team != defender.team:
                       if minion_obj.type == MinionType.RANGED:
                           aura_bonus -= 1
                        
    
    components = {
        "base": base_defense,
        "items": item_bonus,
        "auras": aura_bonus
    }
    
    # Apply Effect Hook
    if card and card.effect_id:
        effect = EffectRegistry.get(card.effect_id)
        if effect and ctx:
             effect.modify_defense_components(components, ctx)
        elif effect and not ctx:
             # Try to run without full context if possible? 
             # Or construct partial context here?
             # Better to require ctx for modifications.
             pass

    return sum(components.values())

def resolve_combat(attack_power: int, defense_power: int) -> bool:
    """
    Returns True if Attacker wins (Target Defeated).
    """
    return attack_power > defense_power

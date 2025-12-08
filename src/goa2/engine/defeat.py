from typing import Optional
from goa2.domain.state import GameState
from goa2.domain.models import Minion, Hero, CardState
from goa2.domain.types import UnitID

def calculate_life_loss(level: int) -> int:
    """
    Calculates Life Counters lost based on Hero Level.
    Level 1-3: 1
    Level 4-6: 2
    Level 7-8: 3
    """
    if level <= 3: return 1
    if level <= 6: return 2
    return 3

def defeat_unit(state: GameState, unit_id: UnitID, killer_id: Optional[UnitID] = None) -> None:
    """
    Handles the defeat of a unit (Minion or Hero).
    - Minion: Remove, Award Coins to Killer.
    - Hero: Life Loss, Resolution Cancel, Killer Coins (Level), Team Coins (Life Loss).
    """
    
    # 1. Identify Unit
    unit = state.get_unit(unit_id)
    if not unit:
        return
        
    killer_hero = None
    if killer_id:
        killer_hero = state.get_hero(killer_id)

    # --- MINION ---
    if isinstance(unit, Minion):
        print(f"[Defeat] Minion {unit.name} defeated.")
        
        # Remove Unit from Board
        if unit.id in state.unit_locations:
            loc = state.unit_locations[unit.id]
            del state.unit_locations[unit.id]
            if loc in state.board.tiles and state.board.tiles[loc].occupant_id == unit.id:
                 state.board.tiles[loc].occupant_id = None
                 
        # Remove from Team
        if unit.team:
            tm = state.teams.get(unit.team)
            if tm:
                tm.minions = [m for m in tm.minions if m.id != unit.id]

        # Reward Killer
        if killer_hero:
            reward = unit.value
            killer_hero.gold += reward
            print(f"   {killer_hero.name} gains {reward} gold.")
            
    # --- HERO ---
    elif isinstance(unit, Hero):
        print(f"[Defeat] Hero {unit.name} (Lvl {unit.level}) defeated.")
        
        # 1. Life Loss
        loss = calculate_life_loss(unit.level)
        unit_team = state.teams.get(unit.team) if unit.team else None
        if unit_team:
            unit_team.life_counters = max(0, unit_team.life_counters - loss)
            print(f"   {unit_team.color.name} Team loses {loss} Life Counter(s). Remaining: {unit_team.life_counters}")
            
        # 2. Card Cancellation
        # Search queue for unit's card
        # Queue item: (hero_id, card)
        # We need to remove it but mark resolved.
        # Queue order matters? Yes. Removing from middle is fine.
        
        found_idx = -1
        for i, (hid, card) in enumerate(state.resolution_queue):
            if hid == unit.id:
                found_idx = i
                break
        
        if found_idx != -1:
            _, card = state.resolution_queue.pop(found_idx)
            card.state = CardState.RESOLVED
            print(f"   {unit.name}'s card '{card.name}' resolved with NO EFFECT.")
            
        # 3. Rewards
        enemy_team = None
        for t in state.teams.values():
            if t.color != unit.team: # Enemy Team
                enemy_team = t
                break
                
        if enemy_team:
            # Killer Reward (Equal to Victim Level)
            if killer_hero and killer_hero.team != unit.team:
                reward = unit.level
                killer_hero.gold += reward
                print(f"   Killer {killer_hero.name} gains {reward} gold (Level).")
                
            # Other Enemies Reward (Equal to Life Loss)
            for enemy in enemy_team.heroes:
                if killer_hero and enemy.id == killer_hero.id:
                    continue # Already paid killer? OR does killer get BOTH?
                    # "give coins to MINION killer..." (Separate rules)
                    # "give coins to every OTHER enemy hero"
                    # So Killer gets Level. Others get Life Loss amount.
                
                enemy.gold += loss
                print(f"   Enemy {enemy.name} gains {loss} gold (Life Loss Share).")
        
        # Note: Hero is NOT removed from board or team. They just Respawn later (handled by Phase logic).
        # Actually, "Defeated heroes are placed on their player board".
        # So we SHOULD remove from board?
        # Yes, usually they leave the hex.
        if unit.id in state.unit_locations:
             loc = state.unit_locations[unit.id]
             del state.unit_locations[unit.id]
             if loc in state.board.tiles and state.board.tiles[loc].occupant_id == unit.id:
                 state.board.tiles[loc].occupant_id = None

from typing import List, Dict, Tuple, Optional
from goa2.domain.state import GameState
from goa2.domain.input import InputRequest, InputRequestType
from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, Hero, Card, CardTier, CardColor, ActionType, MinionType
from goa2.domain.types import HeroID, CardID, UnitID, BoardEntityID
from typing import Optional

from goa2.engine.actions import PlayCardCommand, RevealCardsCommand, ResolveNextCommand, SpawnMinionCommand, PerformMovementCommand, ChooseActionCommand

from goa2.engine.phases import GamePhase


from goa2.engine.map_logic import check_lane_push_trigger, execute_push
from goa2.engine.map_loader import load_map

def main():
    print("=== Guards of Atlantis II Engine (Phase 5 Map Logic) ===")
    
    # 1. Setup Board (Load from JSON)
    print("\n[Setup]")
    try:
        board = load_map("data/maps/test_map.json")
        print(f"Loaded Board: {len(board.zones)} zones, {len(board.spawn_points)} spawn points.")
        for z_id, z in board.zones.items():
             lbl = z.label or z.id
             n_lbls = [board.zones[nid].label or nid for nid in z.neighbors]
             print(f"   - Zone {lbl} neighbors: {n_lbls}")
    except FileNotFoundError:
        print("[!] Map file not found. Please ensure data/maps/test_map.json exists.")
        return

    # Mocking spawn points or initial units if map doesn't define them strictly yet
    # We will query zones by label to place units.
    
    def find_zone_by_label(b: Board, lbl: str) -> Optional[str]:
        for z in b.zones.values():
            if z.label == lbl:
                return z.id
        return None

    z_mid_id = find_zone_by_label(board, "Mid")
    z_red_base_id = find_zone_by_label(board, "RedBase")
    z_blue_base_id = find_zone_by_label(board, "BlueBase")

    state = GameState(board=board, teams={}, active_zone_id=z_mid_id if z_mid_id else list(board.zones.keys())[0])
    
    # Dynamic Placement Helper
    def get_first_hex(b: Board, z_id: str) -> Optional[Hex]:
        z = b.zones.get(z_id)
        if z and z.hexes:
            return list(z.hexes)[0]
        return None

    def get_second_hex(b: Board, z_id: str) -> Optional[Hex]:
        z = b.zones.get(z_id)
        if z and len(z.hexes) > 1:
            return list(z.hexes)[1]
        return None

    # Hero in Mid
    h_red_loc = get_first_hex(board, z_mid_id) or Hex(q=0,r=0,s=0)
    m_red_loc = get_second_hex(board, z_mid_id) or Hex(q=1,r=-1,s=0)
    
    # Hero in Blue Base (Target for FT)
    h_blue_loc = get_first_hex(board, z_blue_base_id) or Hex(q=10,r=0,s=-10)

    # Hero in Zone A
    from goa2.data.heroes import HeroRegistry
    
    # Red Hero: Knight
    hero_red = HeroRegistry.get("Knight")
    hero_red.team = TeamColor.RED
    hero_red.id = HeroID("h_red")
    
    # Put Teleport card in hand for the demo (normally in Deck)
    # The Knight deck has "Shield Bash", "March", "Defend"
    # We want to test FAST TRAVEL. 
    # Let's override the hand to include the demo FT card OR use the Rogue who has FT.
    # The user wants to see the "Knight" deck functionality? No, main.py tests specific things.
    # Let's overwrite the hand with the specific test card for now to keep the script passing.
    card_ft = Card(
        id=CardID("c_ft"), name="Teleport", tier=CardTier.UNTIERED, color=CardColor.GOLD,
        initiative=10, primary_action=ActionType.FAST_TRAVEL, primary_action_value=0, effect_id="e_ft", effect_text="Fast Travel"
    )
    hero_red.hand = [card_ft]
    
    state.teams[TeamColor.RED] = Team(color=TeamColor.RED, heroes=[hero_red])
    state.unit_locations[UnitID("h_red")] = h_red_loc 
    if h_red_loc in board.tiles:
        board.tiles[h_red_loc].occupant_id = BoardEntityID("h_red")
    
    # Minion in Zone A (Red's Minion)
    SpawnMinionCommand(m_red_loc, MinionType.MELEE, TeamColor.RED, UnitID("m_red_1")).execute(state)
    
    # Blue Hero (Target) in FAR zone to allow FT from Mid
    # Blue Hero: Rogue
    hero_blue = HeroRegistry.get("Rogue")
    hero_blue.team = TeamColor.BLUE
    hero_blue.id = HeroID("h_blue")
    
    state.teams[TeamColor.BLUE] = Team(color=TeamColor.BLUE, heroes=[hero_blue])
    state.unit_locations[UnitID("h_blue")] = h_blue_loc 
    if h_blue_loc in board.tiles:
        board.tiles[h_blue_loc].occupant_id = BoardEntityID("h_blue")
        
    print(f"Active Zone: {state.active_zone_id}")
    print(f"Red Hero at {h_red_loc}")
    print(f"Red Minion at {state.unit_locations[UnitID('m_red_1')]}")
    # print(f"Blue Hero at {state.unit_locations[UnitID('h_blue')]}")
    
    # Test 1: Push Check (Should be None, Red has 1 minion, Blue has 0 -> Blue lost? No, wait)
    print("\n[Test 1] Initial Push Check")
    losing = check_lane_push_trigger(state, state.active_zone_id)
    print(f"   Push Triggered? Losing Team: {losing}")
    
    # Test 2: Combat Math (Mocked)
    print("\n[Test 2] Combat Math Verification")
    from goa2.engine.combat import calculate_attack_power, calculate_defense_power
    # Red Hero (Item +1 Attack) attacking
    # Blue Hero (No items, No Minions nearby) defending
    atk = calculate_attack_power(None, hero_red) # Card None for MVP base 4
    def_val = calculate_defense_power(hero_blue, state)
    print(f"   Red Attack: {atk} (Expected 5: Base 4 + Item 1)")
    print(f"   Blue Defense: {def_val} (Expected 3: Base 3 + Aura 0)")
    
    # Test 3: Fast Travel (Success Case)
    # 2. Planning
    state.phase = GamePhase.PLANNING
    PlayCardCommand(HeroID("h_red"), CardID("c_ft")).execute(state)
    
    # 3. Revelation
    RevealCardsCommand().execute(state)

    print("\n[Resolution Phase]")
    MAX_STEPS = 5
    steps = 0

    while state.phase == GamePhase.RESOLUTION and steps < MAX_STEPS:
        steps += 1
        
        # 1. If stack empty, pull next card
        if not state.input_stack:
            # If queue is empty, ResolveNext will finish the phase
            ResolveNextCommand().execute(state)
            
        # 2. If stack has request, handle it
        if state.input_stack:
            req = state.input_stack[-1]
            
            if req.request_type == InputRequestType.ACTION_CHOICE:
                print(f"   [Input] h_red chooses FAST_TRAVEL")
                ChooseActionCommand(ActionType.FAST_TRAVEL).execute(state)
                
            elif req.request_type == InputRequestType.MOVEMENT_HEX:
                # Target Zone Blue Base
                # We placed h_blue at h_blue_loc (first hex).
                # FT needs to land in Blue Base.
                # Let's target h_blue_loc if empty? No it's occupied by h_blue.
                # Use second hex if available?
                # Or just try h_blue_loc and expect failure or success if FT allows replacement (unlikely).
                # Let's find an empty hex in Blue Base.
                target = get_second_hex(board, z_blue_base_id) or h_blue_loc
                print(f"   [Input] h_red targets {target} (In Zone Blue Base)")
                try:
                    PerformMovementCommand(target).execute(state)
                    print(f"   [V] Fast Travel Successful to {target}")
                except ValueError as e:
                    print(f"   [X] Failed: {e}")

            elif req.request_type == InputRequestType.SELECT_ENEMY:
                 pass
                 
    print("\n[End Simulation]")
    print(f"Final Hero Pos: {state.unit_locations[UnitID('h_red')]}")
    # Verify Tile System
    final_hex = Hex(q=2,r=0,s=-2)
    tile = state.board.tiles.get(final_hex)
    if tile and tile.occupant_id == "h_red":
        print(f"   [V] Tile System Sync: {final_hex} occupied by {tile.occupant_id}")
    else:
        print(f"   [X] Tile System Sync FAILED: {final_hex} occupant is {tile.occupant_id if tile else 'None'}")
    
if __name__ == "__main__":
    main()



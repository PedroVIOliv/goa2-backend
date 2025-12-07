from goa2.domain.state import GameState
from goa2.domain.input import InputRequest, InputRequestType
from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, Hero, Card, CardTier, CardColor, ActionType, MinionType
from goa2.domain.types import HeroID, CardID, UnitID, BoardEntityID
from goa2.engine.actions import PlayCardCommand, RevealCardsCommand, ResolveNextCommand, SpawnMinionCommand, PerformMovementCommand, ChooseActionCommand

from goa2.engine.phases import GamePhase

from goa2.engine.actions import PlayCardCommand, RevealCardsCommand, ResolveNextCommand, SpawnMinionCommand, PerformMovementCommand, ChooseActionCommand, AttackCommand, PlayDefenseCommand

from goa2.engine.actions import PlayCardCommand, RevealCardsCommand, ResolveNextCommand, SpawnMinionCommand, PerformMovementCommand, ChooseActionCommand, AttackCommand, PlayDefenseCommand
from goa2.engine.map_logic import check_lane_push_trigger, execute_push

def main():
    print("=== Guards of Atlantis II Engine (Phase 5 Map Logic) ===")
    
    # 1. Setup Board with 2 Zones
    print("\n[Setup]")
    board = Board() 
    # Mocking Zones manually for this test since Board() init might be empty
    # We need to inject zones.
    from goa2.domain.board import Zone
    zone_a = Zone(id="z_mid", hexes={Hex(q=0,r=0,s=0), Hex(q=1,r=-1,s=0), Hex(q=0,r=-1,s=1)})
    zone_b = Zone(id="z_base_blue", hexes={Hex(q=2,r=0,s=-2), Hex(q=3,r=0,s=-3)}) # Far away + neighbor
    zone_c = Zone(id="z_base_red", hexes={Hex(q=-2,r=0,s=2)}) 
    zone_d = Zone(id="z_void", hexes={Hex(q=10,r=0,s=-10)})
    board.zones = {"z_mid": zone_a, "z_base_blue": zone_b, "z_base_red": zone_c, "z_void": zone_d}
    # Lane: Red -> Mid -> Blue
    board.lane = ["z_base_red", "z_mid", "z_base_blue"] 
    board.populate_tiles_from_zones()
    
    state = GameState(board=board, teams={}, active_zone_id="z_mid")
    
    # Hero in Zone A
    card_ft = Card(
        id=CardID("c_ft"), name="Teleport", tier=CardTier.UNTIERED, color=CardColor.GOLD,
        initiative=10, primary_action=ActionType.FAST_TRAVEL, effect_id="e_ft", effect_text="Fast Travel"
    )
    hero_red = Hero(id=HeroID("h_red"), name="Knight", team=TeamColor.RED, deck=[], hand=[card_ft], gold=0)
    # Add Item: +1 Attack
    from goa2.domain.models import StatType
    hero_red.items[StatType.ATTACK] = 1
    
    state.teams[TeamColor.RED] = Team(color=TeamColor.RED, heroes=[hero_red])
    state.unit_locations[UnitID("h_red")] = Hex(q=0,r=0,s=0) # In Zone A
    if Hex(q=0,r=0,s=0) in board.tiles:
        board.tiles[Hex(q=0,r=0,s=0)].occupant_id = BoardEntityID("h_red")
    
    # Minion in Zone A (Red's Minion)
    SpawnMinionCommand(Hex(q=1,r=-1,s=0), MinionType.MELEE, TeamColor.RED, UnitID("m_red_1")).execute(state)
    
    # Blue Hero (Target) in FAR zone to allow FT from Mid
    hero_blue = Hero(id=HeroID("h_blue"), name="Rogue", team=TeamColor.BLUE, deck=[], hand=[], gold=0)
    state.teams[TeamColor.BLUE] = Team(color=TeamColor.BLUE, heroes=[hero_blue])
    state.unit_locations[UnitID("h_blue")] = Hex(q=10,r=0,s=-10) # In Void
    if Hex(q=10,r=0,s=-10) in board.tiles:
        board.tiles[Hex(q=10,r=0,s=-10)].occupant_id = BoardEntityID("h_blue")
        
    print(f"Active Zone: {state.active_zone_id}")
    print(f"Red Hero at {state.unit_locations[UnitID('h_red')]}")
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
                target = Hex(q=2,r=0,s=-2) # Target Zone B
                print(f"   [Input] h_red targets {target} (In Zone B)")
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

if __name__ == "__main__":
    main()

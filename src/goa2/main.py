from goa2.domain.state import GameState
from goa2.domain.input import InputRequest, InputRequestType
from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import Team, TeamColor, Hero, Card, CardTier, CardColor, ActionType, MinionType
from goa2.domain.types import HeroID, CardID, UnitID
from goa2.engine.actions import PlayCardCommand, RevealCardsCommand, ResolveNextCommand, SpawnMinionCommand, PerformMovementCommand, ChooseActionCommand

from goa2.engine.phases import GamePhase

from goa2.engine.actions import PlayCardCommand, RevealCardsCommand, ResolveNextCommand, SpawnMinionCommand, PerformMovementCommand, ChooseActionCommand, AttackCommand, PlayDefenseCommand

def main():
    print("=== Guards of Atlantis II Engine (Phase 4 Combat) ===")
    
    # 1. Setup
    print("\n[Setup]")
    board = Board() 
    state = GameState(board=board, teams={})
    
    # Define Heroes
    # Hero A (Knight) - Red
    card_slash = Card(
        id=CardID("c_slash"), name="Slash", tier=CardTier.UNTIERED, color=CardColor.GOLD, 
        initiative=10, primary_action=ActionType.ATTACK, effect_id="e2", effect_text="Attack 4"
    )
    hero_a = Hero(id=HeroID("h_red"), name="Knight", team=TeamColor.RED, deck=[], hand=[card_slash], gold=0)
    
    # Hero B (Rogue) - Blue
    card_dodge = Card(
        id=CardID("c_dodge"), name="Dodge", tier=CardTier.UNTIERED, color=CardColor.GOLD,
        initiative=5, primary_action=ActionType.MOVEMENT, secondary_actions={ActionType.DEFENSE:0}, 
        effect_id="e3", effect_text="Move 2"
    )
    hero_b = Hero(id=HeroID("h_blue"), name="Rogue", team=TeamColor.BLUE, deck=[], hand=[card_dodge], gold=0)
    
    state.teams[TeamColor.RED] = Team(color=TeamColor.RED, heroes=[hero_a])
    state.teams[TeamColor.BLUE] = Team(color=TeamColor.BLUE, heroes=[hero_b])
    
    # Place Units (Adjacent)
    state.unit_locations[UnitID("h_red")] = Hex(q=0, r=0, s=0)
    state.unit_locations[UnitID("h_blue")] = Hex(q=1, r=-1, s=0) # NE neighbor
    
    print(f"Red Hero at {state.unit_locations[UnitID('h_red')]}")
    print(f"Blue Hero at {state.unit_locations[UnitID('h_blue')]}")
    
    # 2. Planning Phase
    state.phase = GamePhase.PLANNING
    print("\n[Planning Phase]")
    PlayCardCommand(HeroID("h_red"), CardID("c_slash")).execute(state)
    # Blue doesn't play for this test (or plays dummy)
    # We focus on Red's turn.
    
    # 3. Revelation
    RevealCardsCommand().execute(state)
    
    # 4. Resolution Loop
    print("\n[Resolution Phase]")
    MAX_STEPS = 10
    steps = 0
    while state.phase == GamePhase.RESOLUTION and steps < MAX_STEPS:
        steps += 1
        
        if not state.input_stack:
            print(f">> ResolveNext (Stack Empty, Queue Size: {len(state.resolution_queue)})")
            ResolveNextCommand().execute(state)
            
            if state.input_stack:
                 req = state.input_stack[-1]
                 print(f"   [!] Paused: {req.request_type.name} from {req.player_id}")
                 
        else:
            req = state.input_stack[-1]
            player_id = req.player_id
            
            if req.request_type == InputRequestType.ACTION_CHOICE:
                print(f"   [Input] {player_id} chooses ATTACK")
                ChooseActionCommand(ActionType.ATTACK).execute(state)
                
            elif req.request_type == InputRequestType.SELECT_ENEMY:
                target_id = UnitID("h_blue")
                print(f"   [Input] {player_id} targets {target_id}")
                AttackCommand(target_id).execute(state)
                # Confirm we pushed Defense Request
                if state.input_stack[-1].request_type == InputRequestType.DEFENSE_CARD:
                    print("   [!] VALIDATION: Stack now waiting for DEFENSE")

            elif req.request_type == InputRequestType.DEFENSE_CARD:
                print(f"   [Input] {player_id} defends (Pass/Block)")
                # Simulate passing (taking valid hit) or playing card
                # For this test, let's play 'None' (Take hit)
                PlayDefenseCommand(None).execute(state)
                print("   [!] Combat Resolved.")
            
            else:
                print(f"   Unknown Request: {req.request_type}")
                break
                
    print("\n[End Simulation]")
    
if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()

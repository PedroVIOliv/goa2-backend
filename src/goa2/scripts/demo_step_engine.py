from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor
from goa2.engine.steps import LogMessageStep, SelectTargetStep, DamageStep
from goa2.engine.handler import process_resolution_stack, push_steps

def run_demo():
    print("=== Multi-Player Step Engine Demo ===")
    
    # 1. Setup
    state = GameState(
        board=Board(),
        teams={TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[])},
        current_actor_id="hero_red_01" # It is Red's turn
    )
    
    # 2. Define Card Logic
    # Red Player selects target -> Blue Player (hardcoded ID for demo) selects defense
    card_steps = [
        LogMessageStep(message="[Turn] It is {actor_id}'s turn.", ),
        
        # Step 1: Active Player selects target
        SelectTargetStep(
            prompt="[Red] Select target for Attack", 
            output_key="target_id",
            player_id="hero_red_01" 
        ),
        
        # Step 2: Reaction - Opponent (Blue) chooses to defend
        # In a real engine, we'd dynamically determine who the owner of 'target_id' is.
        # Here, we hardcode it to verify the mechanism.
        SelectTargetStep(
            prompt="[Blue] You are being attacked! Select a card to Discard/Defend.",
            output_key="defense_card_id",
            player_id="hero_blue_01"
        ),
        
        LogMessageStep(message="[Result] Red attacked {target_id}, Blue defended with {defense_card_id}.")
    ]
    
    state.execution_context["actor_id"] = "hero_red_01"
    
    print("[1] Player plays 'Coordinated Attack'")
    push_steps(state, card_steps)
    
    # --- Loop 1: Red Input ---
    print("\n[2] Engine Processing (Pass 1)...")
    req = process_resolution_stack(state)
    print(f"[!] Paused. Request: {req}")
    
    # Simulate Red Input
    print("   -> Red Player selects 'hero_blue_01'")
    state.execution_stack[-1].pending_input = {"selected_id": "hero_blue_01"}
    
    # --- Loop 2: Blue Input ---
    print("\n[3] Engine Processing (Pass 2)...")
    req = process_resolution_stack(state)
    print(f"[!] Paused. Request: {req}")
    
    # Simulate Blue Input
    print("   -> Blue Player selects 'card_deflect'")
    state.execution_stack[-1].pending_input = {"selected_id": "card_deflect"}
    
    # --- Loop 3: Resolution ---
    print("\n[4] Engine Processing (Pass 3)...")
    req = process_resolution_stack(state)
    
    if not req:
        print("\n[=] Resolution Complete.")

if __name__ == "__main__":
    run_demo()
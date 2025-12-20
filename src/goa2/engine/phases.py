from typing import List, Tuple, Dict, Any, Optional
from goa2.domain.state import GameState
from goa2.domain.models import TeamColor, GamePhase, Card
from goa2.domain.types import HeroID
from goa2.engine.handler import push_steps
from goa2.engine.steps import ResolveTieBreakerStep, LogMessageStep

def commit_card(state: GameState, hero_id: HeroID, card: Card):
    """
    Called when a player selects a card during the Planning Phase.
    """
    if state.phase != GamePhase.PLANNING:
        print(f"   [!] Cannot commit card. Game is in {state.phase}")
        return

    state.pending_inputs[hero_id] = card
    print(f"   [Planning] {hero_id} committed a card.")

    # Check if all heroes have committed
    total_heroes = sum(len(team.heroes) for team in state.teams.values())
    if len(state.pending_inputs) >= total_heroes:
        start_revelation_phase(state)

def start_revelation_phase(state: GameState):
    """
    Reveals all cards and builds the initial resolution queue.
    """
    state.phase = GamePhase.REVELATION
    print("\n=== REVELATION PHASE ===")

    # 1. Reveal all cards (set facedown = False)
    # 2. Build sorted list of (HeroID, Card)
    revealed_cards = []
    for h_id, card in state.pending_inputs.items():
        card.is_facedown = False
        revealed_cards.append((h_id, card))

    # 3. Sort by Initiative (Descending)
    # Note: Primary sort is initiative. Tie-breakers handled during resolution.
    revealed_cards.sort(key=lambda x: x[1].initiative, reverse=True)
    
    state.resolution_queue = revealed_cards
    state.pending_inputs = {} # Clear buffer
    
    # Transition to Resolution
    start_resolution_phase(state)

def start_resolution_phase(state: GameState):
    state.phase = GamePhase.RESOLUTION
    print("=== RESOLUTION PHASE ===")
    process_next_in_queue(state)

def process_next_in_queue(state: GameState):
    """
    Pops the next card(s) from the queue and populates the execution stack.
    Handles grouping for ties.
    """
    if not state.resolution_queue:
        print("   [Queue] All cards resolved. Turn End.")
        # Trigger Turn End Logic here
        return

    # 1. Identify Tied Group
    top_h_id, top_card = state.resolution_queue[0]
    target_initiative = top_card.initiative
    
    tied_group = []
    while state.resolution_queue and state.resolution_queue[0][1].initiative == target_initiative:
        tied_group.append(state.resolution_queue.pop(0))

    # 2. If no tie -> Push logic immediately
    if len(tied_group) == 1:
        hero_id, card = tied_group[0]
        state.current_actor_id = hero_id
        print(f"   [Queue] Next actor: {hero_id} (Init: {card.initiative})")
        
        # Convert Card to Steps (Macro Step)
        # For now, we use a placeholder log step. 
        # In real engine, we'd have card.get_steps()
        push_steps(state, [LogMessageStep(message=f"Resolving card for {hero_id}")])
        return

    # 3. If tie -> Push Tie Breaker Step
    print(f"   [Queue] Tie detected at Initiative {target_initiative} between {[h for h,c in tied_group]}")
    
    # We push the tied cards BACK into the queue (they will be resolved one by one after tie break)
    # Actually, we should put them in a special state or context?
    # Better: Push a TieBreakerStep that, when resolved, pushes the winner's logic 
    # AND pushes the remaining tied players back onto the stack/queue.
    
    state.execution_stack.append(ResolveTieBreakerStep(
        tied_hero_ids=[h for h,c in tied_group]
    ))
    
    # We need to remember the cards! 
    # We store the tied_group in context so the TieBreaker can access them.
    state.execution_context["tied_cards"] = tied_group

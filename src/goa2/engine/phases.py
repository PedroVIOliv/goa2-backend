from typing import List, Tuple, Dict, Any, Optional
from goa2.domain.state import GameState
from goa2.domain.models import TeamColor, GamePhase, Card, CardState
from goa2.domain.types import HeroID
from goa2.engine.handler import push_steps
from goa2.engine.steps import ResolveTieBreakerStep, LogMessageStep

def commit_card(state: GameState, hero_id: HeroID, card: Card):
    """
    Called when a player selects a card during the Planning Phase.
    Validates that the card is in the player's hand.
    """
    if state.phase != GamePhase.PLANNING:
        print(f"   [!] Cannot commit card. Game is in {state.phase}")
        return

    hero = state.get_hero(hero_id)
    if not hero:
        print(f"   [!] Error: Hero {hero_id} not found.")
        return

    # Check if card is in hand
    if card not in hero.hand:
        print(f"   [!] {hero_id} tried to play card {card.id} which is NOT in hand.")
        return

    # Move card from hand to pending buffer (Facedown on board)
    # Using helper to ensure state consistency
    try:
        hero.play_card(card)
    except ValueError as e:
        print(f"   [!] Error playing card: {e}")
        return

    state.pending_inputs[hero_id] = card
    print(f"   [Planning] {hero_id} committed a card.")

    _check_phase_transition(state)

def pass_turn(state: GameState, hero_id: HeroID):
    """
    Called when a player has no cards and must Pass.
    """
    if state.phase != GamePhase.PLANNING:
        return
    
    hero = state.get_hero(hero_id)
    if not hero:
        return

    # Rule Check: You must play a card if able.
    if len(hero.hand) > 0:
        print(f"   [!] {hero_id} cannot Pass (Hand has {len(hero.hand)} cards).")
        return
        
    state.pending_inputs[hero_id] = None
    print(f"   [Planning] {hero_id} PASSED.")
    
    _check_phase_transition(state)

def _check_phase_transition(state: GameState):
    # Check if all heroes have committed (Card or Pass)
    total_heroes = sum(len(team.heroes) for team in state.teams.values())
    if len(state.pending_inputs) >= total_heroes:
        start_revelation_phase(state)

def start_revelation_phase(state: GameState):
    """
    Reveals all cards and sets up the unresolved pool.
    """
    state.phase = GamePhase.REVELATION
    print("\n=== REVELATION PHASE ===")

    state.unresolved_hero_ids = []
    
    # Assign cards to heroes and populate the unresolved list
    for h_id, card in state.pending_inputs.items():
        # If card is None, the player Passed. They do not enter the resolution pool.
        if card is None:
            continue

        hero = state.get_hero(h_id)
        if hero:
            card.is_facedown = False
            # card.state is already UNRESOLVED from play_card
            
            hero.current_turn_card = card
            state.unresolved_hero_ids.append(h_id)
        else:
            print(f"   [!] Error: Hero {h_id} not found during revelation.")

    state.pending_inputs = {} # Clear buffer
    
    # Transition to Resolution
    start_resolution_phase(state)

def start_resolution_phase(state: GameState):
    state.phase = GamePhase.RESOLUTION
    print("=== RESOLUTION PHASE ===")
    resolve_next_action(state)

def resolve_next_action(state: GameState):
    """
    Dynamically identifies the next actor based on current initiatives.
    Follows Rule: "After each action... re-identify the player with Highest Initiative".
    """
    if not state.unresolved_hero_ids:
        print("   [Queue] All cards resolved. Turn End.")
        # Trigger Turn End Logic here
        return

    # 1. Calculate current initiatives for all candidates
    candidates: List[Tuple[HeroID, int]] = []
    for h_id in state.unresolved_hero_ids:
        hero = state.get_hero(h_id)
        if hero:
            candidates.append((h_id, hero.get_effective_initiative()))
            
    if not candidates:
        return

    # 2. Sort Descending
    candidates.sort(key=lambda x: x[1], reverse=True)
    
    # 3. Identify Tied Group
    highest_init = candidates[0][1]
    tied_hero_ids = [c[0] for c in candidates if c[1] == highest_init]

    # 4. If no tie -> Resolve immediately
    if len(tied_hero_ids) == 1:
        hero_id = tied_hero_ids[0]
        state.current_actor_id = hero_id
        
        # Remove from pool immediately (Acting/Resolved)
        if hero_id in state.unresolved_hero_ids:
            state.unresolved_hero_ids.remove(hero_id)
            
        print(f"   [Resolution] Next actor: {hero_id} (Init: {highest_init})")
        
        # Convert Card to Steps
        push_steps(state, [LogMessageStep(message=f"Resolving card for {hero_id}")])
        return

    # 5. If tie -> Push Tie Breaker Step
    print(f"   [Resolution] Tie detected at Initiative {highest_init} between {tied_hero_ids}")
    
    # We DO NOT remove them from unresolved_hero_ids yet.
    # The TieBreaker step will determine the winner, remove ONLY the winner, 
    # and then recursively call resolve_next_action (implicitly via loop or explicit step).
    # Wait, the TieBreakerStep in steps.py handles the recursion.
    # But it needs to know how to "Execute" the winner.
    
    state.execution_stack.append(ResolveTieBreakerStep(
        tied_hero_ids=tied_hero_ids
    ))
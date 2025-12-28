from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Union, Tuple
from pydantic import BaseModel, Field

from goa2.domain.state import GameState
from goa2.domain.models import ActionType, Card, TeamColor
from goa2.domain.hex import Hex
from goa2.engine import rules # For validation

# -----------------------------------------------------------------------------
# Base Classes
# -----------------------------------------------------------------------------

class StepResult(BaseModel):
    """Result of a step execution."""
    is_finished: bool = True
    requires_input: bool = False
    input_request: Optional[Dict[str, Any]] = None
    new_steps: List['GameStep'] = Field(default_factory=list) # Steps to spawn

class GameStep(BaseModel, ABC):
    """
    Base class for all atomic game operations.
    Each step performs a single logic unit and can manage its own state.
    """
    type: str = "generic_step"
    
    # Unique ID for tracking this specific step instance (useful for input association)
    step_id: str = Field(default_factory=lambda: str(id(object()))) 
    
    # Input buffer: If the client provides input, it's stored here before 'resolve' is called
    pending_input: Optional[Any] = None

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        """
        Executes the step.
        :param state: Global GameState.
        :param context: Shared transient memory for the current Action chain.
        :return: StepResult indicating if we are done or need input.
        """
        raise NotImplementedError

# -----------------------------------------------------------------------------
# Common Steps
# -----------------------------------------------------------------------------

class LogMessageStep(GameStep):
    """Debugging step to print messages."""
    message: str
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        # Interpolate context variables
        msg = self.message.format(**context)
        print(f"   [STEP] {msg}")
        return StepResult(is_finished=True)


class SelectTargetStep(GameStep):
    """
    Waits for user input to select a target.
    Stores the result in 'context' under 'output_key'.
    """
    type: str = "select_target"
    prompt: str
    output_key: str = "target_id"
    valid_targets: Optional[List[str]] = None # List of IDs
    player_id: Optional[str] = None # Who should provide input? None = Active Player.

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        # Determine who should answer
        target_player = self.player_id if self.player_id else state.current_actor_id
        
        # 1. Check if we already have input
        if self.pending_input:
            # Validate input (Basic check)
            selected_id = self.pending_input.get("selected_id")
            
            if not selected_id:
                return StepResult(requires_input=True, input_request={
                    "type": "SELECT_UNIT", 
                    "prompt": "Invalid Selection. " + self.prompt,
                    "player_id": target_player
                })

            # Store in Context
            context[self.output_key] = selected_id
            print(f"   [INPUT] Player {target_player} selected {selected_id}")
            return StepResult(is_finished=True)
            
        # 2. If no input, Request it
        return StepResult(
            is_finished=False, 
            requires_input=True, 
            input_request={
                "type": "SELECT_UNIT",
                "prompt": self.prompt,
                "valid_targets": self.valid_targets,
                "player_id": target_player
            }
        )

class DamageStep(GameStep):
    """
    Deals damage to a unit found in the context.
    """
    type: str = "damage"
    target_key: str = "target_id"
    amount: int
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        target_id = context.get(self.target_key)
        if not target_id:
            print(f"   [ERROR] No target found for key '{self.target_key}'")
            return StepResult(is_finished=True)
            
        # In a real impl, we'd look up the Unit in state
        # unit = state.get_unit(target_id)
        # unit.hp -= self.amount
        
        print(f"   [LOGIC] Dealt {self.amount} damage to {target_id}")
        return StepResult(is_finished=True)

class DrawCardStep(GameStep):
    type: str = "draw_card"
    hero_id: str
    amount: int = 1
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        print(f"   [LOGIC] {self.hero_id} draws {self.amount} card(s).")
        return StepResult(is_finished=True)

# -----------------------------------------------------------------------------
# Complex Primitives (Move, Attack, Reaction)
# -----------------------------------------------------------------------------

class MoveUnitStep(GameStep):
    """
    Moves the active unit (or specified unit) to a target hex.
    Includes Pathfinding validation if destination is selected.
    """
    type: str = "move_unit"
    unit_id: Optional[str] = None # If None, uses current_actor
    destination_key: str = "target_hex" # Where to look in context for destination
    range_val: int = 1
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        actor_id = self.unit_id if self.unit_id else state.current_actor_id
        dest_val = context.get(self.destination_key)
        
        if not actor_id:
             print("   [ERROR] No actor for move.")
             return StepResult(is_finished=True)
             
        if not dest_val:
             print("   [ERROR] No destination for move.")
             return StepResult(is_finished=True)

        # Ensure destination is a Hex object
        if isinstance(dest_val, dict):
            dest_hex = Hex(**dest_val)
        else:
            dest_hex = dest_val # Assume it is already a Hex

        # 1. Get Current Location
        start_hex = state.unit_locations.get(actor_id)
        if not start_hex:
            print(f"   [ERROR] Unit {actor_id} has no location on board.")
            return StepResult(is_finished=True)

        # 2. Validate Path (using engine rules)
        is_valid = rules.validate_movement_path(
            board=state.board,
            unit_locations=state.unit_locations,
            start=start_hex,
            end=dest_hex,
            max_steps=self.range_val
        )
        
        if not is_valid:
            print(f"   [INVALID] Move for {actor_id} to {dest_hex} is illegal.")
            return StepResult(is_finished=True) # Mandatory step failed, halt.

        print(f"   [LOGIC] Moving {actor_id} from {start_hex} to {dest_hex} (Range {self.range_val})")
        state.move_unit(actor_id, dest_hex)
        return StepResult(is_finished=True)

class ReactionWindowStep(GameStep):
    """
    Gives a target player a chance to react (Play Defense Card).
    Validates that the chosen card actually HAS a Defense action.
    """
    type: str = "reaction_window"
    target_player_key: str = "target_id" # The player being attacked
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        target_id = context.get(self.target_player_key)
        if not target_id: return StepResult(is_finished=True) # Should not happen

        # Find Target Hero to check hand
        target_hero = state.get_hero(target_id)
        valid_defense_cards = []
        if target_hero:
            for card in target_hero.hand:
                # Check Primary or Secondary for Defense
                if (card.primary_action == ActionType.DEFENSE or 
                    ActionType.DEFENSE in card.secondary_actions):
                    valid_defense_cards.append(card)

        valid_ids = [c.id for c in valid_defense_cards]
        
        # 1. Check Input
        if self.pending_input:
            card_id = self.pending_input.get("selected_card_id")
            
            # Case A: PASS
            if card_id == "PASS":
                print(f"   [REACTION] Player {target_id} Passed (No Defense).")
                context["defense_value"] = 0
                return StepResult(is_finished=True)
            
            # Case B: Selected Card
            if card_id:
                # Calculate Value
                def_val = 0
                selected_card = next((c for c in valid_defense_cards if c.id == card_id), None)
                if selected_card:
                    if selected_card.primary_action == ActionType.DEFENSE:
                        def_val = selected_card.primary_action_value or 0
                    elif ActionType.DEFENSE in selected_card.secondary_actions:
                        def_val = selected_card.secondary_actions[ActionType.DEFENSE]
                
                # Fallback for demo if card not found in real object
                if not selected_card: 
                     def_val = 5 # Mock default
                
                print(f"   [REACTION] Player {target_id} defends with {card_id} (Value: {def_val})")
                context["defense_value"] = def_val
                
                return StepResult(is_finished=True)

        # 2. Request Input
        return StepResult(
            requires_input=True,
            input_request={
                "type": "SELECT_CARD_OR_PASS",
                "prompt": f"Player {target_id}, select a Defense card.",
                "player_id": target_id,
                "options": valid_ids + ["PASS"]
            }
        )

class ResolveCombatStep(GameStep):
    """
    Compares Attack vs Defense and applies results.
    Logic: If Defense >= Attack -> Blocked. Else -> Defeated.
    """
    type: str = "resolve_combat"
    damage: int # Base attack value from the card
    target_key: str = "victim_id"
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        defense_val = context.get("defense_value", 0)
        attack_val = self.damage
        target_id = context.get(self.target_key)
        
        print(f"   [COMBAT] Attack ({attack_val}) vs Defense ({defense_val})")
        
        if defense_val >= attack_val:
            print(f"   [RESULT] Attack BLOCKED! {target_id} is safe.")
        else:
            print(f"   [RESULT] Attack HITS! {target_id} is DEFEATED!")
            # Logic: state.kill_unit(target_id)
            
        return StepResult(is_finished=True)

class FinalizeHeroTurnStep(GameStep):
    """
    Finalizes a hero's turn by moving their current card to the resolved dashboard.
    Clears the actor context.
    """
    type: str = "finalize_hero_turn"
    hero_id: str

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        hero = state.get_hero(self.hero_id)
        if hero:
            print(f"   [LOGIC] Finalizing turn for {self.hero_id}. Card moved to Resolved.")
            hero.resolve_current_card()
        
        # Clear transient context for the next actor
        context.clear()
        state.current_actor_id = None
        
        return StepResult(is_finished=True)

class ResolveTieBreakerStep(GameStep):
    """
    Recursive handler for tied initiative players.
    1. Determines next winner (via Coin Flip or Team Choice).
    2. Pushes Winner's logic to stack.
    3. Pushes remaining players back via another TieBreakerStep.
    """
    type: str = "resolve_tie_breaker"
    tied_hero_ids: List[str]

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if not self.tied_hero_ids:
            return StepResult(is_finished=True)

        # 1. Group remaining tied players by Team
        teams_represented = {}
        for h_id in self.tied_hero_ids:
            hero = state.get_hero(h_id)
            if hero:
                teams_represented.setdefault(hero.team, []).append(h_id)

        winner_id = None
        needs_input = False
        target_team = None
        candidates = []

        # LOGIC:
        # A. If multiple teams -> Use Tie Breaker Coin to pick the FAVORED Team.
        if len(teams_represented) > 1:
            favored_team = state.tie_breaker_team
            if favored_team in teams_represented:
                candidates = teams_represented[favored_team]
                target_team = favored_team
            else:
                # Favored team not tied? Pick first available team.
                target_team = list(teams_represented.keys())[0]
                candidates = teams_represented[target_team]
            
            # If target team has multiple players -> they must choose
            if len(candidates) > 1:
                needs_input = True
            else:
                winner_id = candidates[0]
                # FLIP COIN only if we resolved a Different-Team tie
                state.tie_breaker_team = TeamColor.BLUE if state.tie_breaker_team == TeamColor.RED else TeamColor.RED
                print(f"   [TIE] Coin wins for {favored_team.name}. {winner_id} acts. Coin flipped.")

        # B. If only one team -> they must choose who goes next
        else:
            target_team = list(teams_represented.keys())[0]
            candidates = teams_represented[target_team]
            if len(candidates) > 1:
                needs_input = True
            else:
                winner_id = candidates[0]

        # 2. Process Input if needed
        if needs_input:
            if self.pending_input:
                winner_id = self.pending_input.get("selected_hero_id")
                print(f"   [TIE] Team {target_team.name} chose {winner_id} to act first.")
                # We do NOT flip coin here if it was a same-team choice? 
                # Actually, rules say flip after one favored player resolves.
                # If Red was favored, and Red chose A over D, Red acted. Flip coin.
                if len(teams_represented) > 1:
                     state.tie_breaker_team = TeamColor.BLUE if state.tie_breaker_team == TeamColor.RED else TeamColor.RED
            else:
                return StepResult(
                    requires_input=True,
                    input_request={
                        "type": "CHOOSE_ACTOR",
                        "prompt": f"Team {target_team.name}, choose who acts first between {candidates}.",
                        "player_ids": candidates,
                        "team": target_team
                    }
                )

        # 3. We have a winner! 
        # Identify the winner's card
        winner_hero = state.get_hero(winner_id)
        winner_card = winner_hero.current_turn_card if winner_hero else None
        
        # CRITICAL: Remove winner from unresolved pool so they don't act again immediately
        if winner_id in state.unresolved_hero_ids:
            state.unresolved_hero_ids.remove(winner_id)
            
        state.current_actor_id = winner_id
            
        new_steps = []
        # A. Winner Action
        new_steps.append(LogMessageStep(message=f"Resolving card for {winner_id}"))
        
        # TODO: Here we would push the actual steps from the card.
        # For now, we at least push the Finalize step.
        new_steps.append(FinalizeHeroTurnStep(hero_id=winner_id))

        return StepResult(is_finished=True, new_steps=new_steps)

class AttackSequenceStep(GameStep):
    """
    Composite Step.
    Expands into: Select Target -> Reaction Window -> Resolve Combat.
    """
    type: str = "attack_sequence"
    damage: int
    range_val: int
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        print(f"   [MACRO] Expanding Attack Sequence (Dmg: {self.damage}, Rng: {self.range_val})")
        
        # Desired Execution Order: Select -> Reaction -> Combat
        new_steps = [
            SelectTargetStep(prompt="Select Attack Target", output_key="victim_id"),
            ReactionWindowStep(target_player_key="victim_id"),
            ResolveCombatStep(damage=self.damage, target_key="victim_id")
        ]
        
        return StepResult(is_finished=True, new_steps=new_steps)

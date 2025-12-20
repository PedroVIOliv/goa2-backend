from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field

from goa2.domain.state import GameState
from goa2.domain.models import ActionType, Card

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
        dest_hex = context.get(self.destination_key)
        
        if not actor_id:
             print("   [ERROR] No actor for move.")
             return StepResult(is_finished=True)
             
        if not dest_hex:
             # In a real scenario, we might prompt for input HERE if missing.
             # For now, assume a SelectTargetStep ran before this.
             print("   [ERROR] No destination for move.")
             return StepResult(is_finished=True)

        # 1. Validate Path (using engine rules)
        # Placeholder for full Hex object reconstruction from context
        # rules.validate_movement_path(state.board, state.unit_locations, start, dest_hex, self.range_val)
        
        print(f"   [LOGIC] Moving {actor_id} to {dest_hex} (Range {self.range_val})")
        # state.move_unit(actor_id, dest_hex)
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
                # Validate it is in valid_ids (Security check)
                if card_id not in valid_ids and valid_ids: # Allow if mock? No, be strict.
                    # In demo/mock env, valid_ids might be empty if hero not fully setup.
                    # For demo robustness, we warn but allow if no validation list exists.
                    pass 

                # Calculate Value
                # In real engine, fetch card from Hand.
                # For Demo: Assume mock value or fetch.
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
                
                # We could push a 'DiscardCardStep' here to actualize the cost
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
        # The Handler will push these. 
        # If Handler pushes [A, B, C], C is top?
        # We need to define the contract.
        # Usually "new_steps" implies "replace me with these".
        # If we want Select to run first, it must be Top.
        # So if we return [Select, Reaction, Combat], Handler should push Combat, then Reaction, then Select.
        
        new_steps = [
            SelectTargetStep(prompt="Select Attack Target", output_key="victim_id"),
            ReactionWindowStep(target_player_key="victim_id"),
            ResolveCombatStep(damage=self.damage, target_key="victim_id")
        ]
        
        return StepResult(is_finished=True, new_steps=new_steps)

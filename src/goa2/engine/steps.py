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


from goa2.engine.filters import FilterCondition
from goa2.domain.types import UnitID

# ... (Previous imports) ...

class SelectStep(GameStep):
    """
    Unified selection step using the Filter System.
    Replaces SelectTargetStep and SelectHexStep.
    """
    type: str = "select_step"
    target_type: str # "UNIT" or "HEX"
    prompt: str
    output_key: str = "selection"
    filters: List[FilterCondition] = Field(default_factory=list)
    auto_select_if_one: bool = False
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        actor_id = state.current_actor_id
        
        # 1. Gather Candidates
        candidates = []
        if self.target_type == "UNIT":
            # Collect all Unit IDs on board
            candidates = list(state.unit_locations.keys())
        elif self.target_type == "HEX":
            # Collect all Hexes on board
            # Optimization: If there is a RangeFilter, use it to narrow search area
            # For now, simplistic iteration over all tiles
            candidates = list(state.board.tiles.keys())
            
        # 2. Apply Filters
        valid_candidates = []
        for c in candidates:
            is_valid = True
            for f in self.filters:
                if not f.apply(c, state, context):
                    is_valid = False
                    break
            if is_valid:
                valid_candidates.append(c)

        if not valid_candidates:
            print(f"   [LOGIC] No valid candidates for selection '{self.prompt}'")
            # If mandatory, this might be an issue. For now, we finish.
            # Ideally, we might pass a 'None' or handle 'If Able' here.
            return StepResult(is_finished=True)

        # 3. Auto-Select optimization
        if self.auto_select_if_one and len(valid_candidates) == 1:
            choice = valid_candidates[0]
            context[self.output_key] = choice
            print(f"   [AUTO] Only one valid option: {choice}. Selected automatically.")
            return StepResult(is_finished=True)

        # 4. Check Input
        if self.pending_input:
            selection = self.pending_input.get("selection")
            
            # Type Conversion for Hex
            if self.target_type == "HEX" and isinstance(selection, dict):
                 selection = Hex(**selection)
            
            if selection in valid_candidates:
                context[self.output_key] = selection
                print(f"   [INPUT] Player {actor_id} selected {selection}")
                return StepResult(is_finished=True)
            else:
                 # Invalid choice, re-request
                 pass

        # 5. Request Input
        # For Hexes, we might want to serialize them? Pydantic handles Hex serialization.
        return StepResult(
            requires_input=True,
            input_request={
                "type": f"SELECT_{self.target_type}",
                "prompt": self.prompt,
                "player_id": actor_id,
                "valid_options": valid_candidates 
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

class FindNextActorStep(GameStep):
    """
    Triggers the Phase engine to identify the next active player.
    Used to chain turns together.
    """
    type: str = "find_next_actor"

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        # Import internally to avoid circular dependency (steps <-> phases)
        from goa2.engine.phases import resolve_next_action
        print("   [LOOP] Finding next actor...")
        resolve_next_action(state)
        return StepResult(is_finished=True)

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
        
        return StepResult(is_finished=True, new_steps=[FindNextActorStep()])

class PlaceUnitStep(GameStep):
    """
    Moves a unit to a target hex directly.
    No pathfinding validation. Used for respawns, swaps, and forced placements.
    """
    type: str = "place_unit"
    unit_id: Optional[str] = None # If None, uses current_actor
    destination_key: str = "target_hex" # Where to look in context
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        actor_id = self.unit_id if self.unit_id else state.current_actor_id
        dest_val = context.get(self.destination_key)
        
        if not actor_id:
             print("   [ERROR] No actor for place.")
             return StepResult(is_finished=True)
             
        if not dest_val:
             print("   [ERROR] No destination for place.")
             return StepResult(is_finished=True)

        # Ensure destination is a Hex object
        if isinstance(dest_val, dict):
            dest_hex = Hex(**dest_val)
        else:
            dest_hex = dest_val # Assume it is already a Hex

        # Validation: Check if Tile is Occupied
        tile = state.board.get_tile(dest_hex)
        if tile and tile.is_occupied:
             print(f"   [ERROR] Cannot place {actor_id} at {dest_hex}. Tile is occupied.")
             return StepResult(is_finished=True)

        print(f"   [LOGIC] Placing {actor_id} at {dest_hex}")
        state.move_unit(actor_id, dest_hex)
        return StepResult(is_finished=True)

class SwapUnitsStep(GameStep):
    """
    Swaps the locations of two units.
    Does not count as movement.
    """
    type: str = "swap_units"
    unit_a_id: str
    unit_b_id: str
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        loc_a = state.unit_locations.get(self.unit_a_id)
        loc_b = state.unit_locations.get(self.unit_b_id)
        
        if not loc_a or not loc_b:
            print(f"   [ERROR] Cannot swap {self.unit_a_id} and {self.unit_b_id}. Missing location(s).")
            return StepResult(is_finished=True)

        print(f"   [LOGIC] Swapping {self.unit_a_id} at {loc_a} with {self.unit_b_id} at {loc_b}")
        
        # Move A to B's spot, then B to A's spot.
        # move_unit handles both unit_locations and board tiles.
        state.move_unit(self.unit_a_id, loc_b)
        state.move_unit(self.unit_b_id, loc_a)
        
        return StepResult(is_finished=True)

class PushUnitStep(GameStep):
    """
    Pushes a unit away from a source location.
    Stops at obstacles or board edge.
    """
    type: str = "push_unit"
    target_id: str
    source_hex: Optional[Hex] = None # If None, uses current actor's location
    distance: int = 1
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        target_loc = state.unit_locations.get(self.target_id)
        if not target_loc:
            return StepResult(is_finished=True)
            
        src_hex = self.source_hex
        if not src_hex:
            if state.current_actor_id:
                src_hex = state.unit_locations.get(state.current_actor_id)
        
        if not src_hex:
            print("   [ERROR] No source for push.")
            return StepResult(is_finished=True)
            
        if src_hex == target_loc:
            print("   [ERROR] Cannot push from same hex.")
            return StepResult(is_finished=True)

        # 1. Determine Direction
        direction_idx = src_hex.direction_to(target_loc)
        if direction_idx is None:
            # Fallback: Just pick a direction? No, GoA2 pushes are vector-based.
            # If not in straight line, we can't push "away" cleanly in a hex grid.
            print(f"   [ERROR] Push target {self.target_id} is not in a straight line from source.")
            return StepResult(is_finished=True)

        # 2. Iterative Move
        current_loc = target_loc
        actual_dist = 0
        for _ in range(self.distance):
            next_hex = current_loc.neighbor(direction_idx)
            
            # Check Board Boundaries
            if next_hex not in state.board.tiles:
                print(f"   [PUSH] {self.target_id} hit board edge at {current_loc}")
                break
                
            # Check Obstacles (Static and Occupants)
            tile = state.board.get_tile(next_hex)
            if tile and tile.is_obstacle:
                print(f"   [PUSH] {self.target_id} hit obstacle at {next_hex}")
                break
                
            current_loc = next_hex
            actual_dist += 1
            
        if actual_dist > 0:
            print(f"   [LOGIC] Pushing {self.target_id} from {target_loc} to {current_loc} ({actual_dist} spaces)")
            state.move_unit(self.target_id, current_loc)
        else:
            print(f"   [LOGIC] Push had no effect for {self.target_id}")

        return StepResult(is_finished=True)

class RespawnHeroStep(GameStep):
    """
    Handles the Hero Respawn choice.
    If Hero is defeated, requests player input: Respawn or Pass.
    """
    type: str = "respawn_hero"
    hero_id: str
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        hero = state.get_hero(self.hero_id)
        if not hero:
             return StepResult(is_finished=True)
             
        # Only respawn if not on board
        if self.hero_id in state.unit_locations:
            return StepResult(is_finished=True)

        # 1. Check Input
        if self.pending_input:
            choice = self.pending_input.get("choice")
            if choice == "PASS":
                print(f"   [RESPAWN] {self.hero_id} chose NOT to respawn.")
                context["skipped_respawn"] = True
                return StepResult(is_finished=True)
            
            selected_hex_dict = self.pending_input.get("spawn_hex")
            if selected_hex_dict:
                selected_hex = Hex(**selected_hex_dict)
                print(f"   [RESPAWN] {self.hero_id} respawning at {selected_hex}")
                state.move_unit(self.hero_id, selected_hex)
                return StepResult(is_finished=True)

        # 2. Find valid spawn points (Empty Hero Spawn Point for Team)
        valid_hexes = []
        for h, tile in state.board.tiles.items():
            if (tile.spawn_point and 
                tile.spawn_point.is_hero_spawn and 
                tile.spawn_point.team == hero.team):
                if not tile.is_occupied:
                    valid_hexes.append(h)

        if not valid_hexes:
            print(f"   [RESPAWN] No empty spawn points for {self.hero_id}!")
            return StepResult(is_finished=True)

        # 3. Request Input
        return StepResult(
            requires_input=True,
            input_request={
                "type": "CHOOSE_RESPAWN",
                "prompt": f"Hero {self.hero_id} is defeated. Respawn at an empty spawn point?",
                "player_id": self.hero_id,
                "options": ["RESPAWN", "PASS"],
                "valid_hexes": valid_hexes
            }
        )

class RespawnMinionStep(GameStep):
    """
    Respawns a minion of a certain type/team in the active zone.
    """
    type: str = "respawn_minion"
    team: TeamColor
    minion_type: Any # MinionType enum

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        zone_id = state.active_zone_id
        if not zone_id: return StepResult(is_finished=True)
        
        zone = state.board.zones.get(zone_id)
        if not zone: return StepResult(is_finished=True)
        
        # Count existing minions and spawn points in zone
        team_obj = state.teams.get(self.team)
        existing_count = 0
        for m in team_obj.minions:
            loc = state.unit_locations.get(m.id)
            if loc and loc in zone.hexes and m.type == self.minion_type:
                existing_count += 1
                
        spawn_count = 0
        for h in zone.hexes:
            tile = state.board.get_tile(h)
            if tile and tile.spawn_point and tile.spawn_point.is_minion_spawn:
                if (tile.spawn_point.team == self.team and 
                    tile.spawn_point.minion_type == self.minion_type):
                    spawn_count += 1
                        
        if existing_count >= spawn_count:
            print(f"   [RESPAWN] Cannot respawn {self.minion_type} for {self.team}: Max count reached.")
            return StepResult(is_finished=True)
            
        target_minion = next((m for m in team_obj.minions 
                             if m.type == self.minion_type and m.id not in state.unit_locations), None)
        if not target_minion:
            print(f"   [RESPAWN] No available {self.minion_type} in supply.")
            return StepResult(is_finished=True)
            
        # Select target hex
        if self.pending_input:
            selected_hex_dict = self.pending_input.get("spawn_hex")
            if selected_hex_dict:
                selected_hex = Hex(**selected_hex_dict)
                
                # Validation: Check Occupancy
                tile = state.board.get_tile(selected_hex)
                if tile and tile.is_occupied:
                    print(f"   [ERROR] Cannot respawn {self.minion_type} at {selected_hex}. Occupied.")
                    return StepResult(is_finished=True)

                state.move_unit(target_minion.id, selected_hex)
                print(f"   [RESPAWN] Respawned {target_minion.id} at {selected_hex}")
                return StepResult(is_finished=True)
        
        valid_spaces = [h for h in zone.hexes if not state.board.get_tile(h).is_occupied]
        if not valid_spaces:
            return StepResult(is_finished=True)

        return StepResult(
            requires_input=True,
            input_request={
                "type": "SELECT_HEX",
                "prompt": f"Select space to respawn {self.minion_type}.",
                "player_id": state.current_actor_id,
                "valid_hexes": valid_spaces
            }
        )

class ResolveCardTextStep(GameStep):
    """
    Placeholder for executing the specific Python script/logic associated with a card's text.
    In a full implementation, this would look up a registry using `card.effect_id` 
    and execute the specific function/class for that card.
    """
    type: str = "resolve_card_text"
    card_id: str
    hero_id: str
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        hero = state.get_hero(self.hero_id)
        if not hero or not hero.current_turn_card:
            return StepResult(is_finished=True)
            
        card = hero.current_turn_card
        print(f"   [SCRIPT] Executing custom logic for '{card.name}' (Effect: {card.effect_id}):")
        print(f"            > \"{card.effect_text}\"")
        
        # TODO: Implement the Effect Registry lookup here.
        # For now, if it's a simple Primary Attack/Move, we can mimic it for the demo,
        # but the User requested we strictly treat it as "custom script".
        
        return StepResult(is_finished=True)

class ResolveCardStep(GameStep):
    """
    Analyzes the active card and prompts the user to choose an Action.
    Spawns the appropriate logic steps based on the choice.
    """
    type: str = "resolve_card"
    hero_id: str

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        hero = state.get_hero(self.hero_id)
        if not hero or not hero.current_turn_card:
            return StepResult(is_finished=True)
            
        card = hero.current_turn_card
        
        # 1. Gather Options
        options = []
        
        # Primary
        if card.primary_action:
            options.append({
                "id": "PRIMARY",
                "type": card.primary_action, 
                "value": card.primary_action_value,
                "text": f"Primary: {card.primary_action.name} ({card.primary_action_value or '-'})"
            })
            
        # Secondaries
        for action_type, val in card.secondary_actions.items():
             options.append({
                "id": f"SEC_{action_type.name}",
                "type": action_type,
                "value": val,
                "text": f"Secondary: {action_type.name} ({val})"
            })
            
        # 2. Process Input
        if self.pending_input:
            choice_id = self.pending_input.get("choice_id")
            selected_opt = next((o for o in options if o["id"] == choice_id), None)
            
            if selected_opt:
                act_type = selected_opt["type"]
                val = selected_opt["value"]
                is_primary = (choice_id == "PRIMARY")
                
                print(f"   [CHOICE] Player selected {choice_id} ({act_type.name})")
                
                new_steps = []
                
                if is_primary:
                    # User Mandate: Primary actions apply custom script.
                    new_steps.append(ResolveCardTextStep(
                        card_id=card.id, 
                        hero_id=self.hero_id
                    ))
                else:
                    # Secondary: Standard Primitives
                    if act_type == ActionType.MOVEMENT:
                        new_steps.append(MoveUnitStep(unit_id=self.hero_id, range_val=val))
                        
                    elif act_type == ActionType.FAST_TRAVEL:
                        # Replaces Movement, usually standard Move logic + condition check.
                        new_steps.append(MoveUnitStep(unit_id=self.hero_id, range_val=val)) 
                        
                    elif act_type == ActionType.ATTACK:
                        rng = card.range_value if card.range_value is not None else 1
                        new_steps.append(AttackSequenceStep(damage=val, range_val=rng))
                        
                    elif act_type == ActionType.CLEAR:
                        new_steps.append(LogMessageStep(message=f"{self.hero_id} clears tokens."))
                        
                    elif act_type == ActionType.HOLD:
                        new_steps.append(LogMessageStep(message=f"{self.hero_id} Holds."))
                        
                    elif act_type == ActionType.DEFENSE:
                        # Should not happen as action, but valid in enum
                        new_steps.append(LogMessageStep(message=f"{self.hero_id} Defends (Active)."))

                return StepResult(is_finished=True, new_steps=new_steps)

        # 3. Request Input
        return StepResult(
            requires_input=True,
            input_request={
                "type": "CHOOSE_ACTION",
                "prompt": f"Choose action for card {card.name}",
                "player_id": self.hero_id,
                "options": options
            }
        )

class EndPhaseStep(GameStep):
    """
    Handles the End of Round logic:
    1. Minion Battle
    2. Retrieve Cards
    3. Clear Tokens
    4. Level Up
    5. Reset for next Round
    """
    type: str = "end_phase"

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        print("   [ROUND END] Processing End Phase...")
        
        # TODO: Implement Minion Battle
        # TODO: Implement Card Retrieval
        # TODO: Implement Level Up
        
        # Reset Round
        state.round += 1
        state.turn = 1
        
        # Transition back to Planning for new round
        # Import locally to avoid circular
        from goa2.domain.models import GamePhase
        state.phase = GamePhase.PLANNING
        print(f"   [ROUND START] Round {state.round}, Turn {state.turn}")
        
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
        
        # Import filters locally to avoid circular top-level imports if any issues arise, 
        # though we already imported FilterCondition at top.
        from goa2.engine.filters import RangeFilter, TeamFilter
        
        # Desired Execution Order: Select -> Reaction -> Combat
        new_steps = [
            SelectStep(
                target_type="UNIT",
                prompt="Select Attack Target",
                output_key="victim_id",
                filters=[
                    RangeFilter(max_range=self.range_val),
                    TeamFilter(relation="ENEMY")
                ]
            ),
            ReactionWindowStep(target_player_key="victim_id"),
            ResolveCombatStep(damage=self.damage, target_key="victim_id")
        ]
        
        return StepResult(is_finished=True, new_steps=new_steps)

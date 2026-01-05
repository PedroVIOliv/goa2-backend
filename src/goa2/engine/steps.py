from __future__ import annotations
from abc import ABC
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel, Field

from goa2.domain.state import GameState
from goa2.domain.models import (
    ActionType, TeamColor, CardTier, CardColor, 
    CardState, GamePhase
)
from goa2.domain.models.modifier import DurationType
from goa2.domain.hex import Hex
from goa2.engine import rules # For validation

from goa2.domain.models.enums import StatType
from goa2.domain.models.effect import EffectType, EffectScope

# -----------------------------------------------------------------------------
# Base Classes
# -----------------------------------------------------------------------------

class StepResult(BaseModel):
    """Result of a step execution."""
    is_finished: bool = True
    requires_input: bool = False
    input_request: Optional[Dict[str, Any]] = None
    new_steps: List['GameStep'] = Field(default_factory=list) # Steps to spawn
    abort_action: bool = False  # If True, abort remaining steps in current action

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
    
    # Mandatory step flag: Per GoA2 rules, mandatory steps that fail abort the action.
    # Optional steps ("you may", "up to", "if able") set this to False.
    is_mandatory: bool = True

    # Conditional Execution: If set, this step only runs if 'active_if_key' exists in context.
    active_if_key: Optional[str] = None

    def should_skip(self, context: Dict[str, Any]) -> bool:
        """Checks if the step should be skipped based on active_if_key."""
        if self.active_if_key:
            val = context.get(self.active_if_key)
            # Skip if key is missing or None (falsy is tricky, but usually checking existence/non-None is safer)
            if val is None: 
                return True
        return False

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

class CreateModifierStep(GameStep):
    """Creates a Modifier in the game state."""
    type: str = "create_modifier"

    target_id: Optional[str] = None
    target_key: Optional[str] = None  # Read from context

    stat_type: Optional[StatType] = None
    value_mod: int = 0
    status_tag: Optional[str] = None
    duration: DurationType = DurationType.THIS_TURN

    # Card linkage (for card-based effects)
    source_card_id: Optional[str] = None  # Explicit card ID
    use_context_card: bool = True         # If True, use "current_card_id" from context

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        target = self.target_id or context.get(self.target_key)
        if not target:
            # If target missing, it's an error in logic or optional step skipped
            # For now, just log and finish
            print("   [SKIP] No target for CreateModifierStep")
            return StepResult(is_finished=True)

        # Resolve source card ID
        card_id = self.source_card_id
        if card_id is None and self.use_context_card:
            card_id = context.get("current_card_id")

        from goa2.engine.effect_manager import EffectManager
        EffectManager.create_modifier(
            state=state,
            source_id=state.current_actor_id,
            source_card_id=card_id,  # Link to card
            target_id=target,
            stat_type=self.stat_type,
            value_mod=self.value_mod,
            status_tag=self.status_tag,
            duration=self.duration
        )
        
        desc = f"{self.stat_type.name} {self.value_mod}" if self.stat_type else self.status_tag
        print(f"   [EFFECT] Applied {desc} to {target} (Duration: {self.duration.name})")

        return StepResult(is_finished=True)

class CreateEffectStep(GameStep):
    """Creates a spatial ActiveEffect in the game state."""
    type: str = "create_effect"

    effect_type: EffectType
    scope: EffectScope
    duration: DurationType = DurationType.THIS_TURN

    restrictions: List[ActionType] = Field(default_factory=list)
    stat_type: Optional[StatType] = None
    stat_value: int = 0
    max_value: Optional[int] = None

    blocks_enemy_actors: bool = True
    blocks_friendly_actors: bool = False
    blocks_self: bool = False

    # Card linkage (for card-based effects)
    source_card_id: Optional[str] = None  # Explicit card ID
    use_context_card: bool = True         # If True, use "current_card_id" from context

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        # Resolve source card ID
        card_id = self.source_card_id
        if card_id is None and self.use_context_card:
            card_id = context.get("current_card_id")

        from goa2.engine.effect_manager import EffectManager
        EffectManager.create_effect(
            state=state,
            source_id=state.current_actor_id,
            source_card_id=card_id,  # Link to card
            effect_type=self.effect_type,
            scope=self.scope,
            duration=self.duration,
            restrictions=self.restrictions,
            stat_type=self.stat_type,
            stat_value=self.stat_value,
            max_value=self.max_value,
            blocks_enemy_actors=self.blocks_enemy_actors,
            blocks_friendly_actors=self.blocks_friendly_actors,
            blocks_self=self.blocks_self
        )
        
        print(f"   [EFFECT] Created {self.effect_type.value} from {state.current_actor_id}")

        return StepResult(is_finished=True)

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
        if self.should_skip(context):
            print(f"   [SKIP] Conditional Step '{self.prompt}' skipped (Key '{self.active_if_key}' missing).")
            return StepResult(is_finished=True)

        actor_id = state.current_actor_id
        
        candidates = []
        if self.target_type == "UNIT":
            # Filter entity_locations for things that are actually Units
            all_entities = list(state.entity_locations.keys())
            candidates = [eid for eid in all_entities if state.get_unit(UnitID(str(eid)))]
        elif self.target_type == "HEX":
            # Optimization: If there is a RangeFilter, use it to narrow search area
            # For now, simplistic iteration over all tiles
            candidates = list(state.board.tiles.keys())
            
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
            if self.is_mandatory:
                print(f"   [ABORT] Mandatory selection '{self.prompt}' failed. No candidates.")
                return StepResult(is_finished=True, abort_action=True)
            else:
                print(f"   [SKIP] Optional selection '{self.prompt}' skipped. No candidates.")
                return StepResult(is_finished=True)

        if self.auto_select_if_one and len(valid_candidates) == 1 and self.is_mandatory:
            choice = valid_candidates[0]
            context[self.output_key] = choice
            print(f"   [AUTO] Only one valid option: {choice}. Selected automatically.")
            return StepResult(is_finished=True)

        if self.pending_input:
            selection = self.pending_input.get("selection")
            
            if selection == "SKIP" and not self.is_mandatory:
                print("   [SKIP] Player chose to skip optional selection.")
                return StepResult(is_finished=True)

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

        return StepResult(
            requires_input=True,
            input_request={
                "type": f"SELECT_{self.target_type}",
                "prompt": self.prompt,
                "player_id": actor_id,
                "valid_options": valid_candidates,
                "can_skip": not self.is_mandatory
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

        if isinstance(dest_val, dict):
            dest_hex = Hex(**dest_val)
        else:
            dest_hex = dest_val # Assume it is already a Hex

        # Validation: Check Effects/Constraints
        validation = state.validator.can_move(state, actor_id, self.range_val, context)
        if not validation.allowed:
            print(f"   [BLOCKED] MoveUnitStep: {validation.reason}")
            if self.is_mandatory:
                return StepResult(is_finished=True, abort_action=True)
            return StepResult(is_finished=True)

        start_hex = state.entity_locations.get(actor_id)
        if not start_hex:
            print(f"   [ERROR] Unit {actor_id} has no location on board.")
            return StepResult(is_finished=True)

        is_valid = rules.validate_movement_path(
            board=state.board,
            start=start_hex,
            end=dest_hex,
            max_steps=self.range_val
        )
        
        if not is_valid:
            # NOTE: This should rarely happen if SelectStep correctly filtered movement options.
            # Invalid path is an ERROR (wrong destination chosen), not an abort trigger.
            # Abort only happens at SelectStep when no valid options exist at all.
            print(f"   [ERROR] Invalid move for {actor_id} to {dest_hex}. Path blocked or out of range.")
            return StepResult(is_finished=True)

        print(f"   [LOGIC] Moving {actor_id} from {start_hex} to {dest_hex} (Range {self.range_val})")
        state.move_unit(actor_id, dest_hex)
        return StepResult(is_finished=True)

class FastTravelStep(GameStep):
    """
    Handles Fast Travel action.
    Rule 6.1:
    - Replaces Movement.
    - Requires Start Zone Empty of Enemies.
    - Requires Dest Zone Empty of Enemies.
    - Dest Zone must be Start Zone or Adjacent.
    - Ignores Card movement value (uses Teleport logic).
    """
    type: str = "fast_travel"
    unit_id: Optional[str] = None
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        # Fast Travel Validation could also be added here (can_perform_action(FAST_TRAVEL))
        # But per instruction, focusing on Move/Push/Swap.
        # Fast Travel is usually secondary/optional so failure -> finish.
        actor_id = self.unit_id if self.unit_id else state.current_actor_id
        if not actor_id: return StepResult(is_finished=True)
        
        unit = state.get_unit(actor_id)
        if not unit: return StepResult(is_finished=True)
        
        current_hex = state.entity_locations.get(actor_id)
        if not current_hex: return StepResult(is_finished=True)
        
        current_zone_id = state.board.get_zone_for_hex(current_hex)
        if not current_zone_id:
            print(f"   [ERROR] Fast Travel failed: {actor_id} is not in a valid zone.")
            return StepResult(is_finished=True)
            
        from goa2.engine.rules import get_safe_zones_for_fast_travel
        safe_zones = get_safe_zones_for_fast_travel(state, unit.team, current_zone_id)
        
        if not safe_zones:
            print("   [FAST TRAVEL] Failed. Start zone not safe or no safe destinations.")
            return StepResult(is_finished=True)
            
        valid_hexes = []
        for z_id in safe_zones:
            zone = state.board.zones.get(z_id)
            if zone:
                for h in zone.hexes:
                    tile = state.board.get_tile(h)
                    if tile and not tile.is_occupied:
                         valid_hexes.append(h)
                         
        if not valid_hexes:
            print("   [FAST TRAVEL] No empty spaces in safe zones.")
            return StepResult(is_finished=True)
            
        if self.pending_input:
            selection = self.pending_input.get("selection")
            if selection:
                target_hex = Hex(**selection)
                if target_hex in valid_hexes:
                    print(f"   [FAST TRAVEL] {actor_id} traveling to {target_hex}")
                    return StepResult(is_finished=True, new_steps=[
                        PlaceUnitStep(unit_id=actor_id, target_hex_arg=target_hex)
                    ])
                    
        if len(valid_hexes) == 1:
            target = valid_hexes[0]
            print(f"   [FAST TRAVEL] Auto-traveling to {target}")
            return StepResult(is_finished=True, new_steps=[
                PlaceUnitStep(unit_id=actor_id, target_hex_arg=target)
            ])

        return StepResult(
            requires_input=True,
            input_request={
                "type": "SELECT_HEX",
                "prompt": f"Select Fast Travel Destination (Safe Zones: {safe_zones})",
                "player_id": actor_id,
                "valid_hexes": valid_hexes
            }
        )


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

        target_hero = state.get_hero(target_id)

        # Optimization: Minions/Non-Heroes cannot react.
        if not target_hero:
            print(f"   [REACTION] Target {target_id} is not a hero. Skipping reaction.")
            context["defense_value"] = 0
            return StepResult(is_finished=True)

        valid_defense_cards = []
        for card in target_hero.hand:
            if (card.primary_action == ActionType.DEFENSE or 
                ActionType.DEFENSE in card.secondary_actions):
                valid_defense_cards.append(card)

        valid_ids = [c.id for c in valid_defense_cards]
        
        if self.pending_input:
            card_id = self.pending_input.get("selected_card_id")
            
            # Case A: PASS
            if card_id == "PASS":
                print(f"   [REACTION] Player {target_id} Passed (No Defense).")
                context["defense_value"] = 0
                return StepResult(is_finished=True)
            
            # Case B: Selected Card
            if card_id:
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

        return StepResult(
            requires_input=True,
            input_request={
                "type": "SELECT_CARD_OR_PASS",
                "prompt": f"Player {target_id}, select a Defense card.",
                "player_id": target_id,
                "options": valid_ids + ["PASS"]
            }
        )

class RemoveUnitStep(GameStep):
    """
    Purely removes a unit from the board.
    Does NOT grant rewards. Used by 'Remove' effects and as a sub-step of Defeat.
    """
    type: str = "remove_unit"
    unit_id: str
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        print(f"   [LOGIC] Removing {self.unit_id} from board.")
        state.remove_unit(self.unit_id)
        return StepResult(is_finished=True)

class DefeatUnitStep(GameStep):
    """
    Processes the defeat of a unit (Combat/Skill Kill):
    1. Awards Gold (Killer + Assists).
    2. Updates Life Counters (if Hero).
    3. Spawns RemoveUnitStep.
    """
    type: str = "defeat_unit"
    victim_id: str
    killer_id: Optional[str] = None

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        victim = state.get_unit(self.victim_id)
        if not victim:
            return StepResult(is_finished=True)

        print(f"   [DEATH] Processing Defeat of {self.victim_id}...")

        killer = state.get_unit(self.killer_id) if self.killer_id else None
        
        if hasattr(victim, 'level'): # Is Hero
            level = getattr(victim, 'level', 1)
            
            
            # Level: (Kill Reward, Assist Reward, Death Penalty)
            rewards_table = {
                1: (1, 1, 1),
                2: (2, 1, 1),
                3: (3, 1, 1),
                4: (4, 2, 2),
                5: (5, 2, 2),
                6: (6, 2, 2),
                7: (7, 3, 3),
                8: (8, 3, 3)
            }
            kill_gold, assist_gold, penalty_counters = rewards_table.get(level, (level, 1, 1))
            
            if killer and hasattr(killer, 'gold'):
                killer.gold += kill_gold
                print(f"   [ECONOMY] Killer {killer.id} gains {kill_gold} Gold.")
            
            if killer and hasattr(killer, 'team'):
                killer_team = state.teams.get(killer.team)
                if killer_team:
                    for ally in killer_team.heroes:
                        if ally.id != killer.id:
                            ally.gold += assist_gold
                            print(f"   [ECONOMY] Assist: {ally.id} gains {assist_gold} Gold.")
                            
            if hasattr(victim, 'team'):
                victim_team = state.teams.get(victim.team)
                if victim_team:
                    victim_team.life_counters = max(0, victim_team.life_counters - penalty_counters)
                    print(f"   [SCORE] Team {victim.team.name} loses {penalty_counters} Life Counter(s). Remaining: {victim_team.life_counters}")
                    
                    if victim_team.life_counters == 0:
                         print(f"   [GAME OVER] Team {victim.team.name} has 0 Life Counters! ANNIHILATION.")
                         winning_team = TeamColor.BLUE if victim.team == TeamColor.RED else TeamColor.RED
                         return StepResult(is_finished=True, new_steps=[
                             RemoveUnitStep(unit_id=self.victim_id),
                             TriggerGameOverStep(winner=winning_team, condition="ANNIHILATION")
                         ])
            
        elif hasattr(victim, 'value'): # Is Minion
            reward = victim.value
            print(f"   [DEATH] Minion Defeated! Killer gains {reward} Gold.")
            if killer and hasattr(killer, 'gold'):
                killer.gold += reward

        # Execution Order: RemoveUnitStep -> CheckLanePushStep
        return StepResult(is_finished=True, new_steps=[
            RemoveUnitStep(unit_id=self.victim_id),
            CheckLanePushStep()
        ])

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
        target_id = context.get(self.target_key)
        if not target_id:
            print("   [COMBAT] No target selected. Combat cancelled.")
            return StepResult(is_finished=True)

        defense_card_val = context.get("defense_value", 0)
        attack_val = self.damage
        actor_id = state.current_actor_id
        
        # Calculate Passive Modifiers
        from goa2.engine.stats import calculate_minion_defense_modifier
        mod_val = calculate_minion_defense_modifier(state, target_id)
        
        total_defense = defense_card_val + mod_val
        
        print(f"   [COMBAT] Attack ({attack_val}) vs Defense ({defense_card_val} Card + {mod_val} Mod = {total_defense})")
        
        if total_defense >= attack_val:
            print(f"   [RESULT] Attack BLOCKED! {target_id} is safe.")
            return StepResult(is_finished=True)
        else:
            print(f"   [RESULT] Attack HITS! {target_id} is DEFEATED!")
            return StepResult(is_finished=True, new_steps=[
                DefeatUnitStep(victim_id=target_id, killer_id=actor_id)
            ])

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
    unit_id: Optional[str] = None # If None, checks unit_key, then current_actor
    unit_key: Optional[str] = None # Look up unit_id in context
    destination_key: str = "target_hex" # Where to look in context
    target_hex_arg: Optional[Hex] = None # Explicit argument
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if self.should_skip(context):
            return StepResult(is_finished=True)

        # Resolve target unit (unit being placed)
        target_unit_id = self.unit_id
        if not target_unit_id and self.unit_key:
            target_unit_id = context.get(self.unit_key)
            
        if not target_unit_id:
             target_unit_id = state.current_actor_id
        
        # Priority: explicit arg -> context
        dest_val = self.target_hex_arg
        if not dest_val:
            dest_val = context.get(self.destination_key)
        
        if not target_unit_id:
             print("   [ERROR] No unit for place.")
             return StepResult(is_finished=True)
             
        if not dest_val:
             print("   [ERROR] No destination for place.")
             return StepResult(is_finished=True)

        if isinstance(dest_val, dict):
            dest_hex = Hex(**dest_val)
        else:
            dest_hex = dest_val # Assume it is already a Hex

        # Validation: Check Occupancy
        tile = state.board.get_tile(dest_hex)
        if tile and tile.is_occupied:
             print(f"   [ERROR] Cannot place {target_unit_id} at {dest_hex}. Tile is occupied.")
             return StepResult(is_finished=True)

        # Validation: Check Effects/Constraints
        # actor_id is the entity CAUSING the placement (current_actor)
        actor_id = state.current_actor_id or target_unit_id
        
        validation = state.validator.can_be_placed(
            state=state,
            unit_id=target_unit_id,
            actor_id=actor_id,
            destination=dest_hex,
            context=context
        )
        
        if not validation.allowed:
            print(f"   [BLOCKED] PlaceUnitStep: {validation.reason}")
            if self.is_mandatory:
                return StepResult(is_finished=True, abort_action=True)
            return StepResult(is_finished=True)

        print(f"   [LOGIC] Placing {target_unit_id} at {dest_hex}")
        state.move_unit(target_unit_id, dest_hex)
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
        loc_a = state.entity_locations.get(self.unit_a_id)
        loc_b = state.entity_locations.get(self.unit_b_id)
        
        if not loc_a or not loc_b:
            print(f"   [ERROR] Cannot swap {self.unit_a_id} and {self.unit_b_id}. Missing location(s).")
            return StepResult(is_finished=True)

        # Validation
        actor = state.current_actor_id
        res_a = state.validator.can_be_swapped(state, self.unit_a_id, actor, context)
        if not res_a.allowed:
             print(f"   [BLOCKED] Swap prevented for {self.unit_a_id}: {res_a.reason}")
             if self.is_mandatory: return StepResult(is_finished=True, abort_action=True)
             return StepResult(is_finished=True)

        res_b = state.validator.can_be_swapped(state, self.unit_b_id, actor, context)
        if not res_b.allowed:
             print(f"   [BLOCKED] Swap prevented for {self.unit_b_id}: {res_b.reason}")
             if self.is_mandatory: return StepResult(is_finished=True, abort_action=True)
             return StepResult(is_finished=True)

        print(f"   [LOGIC] Swapping {self.unit_a_id} at {loc_a} with {self.unit_b_id} at {loc_b}")
        
        # Safer Swap: Lift both, then place both.
        state.remove_entity(self.unit_a_id)
        state.remove_entity(self.unit_b_id)
        
        state.place_entity(self.unit_a_id, loc_b)
        state.place_entity(self.unit_b_id, loc_a)
        
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

        # Validation
        actor = state.current_actor_id
        res = state.validator.can_be_pushed(state, self.target_id, actor, context)
        if not res.allowed:
             print(f"   [BLOCKED] Push prevented for {self.target_id}: {res.reason}")
             if self.is_mandatory: return StepResult(is_finished=True, abort_action=True)
             return StepResult(is_finished=True)

        direction_idx = src_hex.direction_to(target_loc)
        if direction_idx is None:
            print(f"   [ERROR] Push target {self.target_id} is not in a straight line from source.")
            return StepResult(is_finished=True)

        current_loc = target_loc
        actual_dist = 0
        for _ in range(self.distance):
            next_hex = current_loc.neighbor(direction_idx)
            
            if next_hex not in state.board.tiles:
                print(f"   [PUSH] {self.target_id} hit board edge at {current_loc}")
                break
                
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
        
        # Set card ID in context for effect creation
        context["current_card_id"] = card.id
        
        print(f"   [SCRIPT] Executing logic for '{card.name}' (Effect: {card.effect_id})")
        
        from goa2.engine.effects import CardEffectRegistry
        effect = CardEffectRegistry.get(card.effect_id)
        
        if effect:
            new_steps = effect.get_steps(state, hero, card)
            return StepResult(is_finished=True, new_steps=new_steps)
            
        # Fallback to standard primary primitives if no specific script found
        print(f"            > No custom script found. Using standard {card.primary_action.name} logic.")
        new_steps = []
        val = card.primary_action_value
        
        if card.primary_action == ActionType.MOVEMENT:
            new_steps.append(MoveUnitStep(unit_id=self.hero_id, range_val=val))
        elif card.primary_action == ActionType.ATTACK:
            rng = card.range_value if card.range_value is not None else 1
            new_steps.append(AttackSequenceStep(damage=val, range_val=rng))
        elif card.primary_action == ActionType.DEFENSE:
            new_steps.append(LogMessageStep(message=f"{self.hero_id} Defends (Primary)."))
        elif card.primary_action == ActionType.SKILL:
            print(f"            > Skill '{card.name}' has no registered effect!")
            new_steps.append(LogMessageStep(message=f"Skill '{card.name}' did nothing."))
            
        return StepResult(is_finished=True, new_steps=new_steps)

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
        
        options = []
        
        from goa2.engine.rules import get_safe_zones_for_fast_travel
        
        def is_action_available(act_type: ActionType) -> bool:
            if act_type == ActionType.FAST_TRAVEL:
                u_loc = state.unit_locations.get(self.hero_id)
                if not u_loc: return False
                z_id = state.board.get_zone_for_hex(u_loc)
                if not z_id: return False
                
                safe = get_safe_zones_for_fast_travel(state, hero.team, z_id)
                if not safe:
                     return False
            return True

        # Primary
        primary_action = card.current_primary_action
        if primary_action:
            if is_action_available(primary_action):
                options.append({
                    "id": primary_action.name,
                    "type": primary_action, 
                    "value": card.current_primary_action_value,
                    "text": f"Primary: {primary_action.name} ({card.current_primary_action_value or '-'})"
                })
            
        # Secondaries
        for action_type, val in card.current_secondary_actions.items():
            if is_action_available(action_type):
                 options.append({
                    "id": action_type.name,
                    "type": action_type,
                    "value": val,
                    "text": f"Secondary: {action_type.name} ({val})"
                })
            
        if self.pending_input:
            choice_id = self.pending_input.get("choice_id")
            selected_opt = next((o for o in options if o["id"] == choice_id), None)
            
            if selected_opt:
                act_type = selected_opt["type"]
                val = selected_opt["value"]
                # Determine if primary by checking the card itself
                is_primary = (act_type == primary_action)
                
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
                        new_steps.append(FastTravelStep(unit_id=self.hero_id)) 
                        
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

        return StepResult(
            requires_input=True,
            input_request={
                "type": "CHOOSE_ACTION",
                "prompt": f"Choose action for card {card.name}",
                "player_id": self.hero_id,
                "options": options
            }
        )

class ResolveDisplacementStep(GameStep):
    """
    Handles the placement of minions that could not spawn due to occupied tiles.
    Uses BFS to find nearest empty hexes and prompts team if multiple options exist.
    """
    type: str = "resolve_displacement"
    # List of (UnitID, OriginalHex)
    displacements: List[Tuple[str, Hex]] = Field(default_factory=list) 

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if not self.displacements:
            return StepResult(is_finished=True)

        red_units = []
        blue_units = []
        
        for uid, origin in self.displacements:
            unit = state.get_unit(uid)
            if unit:
                if unit.team == TeamColor.RED: red_units.append((uid, origin))
                elif unit.team == TeamColor.BLUE: blue_units.append((uid, origin))
        
        first_group = []
        second_group = []
        
        if state.tie_breaker_team == TeamColor.RED:
            first_group = red_units
            second_group = blue_units
        else:
            first_group = blue_units
            second_group = red_units
            
        active_group = first_group if first_group else second_group
        if not active_group:
             return StepResult(is_finished=True)

        if self.pending_input:
             sel_uid = self.pending_input.get("selected_unit_id")
             if sel_uid:
                 target_tuple = next((u for u in active_group if u[0] == sel_uid), None)
                 if target_tuple:
                     remaining_active = [u for u in active_group if u[0] != sel_uid]
                     remaining = remaining_active + (second_group if active_group is first_group else [])
                     
                     return StepResult(is_finished=True, new_steps=[
                         ResolveDisplacementStep(displacements=[target_tuple]),
                         ResolveDisplacementStep(displacements=remaining)
                     ])

        if len(active_group) > 1:
             options = [u[0] for u in active_group]
             unit_obj = state.get_unit(options[0])
             team = unit_obj.team if unit_obj else TeamColor.RED
             
             delegate_id = "unknown"
             team_obj = state.teams.get(team)
             if team_obj and team_obj.heroes:
                delegate_id = team_obj.heroes[0].id
                
             return StepResult(
                 requires_input=True, 
                 input_request={
                     "type": "SELECT_UNIT", 
                     "prompt": f"Team {team.name}, choose which displaced unit to place first.",
                     "player_id": delegate_id,
                     "valid_options": options
                 }
             )

        uid, origin = active_group[0]
        remaining = active_group[1:] + (second_group if active_group is first_group else [])
        
        from goa2.engine.map_logic import find_nearest_empty_hexes
        candidates = find_nearest_empty_hexes(state, origin, state.active_zone_id)
        
        if not candidates:
            print(f"   [DISPLACE] No empty space found for {uid} in zone!")
            return StepResult(is_finished=True, new_steps=[
                ResolveDisplacementStep(displacements=remaining)
            ])

        if self.pending_input:
            selection = self.pending_input.get("selection")
            if selection:
                target_hex = Hex(**selection)
                if target_hex in candidates:
                     print(f"   [DISPLACE] Team chose {target_hex} for {uid}")
                     return StepResult(is_finished=True, new_steps=[
                        PlaceUnitStep(unit_id=uid, target_hex_arg=target_hex),
                        ResolveDisplacementStep(displacements=remaining)
                     ])
        
        if len(candidates) == 1:
            target = candidates[0]
            print(f"   [DISPLACE] Auto-placing {uid} at {target}")
            return StepResult(is_finished=True, new_steps=[
                PlaceUnitStep(unit_id=uid, target_hex_arg=target),
                ResolveDisplacementStep(displacements=remaining)
            ])
            
        unit_obj = state.get_unit(uid)
        team = unit_obj.team if unit_obj else TeamColor.RED
        
        delegate_id = "unknown"
        team_obj = state.teams.get(team)
        if team_obj and team_obj.heroes:
            delegate_id = team_obj.heroes[0].id

        return StepResult(
            requires_input=True,
            input_request={
                "type": "SELECT_HEX", 
                "prompt": f"Team {team.name}, choose displacement for {unit_obj.name}.",
                "player_id": delegate_id,
                "valid_hexes": candidates,
                "context_unit_id": uid
            }
        )

class LanePushStep(GameStep):
    """
    Executes a Lane Push:
    1. Removes Wave Counter.
    2. Moves Battle Zone.
    3. Wipes Minions in old zone.
    4. Respawns Minions in new zone.
    5. Checks Victory Conditions (Throne or Last Push).
    """
    type: str = "lane_push"
    losing_team: TeamColor

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        from goa2.engine.map_logic import get_push_target_zone_id
        
        print(f"   [PUSH] Lane Push Triggered! Losing Team: {self.losing_team.name}")
        
        state.wave_counter -= 1
        print(f"   [PUSH] Wave Counter removed. Remaining: {state.wave_counter}")
        
        if state.wave_counter <= 0:
            print("   [GAME OVER] Last Push Victory!")
            winning_team = TeamColor.BLUE if self.losing_team == TeamColor.RED else TeamColor.RED
            return StepResult(is_finished=True, new_steps=[
                TriggerGameOverStep(winner=winning_team, condition="LAST_PUSH")
            ])

        next_zone_id, is_game_over = get_push_target_zone_id(state, self.losing_team)
        
        if is_game_over:
            print(f"   [GAME OVER] Lane Push Victory! {self.losing_team.name} Throne reached.")
            winning_team = TeamColor.BLUE if self.losing_team == TeamColor.RED else TeamColor.RED
            return StepResult(is_finished=True, new_steps=[
                TriggerGameOverStep(winner=winning_team, condition="LANE_PUSH")
            ])
            
        if not next_zone_id:
            print("   [ERROR] Could not determine next zone for push.")
            return StepResult(is_finished=True)

        current_zone = state.board.zones.get(state.active_zone_id)
        
        # Per rules: "Remove all Minions from old Battle Zone."
        # Heroes stay? Yes, heroes are displaced only if blocking spawn (handled by respawn logic later).
        # Actually rules say: "Occupied by Unit: Owning Team Places Minion..."
        # But here we just wipe OLD minions.
        
        to_remove = []
        if current_zone:
            for uid, loc in state.unit_locations.items():
                if loc in current_zone.hexes:
                    unit = state.get_unit(uid)
                    if hasattr(unit, 'type') and hasattr(unit, 'value'): # Duck typing Minion
                        to_remove.append(uid)
        
        for uid in to_remove:
            state.remove_unit(uid)
            print(f"   [PUSH] Wiped {uid} from old zone.")

        print(f"   [PUSH] Battle Zone moved: {state.active_zone_id} -> {next_zone_id}")
        state.active_zone_id = next_zone_id
        
        next_zone = state.board.zones.get(next_zone_id)
        pending_displacements = []
        
        if next_zone:
            # We need to spawn minions for BOTH teams at their respective points in the new zone.
            
            for sp in next_zone.spawn_points:
                if sp.is_minion_spawn:
                    team = state.teams.get(sp.team)
                    if team:
                        candidate = next((m for m in team.minions 
                                        if m.type == sp.minion_type 
                                        and m.id not in state.unit_locations), None)
                        
                        if candidate:
                            tile = state.board.get_tile(sp.location)
                            if tile and not tile.is_occupied:
                                state.move_unit(candidate.id, sp.location)
                                print(f"   [PUSH] Spawning {candidate.id} at {sp.location}")
                            else:
                                print(f"   [PUSH] Spawn blocked at {sp.location} (Displacement Queued)")
                                pending_displacements.append((candidate.id, sp.location))
        
        if pending_displacements:
             return StepResult(is_finished=True, new_steps=[
                 ResolveDisplacementStep(displacements=pending_displacements)
             ])

        return StepResult(is_finished=True)

class CheckLanePushStep(GameStep):
    """
    Checks if the active zone meets the condition for a Lane Push (0 minions for one team).
    If so, spawns a LanePushStep.
    """
    type: str = "check_lane_push"

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        from goa2.engine.map_logic import check_lane_push_trigger
        
        losing_team = check_lane_push_trigger(state, state.active_zone_id)
        if losing_team:
            print(f"   [CHECK] Lane Push Condition Met for {losing_team.name}")
            return StepResult(is_finished=True, new_steps=[
                LanePushStep(losing_team=losing_team)
            ])
            
        return StepResult(is_finished=True)

class EndPhaseCleanupStep(GameStep):
    """
    Handles the non-combat cleanup of End Phase:
    Retrieve Cards, Clear Tokens, Level Up, Round Reset.
    """
    type: str = "end_phase_cleanup"

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        print("   [CLEANUP] Processing End Phase Cleanup...")
        from goa2.engine.effect_manager import EffectManager
        
        # Expire THIS_ROUND items
        EffectManager.expire_modifiers(state, DurationType.THIS_ROUND)
        EffectManager.expire_effects(state, DurationType.THIS_ROUND)
        
        # Cleanup stale items (lazy expiration for cards leaving play)
        EffectManager.cleanup_stale_effects(state)

        self._retrieve_cards(state)
        self._clear_tokens(state)
        self._level_up(state)
        
        if state.pending_upgrades:
             print("   [PHASE] Level Up Phase started.")
             return StepResult(is_finished=True, new_steps=[ResolveUpgradesStep()])
        
        state.round += 1
        state.turn = 1
        state.phase = GamePhase.PLANNING
        print(f"   [ROUND START] Round {state.round}, Turn {state.turn}")
        
        return StepResult(is_finished=True)

    def _retrieve_cards(self, state: GameState):
        for team in state.teams.values():
            for hero in team.heroes:
                hero.retrieve_cards()

    def _clear_tokens(self, state: GameState):
        pass

    def _level_up(self, state: GameState):
        """
        Calculates gold spending and level increments.
        Rule 3.1: Costs follow cumulative table. Mandatory purchase.
        """
        LEVEL_COSTS = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7}
        any_level_ups = False
        
        for team in state.teams.values():
            for hero in team.heroes:
                upgrades_this_round = 0
                while hero.level < 8:
                    next_level = hero.level + 1
                    cost = LEVEL_COSTS[next_level]
                    if hero.gold >= cost:
                        hero.gold -= cost
                        hero.level = next_level
                        upgrades_this_round += 1
                        any_level_ups = True
                        print(f"   [LEVEL] {hero.id} reached Level {hero.level}!")
                    else:
                        break
                
                if upgrades_this_round > 0:
                    state.pending_upgrades[hero.id] = upgrades_this_round
                else:
                    # Pity Coin: Players who did not Level Up gain 1 Gold.
                    hero.gold += 1
                    print(f"   [ECONOMY] {hero.id} did not level up. Gains 1 Pity Gold. (Gold: {hero.gold})")
        
        if any_level_ups:
             state.phase = GamePhase.LEVEL_UP

class EndPhaseStep(GameStep):
    """
    Entry point for End Phase.
    Executes Minion Battle, checks for Lane Push, then queues Cleanup.
    """
    type: str = "end_phase"

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        print("   [ROUND END] Processing End Phase (Battle)...")
        
        self._resolve_minion_battle(state)
        
        new_steps = []
        
        from goa2.engine.map_logic import check_lane_push_trigger
        losing_team = check_lane_push_trigger(state, state.active_zone_id)
        if losing_team:
            new_steps.append(LanePushStep(losing_team=losing_team))
            
        new_steps.append(EndPhaseCleanupStep())
        
        return StepResult(is_finished=True, new_steps=new_steps)

    def _resolve_minion_battle(self, state: GameState):
        """
        Compare minion counts in active zone. Loser removes difference.
        Heavy minions must be last to be removed.
        """
        if not state.active_zone_id:
            return

        zone = state.board.zones.get(state.active_zone_id)
        if not zone: return

        red_minions = []
        blue_minions = []
        
        for unit_id, loc in state.unit_locations.items():
            if loc in zone.hexes:
                unit = state.get_unit(unit_id)
                if hasattr(unit, 'type') and hasattr(unit, 'is_heavy'): 
                    if unit.team == TeamColor.RED:
                        red_minions.append(unit)
                    elif unit.team == TeamColor.BLUE:
                        blue_minions.append(unit)
        
        r_count = len(red_minions)
        b_count = len(blue_minions)
        diff = abs(r_count - b_count)
        
        if diff == 0:
            print("   [BATTLE] Minion count tied. No removals.")
            return

        loser_team = TeamColor.RED if r_count < b_count else TeamColor.BLUE
        loser_minions = red_minions if loser_team == TeamColor.RED else blue_minions
        
        print(f"   [BATTLE] {loser_team.name} loses {diff} minion(s).")
        
        loser_minions.sort(key=lambda m: m.is_heavy)
        
        removals = loser_minions[:diff]
        for m in removals:
            print(f"   [BATTLE] Removing {m.id} ({m.type.name})")
            state.remove_unit(m.id)


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
                target_team = list(teams_represented.keys())[0]
                candidates = teams_represented[target_team]
            
            if len(candidates) > 1:
                needs_input = True
            else:
                winner_id = candidates[0]
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

        if needs_input:
            if self.pending_input:
                winner_id = self.pending_input.get("selected_hero_id")
                print(f"   [TIE] Team {target_team.name} chose {winner_id} to act first.")
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

        # We have a winner! 
        winner_hero = state.get_hero(winner_id)
        winner_card = winner_hero.current_turn_card if winner_hero else None
        
        # CRITICAL: Remove winner from unresolved pool so they don't act again immediately
        if winner_id in state.unresolved_hero_ids:
            state.unresolved_hero_ids.remove(winner_id)
            
        state.current_actor_id = winner_id
            
        new_steps = []
        new_steps.append(ResolveCardStep(hero_id=winner_id))
        
        new_steps.append(FinalizeHeroTurnStep(hero_id=winner_id))

        return StepResult(is_finished=True, new_steps=new_steps)

class AttackSequenceStep(GameStep):
    """
    Composite Step.
    Expands into: Select Target -> Reaction Window -> Resolve Combat.
    If target_id_key is provided, assumes target is already selected in context and skips selection.
    """
    type: str = "attack_sequence"
    damage: int
    range_val: int = 1
    target_id_key: Optional[str] = None # Optional: Use existing context key instead of selecting
    
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        print(f"   [MACRO] Expanding Attack Sequence (Dmg: {self.damage}, Rng: {self.range_val})")
        
        from goa2.engine.filters import RangeFilter, TeamFilter, ImmunityFilter
        
        key = self.target_id_key if self.target_id_key else "victim_id"
        
        new_steps = []
        
        # Only spawn selection if we don't have a pre-selected key
        if not self.target_id_key:
            new_steps.append(
                SelectStep(
                    target_type="UNIT",
                    prompt="Select Attack Target",
                    output_key=key,
                    filters=[
                        RangeFilter(max_range=self.range_val),
                        TeamFilter(relation="ENEMY"),
                        ImmunityFilter()
                    ]
                )
            )
            
        new_steps.extend([
            ReactionWindowStep(target_player_key=key),
            ResolveCombatStep(damage=self.damage, target_key=key)
        ])
        
        return StepResult(is_finished=True, new_steps=new_steps)

def apply_hero_upgrade(state: GameState, hero_id: str, chosen_card_id: str):
    """
    Executes the upgrade transition for a hero.
    1. Removes old tier card of same color.
    2. Adds chosen card to hand.
    3. Tucks pair card as item.
    4. Decrements pending count.
    """
    hero = state.get_hero(hero_id)
    if not hero: return

    chosen_card = next((c for c in hero.deck if c.id == chosen_card_id), None)
    if not chosen_card:
        print(f"   [!] Upgrade Error: Chosen card {chosen_card_id} not found in deck.")
        return

    prev_card = None
    if chosen_card.tier != CardTier.IV: 
        for c in hero.hand:
            if c.color == chosen_card.color:
                prev_card = c
                break
    
    pair_card = None
    if chosen_card.tier != CardTier.IV:
        pair_card = next((c for c in hero.deck 
                         if c.color == chosen_card.color 
                         and c.tier == chosen_card.tier 
                         and c.id != chosen_card.id), None)

    if prev_card:
        print(f"   [UPGRADE] Removing {prev_card.id} (Tier {prev_card.tier.name}) from hand.")
        hero.hand.remove(prev_card)
        prev_card.state = CardState.RETIRED

    print(f"   [UPGRADE] Adding {chosen_card.id} (Tier {chosen_card.tier.name}) to hand.")
    chosen_card.state = CardState.HAND
    hero.hand.append(chosen_card)

    if pair_card:
        stat = pair_card.item
        if stat:
            hero.items[stat] = hero.items.get(stat, 0) + 1
            print(f"   [UPGRADE] Tucking {pair_card.id} as Item (+1 {stat.name}).")
        pair_card.state = CardState.ITEM

    if hero_id in state.pending_upgrades:
        state.pending_upgrades[hero_id] -= 1
        if state.pending_upgrades[hero_id] <= 0:
            del state.pending_upgrades[hero_id]

class RoundResetStep(GameStep):
    """Resets round state and transitions to Planning."""
    type: str = "round_reset"
    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        state.round += 1
        state.turn = 1
        state.phase = GamePhase.PLANNING
        print(f"   [ROUND START] Round {state.round}, Turn {state.turn}")
        return StepResult(is_finished=True)

class ResolveUpgradesStep(GameStep):
    """
    Simultaneous Upgrade loop.
    Waits for players to finish their pending upgrades.
    """
    type: str = "resolve_upgrades"

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        if not state.pending_upgrades:
             print("   [PHASE] All upgrades complete.")
             return StepResult(is_finished=True, new_steps=[RoundResetStep()])

        broadcast_data = {}
        for h_id, count in state.pending_upgrades.items():
            options = self._get_upgrade_options(state, h_id)
            broadcast_data[h_id] = {
                "remaining": count,
                "options": options
            }

        return StepResult(
            requires_input=True,
            input_request={
                "type": "UPGRADE_PHASE",
                "players": broadcast_data,
                "prompt": "Mandatory Upgrade Phase"
            }
        )

    def _get_upgrade_options(self, state: GameState, hero_id: str):
        hero = state.get_hero(hero_id)
        if not hero: return []
        non_basic_colors = [CardColor.RED, CardColor.BLUE, CardColor.GREEN]
        hand_non_basics = [c for c in hero.hand if c.color in non_basic_colors]
        if not hand_non_basics: return []
        
        tier_map = {CardTier.I: 1, CardTier.II: 2, CardTier.III: 3}
        min_tier_val = min(tier_map.get(c.tier, 99) for c in hand_non_basics)
        
        if min_tier_val == 3:
             ultimates = [c for c in hero.deck if c.tier == CardTier.IV]
             return [{
                 "type": "ULTIMATE",
                 "cards": [c.id for c in ultimates],
                 "card_details": [c.model_dump() for c in ultimates]
             }]

        eligible_colors = [c.color for c in hand_non_basics if tier_map.get(c.tier) == min_tier_val]
        next_tier_map = {1: CardTier.II, 2: CardTier.III}
        target_tier = next_tier_map.get(min_tier_val)
        if not target_tier: return []
        
        options = []
        for color in eligible_colors:
            pair = [c for c in hero.deck if c.color == color and c.tier == target_tier and c.state == CardState.DECK]
            if len(pair) == 2:
                options.append({
                    "color": color,
                    "tier": target_tier,
                    "pair": [c.id for c in pair],
                    "card_details": [c.model_dump() for c in pair]
                })
        return options

class TriggerGameOverStep(GameStep):
    """
    Executes an immediate Game Over sequence.
    1. Sets winner and condition.
    2. Changes Phase to GAME_OVER.
    3. PURGES execution and input stacks to stop all gameplay.
    """
    type: str = "trigger_game_over"
    winner: TeamColor
    condition: str

    def resolve(self, state: GameState, context: Dict[str, Any]) -> StepResult:
        print(f"   [GAME OVER] Victory for {self.winner.name}! Reason: {self.condition}")
        
        state.winner = self.winner
        state.victory_condition = self.condition
        state.phase = GamePhase.GAME_OVER
        
        # Hard Stop: Clear everything pending
        state.execution_stack.clear()
        state.input_stack.clear()
        
        return StepResult(is_finished=True)
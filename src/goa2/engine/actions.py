from typing import List, Optional, Tuple, Dict, Any
from abc import ABC, abstractmethod
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.models import ActionType, Card, Minion, MinionType, TeamColor, Team, CardState, Marker, CardTier, StatType
from goa2.domain.input import InputRequest, InputRequestType
from goa2.domain.hex import Hex
from goa2.engine.phases import GamePhase, ResolutionStep
from goa2.domain.types import HeroID, CardID, UnitID, BoardEntityID
from goa2.engine.rules import validate_movement_path, validate_attack_target
from goa2.engine.defeat import defeat_unit
from goa2.engine.combat import calculate_attack_power, calculate_defense_power, resolve_combat
from goa2.engine.effects import EffectRegistry, EffectContext, Effect
import uuid

def is_silenced(unit) -> bool:
    if not unit: return False
    # Check markers
    if hasattr(unit, 'markers'):
        return any(m.name == "SILENCE" for m in unit.markers)
    return False

class Command(ABC):
    """
    Base class for all commands in the game engine.
    """
    def execute(self, state: GameState) -> GameState:
        raise NotImplementedError

class PlayCardCommand(Command):
    """
    Planning Phase: A player commits a card from their Hand.
    """
    def __init__(self, hero_id: HeroID, card_id: CardID):
        self.hero_id = hero_id
        self.card_id = card_id

    def execute(self, state: GameState) -> GameState:
        # Validation 1: Phase
        if state.phase != GamePhase.PLANNING:
            raise ValueError(f"Cannot play card in phase {state.phase.name}")

        # Find Hero
        hero = state.get_hero(self.hero_id)
        if not hero:
            raise ValueError(f"Hero {self.hero_id} not found")

        # Validation 2: Card in Hand
        card_to_play: Optional[Card] = None
        card_index: int = -1
        
        for i, c in enumerate(hero.hand):
            if c.id == self.card_id:
                card_to_play = c
                card_index = i
                break
        
        if not card_to_play:
             raise ValueError(f"Card {self.card_id} not found in Hero {self.hero_id}'s hand")
             
        # Validation 3: Already Played?
        if self.hero_id in state.pending_inputs:
             raise ValueError(f"Hero {self.hero_id} has already played a card")

        # Execute: Add to Pending and Remove from Hand
        state.pending_inputs[self.hero_id] = card_to_play
        hero.hand.pop(card_index)
        
        # State Transition -> PLAYED
        card_to_play.state = CardState.PLAYED
        card_to_play.is_facedown = True
        
        return state

class RevealCardsCommand(Command):
    """
    Revelation Phase: Reveal all pending cards and sort them by initiative.
    """
    def execute(self, state: GameState) -> GameState:
        if state.phase != GamePhase.PLANNING:
            raise ValueError("Can only reveal cards in PLANNING phase")
            
        if not state.pending_inputs:
             # Nothing to reveal? Maybe valid if empty turn, but usually not.
             # For MVP allow it.
             pass

        # Move Pending -> Resolution Queue
        # Sort by: 
        # 1. Card Initiative (High is better/First) -> Reverse Sort
        # 2. Tie Breaker (MVP: String ID of Hero to be deterministic)
        
        # Transition State: PLAYED -> UNRESOLVED
        for card in state.pending_inputs.values():
             if card.state == CardState.PLAYED:
                 card.state = CardState.UNRESOLVED
                 # Reveal the card
                 card.is_facedown = False

        # Convert dict items to list of tuples
        items = list(state.pending_inputs.items()) # [(hero_id, card), ...]
        
        # Sort key: Initiative (Descending), HeroID (Descending for stability/determinism or Ascending?)
        # Python sort is stable. Let's strictly reverse the tuple (Init, HeroID).
        # Wait, if tie, we need logic. For now just reverse sort on Initiative.
        items.sort(key=lambda x: (x[1].initiative, x[0]), reverse=True)
        
        state.resolution_queue = items
        state.pending_inputs = {} # Clear buffer
        
        # Transition State
        state.phase = GamePhase.RESOLUTION
        state.resolution_step = ResolutionStep.ACTING # Skipping REVELATION step instant for MVP?
                                                      # Design says "Revelation Phase -> Resolution Phase".
                                                      # Let's set to ACTING to start processing immediately.
        
        if state.resolution_queue:
            state.current_actor_id = state.resolution_queue[0][0]
            
        return state

class ResolveNextCommand(Command):
    """
    Resolution Phase: Process the next card in the queue.
    Pauses to request ACTION_CHOICE from the user.
    """
    def execute(self, state: GameState) -> GameState:
        if state.phase != GamePhase.RESOLUTION:
            raise ValueError("Not in RESOLUTION phase")
        
        if state.input_stack:
            # Re-entrant safety: if waiting, do nothing (or raise)
            active_req = state.input_stack[-1]
            raise ValueError(f"Game is waiting for input: {active_req.request_type}")

        if not state.resolution_queue:
            state.phase = GamePhase.SETUP 
            state.resolution_step = ResolutionStep.NONE
            state.current_actor_id = None
            return state

        # Peek at Current
        hero_id, card = state.resolution_queue[0]
        state.current_actor_id = hero_id
        
        # Check Forced Action (Repeat Logic)
        forced_action = card.metadata.get("forced_action")
        if forced_action:
             print(f"   [Resolve] Forced Action: {forced_action}")
             # Ensure we are not waiting for input (double check safety)
             # Push dummy request? No, ChooseActionCommand expects to pop one.
             # Wait, ChooseActionCommand pops InputRequestType.ACTION_CHOICE.
             # If we skip pushing it, ChooseActionCommand will fail validation "Not waiting for any input".
             # So we MUST push it, and then immediately consume it.
             
             req_id = str(uuid.uuid4())
             req = InputRequest(
                id=req_id,
                player_id=hero_id,
                request_type=InputRequestType.ACTION_CHOICE
             )
             state.input_stack.append(req)
             
             # Immediately Execute
             return ChooseActionCommand(forced_action).execute(state)

        # ALWAYS Wait for Choice first
        req_id = str(uuid.uuid4())
        req = InputRequest(
            id=req_id,
            player_id=hero_id,
            request_type=InputRequestType.ACTION_CHOICE
        )
        state.input_stack.append(req)
        return state

class ChooseActionCommand(Command):
    """
    Player chooses which action to perform (Primary or one of Secondaries like HOLD).
    """
    def __init__(self, action_type: ActionType):
        self.action_type = action_type

    def execute(self, state: GameState) -> GameState:
        if not state.input_stack:
            raise ValueError("Not waiting for any input")
        
        current_req = state.input_stack[-1]
        if current_req.request_type != InputRequestType.ACTION_CHOICE:
            # Allow Resuming/Interruption if generic input handling is enabled for this command wrapper.
            # We skip the "Start Action" validation block and fall through to delegation.
            pass
        else:
            # "Start Action" Logic (Respond to ACTION_CHOICE)
            hero_id, card = state.resolution_queue[0]
            
            # Identify Hero for Item lookups
            hero = state.get_hero(hero_id)
            if not hero: raise ValueError(f"Hero {hero_id} not found")
            
            # Validation: Verify asker matches currrent request
            # (Skip strict ID check for MVP or use current_req.player_id)
            
            # Validation: Is this action available?
            available = False
            if card.primary_action == self.action_type:
                available = True
            elif self.action_type in card.secondary_actions:
                available = True
                
            if not available:
                raise ValueError(f"Action {self.action_type} not available on card {card.id}")
                
            # POP the Choice Request
            state.input_stack.pop()
            
            # Push Next Request based on Type
            if self.action_type == ActionType.ATTACK:
                req_id = str(uuid.uuid4())
                
                ctx_data = {}
                excluded = card.metadata.get("excluded_targets")
                if excluded:
                     ctx_data["excluded_unit_ids"] = excluded
                     
                req = InputRequest(
                    id=req_id,
                    player_id=hero_id,
                    request_type=InputRequestType.SELECT_ENEMY,
                    context=ctx_data
                )
                state.input_stack.append(req)
                return state

            elif self.action_type == ActionType.MOVEMENT:
                # Determine Movement Value
                move_val = 0
                if card.primary_action == ActionType.MOVEMENT:
                    move_val = card.primary_action_value or 2 # Default 2?
                elif ActionType.MOVEMENT in card.secondary_actions:
                    move_val = card.secondary_actions[ActionType.MOVEMENT]
                
                # Apply Item Bonuses
                if hero.items:
                     move_val += hero.items.get(StatType.MOVEMENT, 0)
                
                # Push Request
                req_id = str(uuid.uuid4())
                req = InputRequest(
                    id=req_id,
                    player_id=hero_id,
                    request_type=InputRequestType.MOVEMENT_HEX,
                    context={"max_steps": move_val}
                )
                state.input_stack.append(req)
                return state
                
            elif self.action_type == ActionType.FAST_TRAVEL:
                 req_id = str(uuid.uuid4())
                 req = InputRequest(
                    id=req_id,
                    player_id=hero_id,
                    request_type=InputRequestType.FAST_TRAVEL_DESTINATION
                 )
                 state.input_stack.append(req)
                 return state

            elif self.action_type == ActionType.SKILL:
                 # Trigger Effect Pre-Action
                 effect = None
                 # Check Silence
                 if not is_silenced(hero):
                      effect = EffectRegistry.get(card.effect_id)
                 
                 if effect:
                     ctx = EffectContext(state=state, command=self, actor=hero, card=card)
                     effect.on_pre_action(ctx)
                     
                     if state.input_stack:
                         # Effect requested input. Wait.
                         return state
                     else:
                         # No input needed? Run Post-Action immediately (Instants)
                         effect.on_post_action(ctx)
                         
                         # CLEANUP (Same as Post-Move/Post-Attack)
                         state.resolution_queue.pop(0) # Remove Card
                         card.state = CardState.RESOLVED
                         if state.resolution_queue:
                            state.current_actor_id = state.resolution_queue[0][0]
                         else:
                            state.current_actor_id = None
                            state.phase = GamePhase.SETUP
                            state.resolution_step = ResolutionStep.NONE
                         
                         return state
                 else:
                     # No effect? Just cleanup.
                     state.resolution_queue.pop(0)
                     card.state = CardState.RESOLVED
                     if state.resolution_queue:
                         state.current_actor_id = state.resolution_queue[0][0]
                     else:
                        state.current_actor_id = None
                        state.phase = GamePhase.SETUP
                        state.resolution_step = ResolutionStep.NONE
                     return state

            # For other actions...
            # Fall through to Dispatch Logic (below)

        # Dispatch / Resume Logic
        # We reach here if:
        # 1. We just popped ACTION_CHOICE (but we returned early for most cases above).
        # 2. We were called with non-ACTION_CHOICE (Resuming).
        
        # If we returned above, we won't be here.
        # But wait! If we popped ACTION_CHOICE and pushed SELECT_ENEMY, we returned strict?
        # Yes.
        
        # So this section is ONLY for "Resuming" (Case 2).
        
        if self.action_type == ActionType.ATTACK:
             if current_req.request_type == InputRequestType.SELECT_ENEMY:
                 # Check if we have a persisted target (Resumption)
                 hero_id, card = state.resolution_queue[0]
                 target_id_str = card.metadata.get("target_unit_id")
                 if target_id_str:
                      return AttackCommand(target_unit_id=UnitID(target_id_str)).execute(state)
                 else:
                      # If no persisted target, we can't auto-resume without input processing.
                      # But in Test, input is only on stack.
                      # Ideally, we should parse the input here if it's new?
                      # Or assume AttackCommand handles it if passed None?
                      # AttackCommand constructor requires target_id.
                      # Let's assume for Resumption we MUST have metadata.
                      pass

        elif self.action_type == ActionType.FAST_TRAVEL:
             req_id = str(uuid.uuid4())
             req = InputRequest(
                 id=req_id,
                 player_id=hero_id,
                 request_type=InputRequestType.FAST_TRAVEL_DESTINATION
             )
             state.input_stack.append(req)
             return state
            
        elif self.action_type == ActionType.HOLD:
            # Finish immediately (Pass, but consume card)
            pass 
        
        elif self.action_type in [ActionType.FAST_TRAVEL, ActionType.HOLD, ActionType.CLEAR]:
             # EXPLICIT RULE: These actions NEVER trigger effects.
             pass 
        
        else:
             # For Skills (no extra input needed usually, or handled specifically)
             # --- EFFECT HOOK: Instant Skill ---
            # Rule: Effects only trigger if they match the Primary Action.
            effect = None
            if card.primary_action == ActionType.SKILL:
                 # Identify Hero for Item lookups
                hero_id, card = state.resolution_queue[0]
                hero = state.get_hero(hero_id)
                if not hero: raise ValueError(f"Hero {hero_id} not found")

                if not is_silenced(hero):
                     effect = EffectRegistry.get(card.effect_id) if card.effect_id else None
            # Prepare Context (Preliminary)
            ctx = EffectContext(state=state, command=self, actor=hero, card=card, target=None) if effect else None

            if effect:
                effect.on_pre_action(ctx)
                
            # CHECK if the Effect requested Input (Async Skill)
            # We popped 'ACTION_CHOICE' earlier. If stack is not empty, it means new input is requested.
            if len(state.input_stack) > 0:
                # Suspend Execution. 
                # Do NOT call on_post_action yet.
                # Do NOT pop resolution queue.
                return state
            
            # If no input requested, assume Instant Complete
            if effect:
                effect.on_post_action(ctx)
            
        # Finish Action (Pop and Reset)
        # Shared 'Finish' logic could be refactored, but repeating for now
        # Stack is already popped. Just check if queue done.
        
        completed_hero_id, completed_card = state.resolution_queue.pop(0)
        
        # State Transition -> RESOLVED
        completed_card.state = CardState.RESOLVED
        
        if state.resolution_queue:
            state.current_actor_id = state.resolution_queue[0][0]
        else:
            state.current_actor_id = None
            state.phase = GamePhase.SETUP
            state.resolution_step = ResolutionStep.NONE
            
        return state

class PerformMovementCommand(Command):
    """
    Executes the movement after receiving input (Target Hex).
    """
    def __init__(self, target_hex: Hex):
        self.target_hex = target_hex

    def execute(self, state: GameState) -> GameState:
        if not state.input_stack:
             raise ValueError("Not waiting for input")
             
        current_req = state.input_stack[-1]
        if current_req.request_type != InputRequestType.MOVEMENT_HEX:
            raise ValueError(f"Not waiting for movement input, waiting for {current_req.request_type}")
            
        # Identify Actor
        hero_id, card = state.resolution_queue[0]
        unit_id = UnitID(str(hero_id))
        
        start_hex = state.unit_locations.get(unit_id)
        if not start_hex:
             raise ValueError(f"Hero {hero_id} is not on the board")
             
        # Validate Logic
        max_steps = current_req.context.get("max_steps", 0)
        
        # Standard Movement Logic
        if not validate_movement_path(
            state.board, 
            state.unit_locations, 
            start_hex, 
            self.target_hex, 
            max_steps, 
            ignore_obstacles=False,
            active_zone_id=state.active_zone_id 
        ):
            raise ValueError(f"Invalid movement path to {self.target_hex}")
            
        # Execute Move
        
        unit = state.get_unit(unit_id)

        # --- EFFECT HOOK: Pre-Move ---
        # Rule: Effects only trigger if they match the Primary Action.
        effect = None
        if card.primary_action == ActionType.MOVEMENT:
            if not is_silenced(unit):
                 effect = EffectRegistry.get(card.effect_id) if card.effect_id else None
        eff_ctx = None
        if effect:
            eff_ctx = EffectContext(state=state, command=self, actor=state.get_unit(unit_id), card=card, target=None) # Target is hex, not unit
            effect.on_pre_action(eff_ctx)

        state.move_unit(unit_id, self.target_hex)
        
        # --- EFFECT HOOK: Post-Move ---
        if effect and eff_ctx:
            effect.on_post_action(eff_ctx)
        
        # Cleanup / Finish Action
        state.input_stack.pop() # Remove Input Request
        completed_hero_id, completed_card = state.resolution_queue.pop(0) # Remove Card from Queue
        
        # State Transition -> RESOLVED
        completed_card.state = CardState.RESOLVED
        
        if state.resolution_queue:
            state.current_actor_id = state.resolution_queue[0][0]
        else:
            state.current_actor_id = None
            state.phase = GamePhase.SETUP
            state.resolution_step = ResolutionStep.NONE
            
        return state

class PerformFastTravelCommand(Command):
    """
    Executes Fast Travel (Teleport logic)
    """
    def __init__(self, target_hex: Hex):
        self.target_hex = target_hex

    def execute(self, state: GameState) -> GameState:
        if not state.input_stack:
             raise ValueError("Not waiting for input")
             
        current_req = state.input_stack[-1]
        if current_req.request_type != InputRequestType.FAST_TRAVEL_DESTINATION:
            raise ValueError(f"Not waiting for Fast Travel input, waiting for {current_req.request_type}")
            
        # Identify Actor
        hero_id, card = state.resolution_queue[0]
        unit_id = UnitID(str(hero_id))
        
        start_hex = state.unit_locations.get(unit_id)
        if not start_hex:
             raise ValueError(f"Hero {hero_id} is not on the board")
             
        actor = state.get_unit(unit_id)
        actor_team = actor.team if actor else TeamColor.RED
        
        # FAST TRAVEL RESTRICTIONS (Rule 5.1 updated)
        # 1. StartZone Empty of Enemies
        start_zone_id = state.board.get_zone_for_hex(start_hex)
        from goa2.engine.map_logic import count_enemies
        if start_zone_id and count_enemies(state, start_zone_id, actor_team) > 0:
             raise ValueError("Cannot Fast Travel: Enemies in Start Zone")

        # 2. DestZone Empty of Enemies
        dest_zone_id = state.board.get_zone_for_hex(self.target_hex)
        if dest_zone_id and count_enemies(state, dest_zone_id, actor_team) > 0:
             raise ValueError("Cannot Fast Travel: Enemies in Dest Zone")
        
        # 3. Zone Adjacency (Rule 5.1)
        if start_zone_id and dest_zone_id:
            start_zone = state.board.zones.get(start_zone_id)
            if start_zone_id != dest_zone_id:
                if dest_zone_id not in start_zone.neighbors:
                     raise ValueError("Cannot Fast Travel: Destination not adjacent")
        
        # 3. Target Empty
        if self.target_hex in state.unit_locations.values():
              raise ValueError("Fast Travel target occupied")
        
        if self.target_hex in state.board.tiles:
            if state.board.tiles[self.target_hex].is_obstacle:
                 raise ValueError("Fast Travel target bocked")
                 
        # --- EFFECT HOOK: Pre-FastTravel ---
        effect = None
        if card.primary_action == ActionType.FAST_TRAVEL:
             # Check Silence
             if not is_silenced(actor):
                  effect = EffectRegistry.get(card.effect_id) if card.effect_id else None
        
        # Execute Move (Teleport)
        state.move_unit(unit_id, self.target_hex)

        # Cleanup
        state.input_stack.pop()
        completed_hero_id, completed_card = state.resolution_queue.pop(0)

        # State Transition -> RESOLVED
        completed_card.state = CardState.RESOLVED
        
        if state.resolution_queue:
            state.current_actor_id = state.resolution_queue[0][0]
        else:
            state.current_actor_id = None
            state.phase = GamePhase.SETUP
            state.resolution_step = ResolutionStep.NONE
            
        return state

class SpawnMinionCommand(Command):
    """
    Debug/Setup command to place a minion.
    """
    def __init__(self, location: Hex, minion_type: MinionType, team: TeamColor, unit_id: UnitID):
        self.location = location
        self.minion_type = minion_type
        self.team = team
        self.unit_id = unit_id

    def execute(self, state: GameState) -> GameState:
        if self.location in state.unit_locations.values():
            raise ValueError(f"Location {self.location} occupied")
            
        minion = Minion(
            id=self.unit_id,
            name=f"{self.minion_type.name} Minion",
            type=self.minion_type,
            team=self.team,
            value=1
        )
        
        if self.team not in state.teams:
             state.teams[self.team] = Team(color=self.team)
             
        team_obj = state.teams.get(self.team)
        if team_obj:
            team_obj.minions.append(minion)
        
        state.move_unit(self.unit_id, self.location)
            
        return state

class AttackCommand(Command):
    """
    Executes the attack after receiving target input.
    Triggers the Defense Interrupt.
    """
    def __init__(self, target_unit_id: UnitID):
        self.target_unit_id = target_unit_id

    def execute(self, state: GameState) -> GameState:
        if not state.input_stack:
             raise ValueError("Not waiting for input")
             
        current_req = state.input_stack[-1]
        
        # Identify Attacker
        attacker_id, card = state.resolution_queue[0]
        if not self.target_unit_id and card.metadata.get("target_unit_id"):
             self.target_unit_id = UnitID(card.metadata["target_unit_id"])

        attacker_unit_id = UnitID(str(attacker_id))
        
        # Save Target to Metadata for resumption
        card.metadata["target_unit_id"] = str(self.target_unit_id)
        
        # Validation: Is target excluded? (Repeat restriction)
        excluded = card.metadata.get("excluded_targets", [])
        if str(self.target_unit_id) in excluded:
             raise ValueError(f"Target {self.target_unit_id} is excluded (already attacked)")
        
        attacker_pos = state.unit_locations.get(attacker_unit_id)
        target_pos = state.unit_locations.get(self.target_unit_id)
        
        if not attacker_pos or not target_pos:
            raise ValueError("Unit not found on board")
            
        # Validate Attack (Range, Line of Sight)
        range_val = card.range_value if card.is_ranged else 1
        
        if not validate_attack_target(state.unit_locations, attacker_pos, target_pos, range_val):
             raise ValueError("Invalid target (out of range/sight)")
             
        # --- EFFECT HOOK: Pre-Attack ---
        effect = None
        attacker_unit = state.get_unit(attacker_unit_id)
        if card.primary_action == ActionType.ATTACK:
             if not is_silenced(attacker_unit):
                  effect = EffectRegistry.get(card.effect_id) if card.effect_id else None
        target_unit = state.get_unit(self.target_unit_id)
        
        if effect:
             ctx = EffectContext(state=state, command=self, actor=attacker_unit, card=card, target=target_unit)
             effect.on_pre_action(ctx)
             
             if state.input_stack and state.input_stack[-1].request_type != InputRequestType.SELECT_ENEMY:
                 return state
        
        if state.input_stack and state.input_stack[-1].request_type == InputRequestType.SELECT_ENEMY:
            state.input_stack.pop()
        
        # Check if Target is Minion -> Auto-Resolve (MVP Rule: Minions don't defend with cards)
        if isinstance(target_unit, Minion):
             # Calculate Attack
             attacker_hero = state.get_hero(attacker_id) # Attacker is Hero?
             
             if attacker_hero:
                 attack_val = calculate_attack_power(card, attacker_hero)
                 defense_val = 0 # Minions have 0 defense/value?
                 
                 print(f"   [Combat] Minion Attack ({attack_val}) vs Defense ({defense_val})")
                 if resolve_combat(attack_val, defense_val):
                      print(f"   [Result] Minion {self.target_unit_id} DEFEATED!")
                      defeat_unit(state, self.target_unit_id, killer_id=attacker_id)
             
             # --- EFFECT HOOK: Post-Attack (Minion Path) ---
             # We reuse the 'effect' retrieved earlier in Pre-Attack
             if effect:
                  # Context might need target info again if it changed or if we want to ensure consistency
                  # For now reusing 'ctx' created in Pre-Attack if available, otherwise recreate?
                  # Pre-Attack 'ctx' was local. We need to recreate or use if still in scope?
                  # 'ctx' variable from line 601 is in scope.
                  # But wait, line 601 `ctx` creation was conditional on `effect`.
                  # And if we returned early (line 605), we wouldn't be here.
                  # But we MIGHT have returned early if input was needed.
                  # If input was needed (Select Enemy), we popped it (line 608).
                  # So we are here.
                  # We should recreate context to be safe and stateless.
                  
                  ctx_post = EffectContext(state=state, command=self, actor=attacker_unit, card=card, target=target_unit)
                  effect.on_post_action(ctx_post)

             # Automatic Cleanup (Since we skipped Defense Phase)
             # NOTE: If the effect re-inserted the card (Repetition), we should NOT pop the current card if it's still head of queue.
             # Logic: If effect requested new input (for repetition), we should suspend.
             
             if state.input_stack:
                 # Effect pushed input (e.g. Repetition Select Enemy).
                 # Treat as "suspended". Do NOT pop resolution queue.
                 return state

             if state.resolution_queue:
                  # Check if we should pop.
                  # If we repeated, the card might be at index 0 (re-inserted) or we just operate on HEAD.
                  # Standard behavior: Pop HEAD.
                  completed_hero_id, completed_card = state.resolution_queue.pop(0)
                  completed_card.state = CardState.RESOLVED
             
             if state.resolution_queue:
                  state.current_actor_id = state.resolution_queue[0][0]
             else:
                  state.current_actor_id = None
                  state.phase = GamePhase.SETUP
                  state.resolution_step = ResolutionStep.NONE

             return state

        # 2. Push the 'Defense' request for the TARGET player.
        target_hero_id = HeroID(str(self.target_unit_id))
        
        req_id = str(uuid.uuid4())
        defense_req = InputRequest(
            id=req_id,
            player_id=target_hero_id,
            request_type=InputRequestType.DEFENSE_CARD,
            context={
                "attacker_id": attacker_id,
                "attack_card_id": card.id
            }
        )
        state.input_stack.append(defense_req)
        
        return state

class PlayDefenseCommand(Command):
    """
    The Defender plays a card to block.
    """
    def __init__(self, card_id: Optional[CardID] = None):
        self.card_id = card_id

    def execute(self, state: GameState) -> GameState:
        if not state.input_stack:
             raise ValueError("Not waiting for input")
             
        current_req = state.input_stack[-1]
        if current_req.request_type != InputRequestType.DEFENSE_CARD:
            raise ValueError("Not waiting for defense")
            
        defender_id = current_req.player_id
        defender = state.get_hero(defender_id)
        
        defense_card: Optional[Card] = None
        if self.card_id:
            for i, c in enumerate(defender.hand):
                if c.id == self.card_id:
                    defense_card = c
                    defender.hand.pop(i)
                    break
            
            if not defense_card:
                 raise ValueError("Defense card not found in hand")
            
            defense_card.state = CardState.DISCARD
            defense_card.is_facedown = False

        _attacker_id, attack_card = state.resolution_queue[0]
        attacker = state.get_hero(current_req.context["attacker_id"])
        attack_val = calculate_attack_power(attack_card, attacker)
        
        def_ctx = None
        if defense_card and defense_card.effect_id:
             attacker_unit = state.get_unit(UnitID(str(attacker.id))) if attacker else None
             def_ctx = EffectContext(state=state, command=self, actor=defender, card=defense_card, target=attacker_unit)

        defense_val = calculate_defense_power(defender, state, defense_card, ctx=def_ctx) 
        
        print(f"   [Combat] Attack ({attack_val}) vs Defense ({defense_val})")
        
        if resolve_combat(attack_val, defense_val):
            print(f"   [Result] Hero {defender_id} DEFEATED!")
        else:
            print(f"   [Result] Attack BLOCKED!")
            
        state.input_stack.pop()
        
        # --- EFFECT HOOK: Post-Attack ---
        attack_effect = None
        if attack_card.primary_action == ActionType.ATTACK:
             attacker_unit = state.get_unit(UnitID(str(_attacker_id)))
             if not is_silenced(attacker_unit):
                  attack_effect = EffectRegistry.get(attack_card.effect_id) if attack_card.effect_id else None
        
        if attack_effect:
             attacker_unit = state.get_unit(UnitID(str(_attacker_id)))
             defender_unit = state.get_unit(UnitID(str(defender_id)))
             
             ctx = EffectContext(state=state, command=self, actor=attacker_unit, card=attack_card, target=defender_unit)
             
             attack_effect.on_post_action(ctx)
        
        # Check if Effect requested new Input (e.g. Repetition)
        if state.input_stack:
             return state

        # Resolve Main Action (Attacker).
        # Since Attack is done, we pop the resolution queue too.
        completed_hero_id, completed_card = state.resolution_queue.pop(0)
        
        # State Transition -> RESOLVED (Attacker's card)
        completed_card.state = CardState.RESOLVED
        
        if state.resolution_queue:
            state.current_actor_id = state.resolution_queue[0][0]
        else:
            state.current_actor_id = None
            state.phase = GamePhase.SETUP
            state.resolution_step = ResolutionStep.NONE
            
        return state

class UpgradeCardCommand(Command):
    """
    Executes the upgrade choice for a hero.
    1. Finds substitute card (Old Tier).
    2. Finds 'Other' new card (Same Tier/Color) -> ITEM.
    3. Adds New Card to Hand.
    """
    def __init__(self, hero_id: HeroID, chosen_card_id: CardID):
        self.hero_id = hero_id
        self.chosen_card_id = chosen_card_id
        
    def execute(self, state: GameState) -> GameState:
        # 1. Validation: Waiting for Input
        if not state.input_stack:
             raise ValueError("Not waiting for input")
             
        # Support Simultaneous Upgrades (Non-blocking):
        # Search the stack for a request that matches this command.
        target_req = None
        target_index = -1
        
        for i, req in enumerate(reversed(state.input_stack)):
            # We iterate backwards just in case, though order shouldn't matter for unique hero IDs.
            if req.request_type == InputRequestType.UPGRADE_CHOICE and str(req.player_id) == str(self.hero_id):
                target_req = req
                target_index = len(state.input_stack) - 1 - i
                break
                
        if not target_req:
             # Fallback check for nice error message
             if state.input_stack[-1].request_type == InputRequestType.UPGRADE_CHOICE:
                  raise ValueError(f"Waiting for input from {state.input_stack[-1].player_id}, but {self.hero_id} tried to act.")
             else:
                  raise ValueError(f"Not waiting for Upgrade, waiting for {state.input_stack[-1].request_type}")

        current_req = target_req

        # 2. Identify Hero
        hero = state.get_hero(self.hero_id)
        if not hero: raise ValueError("Hero not found")
        
        # 3. Find The Chosen Card
        chosen_card = None
        for c in hero.deck:
             if str(c.id) == str(self.chosen_card_id):
                 chosen_card = c
                 break
        
        if not chosen_card:
             raise ValueError(f"Chosen upgrade card {self.chosen_card_id} not found in deck")

        # 4. Context Validation: Tier Check
        required_tier = current_req.context.get("tier")
        if required_tier:
             # CardTier is str Enum, so simple comparison works if serialized to str or enum
             if chosen_card.tier != required_tier:
                  raise ValueError(f"Invalid Tier: Expected {required_tier}, got {chosen_card.tier}")
             
        # 5. Logic: Swap
        if chosen_card.tier == CardTier.IV:
             # Ultimate
             chosen_card.state = CardState.PASSIVE
             
        else:
             # Standard Upgrade (Tier II/III)
             # A. Find 'Other' card of same Tier/Color (The one NOT chosen)
             other_card = None
             for c in hero.deck:
                 if c.tier == chosen_card.tier and c.color == chosen_card.color and c.id != chosen_card.id:
                     other_card = c
                     break
             
             if other_card:
                 other_card.state = CardState.ITEM
                 # Apply Item Passive Bonus
                 if other_card.item:
                     current_val = hero.items.get(other_card.item, 0)
                     hero.items[other_card.item] = current_val + 1
             
             # B. Find 'Old' card (Previous Tier)
             target_prev_tier = None
             if chosen_card.tier == CardTier.II: target_prev_tier = CardTier.I
             elif chosen_card.tier == CardTier.III: target_prev_tier = CardTier.II
             
             old_card = None
             if target_prev_tier:
                 for c in hero.deck:
                     if c.color == chosen_card.color and c.tier == target_prev_tier:
                         old_card = c
                         break
                     
             if old_card:
                 old_card.state = CardState.RETIRED
                 # Remove from Hand if there
                 if old_card in hero.hand:
                     hero.hand.remove(old_card)
                     
             # C. Add New Card to Hand
             chosen_card.state = CardState.HAND
             hero.hand.append(chosen_card)
        
        # 6. Consume Input Request
        state.input_stack.pop(target_index)

        return state

class ResolveSkillCommand(Command):
    """
    Handles resolution of a Skill that requested input (e.g. SELECT_UNIT).
    Delegates to the Card's Effect.
    """
    def __init__(self, target_unit_id: Optional[UnitID] = None, target_hex: Optional[Hex] = None):
        self.target_unit_id = target_unit_id
        self.target_hex = target_hex

    def execute(self, state: GameState) -> GameState:
        if not state.input_stack:
             raise ValueError("Not waiting for input")
             
        current_req = state.input_stack[-1]
              
        # Identify Actor/Card
        hero_id, card = state.resolution_queue[0]
        
        effect = EffectRegistry.get(card.effect_id)
        if not effect:
             raise ValueError(f"No effect found for skill {card.name}")
             
        actor = state.get_hero(hero_id)
        
        # Resolve Target Object
        target_unit = None
        if self.target_unit_id:
             target_unit = state.get_unit(self.target_unit_id)
             
        # Create Context
        ctx = EffectContext(
             state=state,
             command=self,
             actor=actor,
             card=card,
             target=target_unit,
             data={
                 "input_unit_id": str(self.target_unit_id) if self.target_unit_id else None,
                 "input_hex": self.target_hex
             }
        )
        
        # Execute Effect Logic
        effect.on_post_action(ctx)
        
        # Cleanup / Finish
        # We need to remove the specific request that was just resolved.
        # It's explicitly valid to assume it's the one that triggered this command,
        # but if on_post_action pushed NEW requests, they are on TOP.
        # So we need to find and remove the 'completed' request carefully or 
        # assume the effect managed the stack? 
        # Standard: Effect PUSHES on top. So the 'completed' request is deeper?
        # No, 'on_post_action' runs. 
        # Input Stack: [Req1] -> ResolveSkill -> on_post hooks -> Pushes [Req2] -> Stack: [Req1, Req2]
        # We want to remove Req1. 
        # So we remove validly.
        
        # Finding the request index might be tricky if not tracked.
        # But we know `ResolveSkillCommand` runs ONLY when `state.input_stack` has a request.
        # And we validated it at start.
        # Let's assume we remove the request that we "answered".
        # Which is NOT necessarily at -1 if on_post_action added stuff!
        
        # Strategy:
        # 1. Capture reference to request at start.
        # 2. Remove it by reference.
        
        if current_req in state.input_stack:
            state.input_stack.remove(current_req)
            
        # Check if chained requests exist
        if state.input_stack:
             # Processing continues (Multi-step effect)
             return state
        
        # Finish Action (Pop resolution queue)
        state.resolution_queue.pop(0)
        card.state = CardState.RESOLVED
        
        if state.resolution_queue:
            state.current_actor_id = state.resolution_queue[0][0]
        else:
            state.current_actor_id = None
            state.phase = GamePhase.SETUP
            state.resolution_step = ResolutionStep.NONE
            
        return state

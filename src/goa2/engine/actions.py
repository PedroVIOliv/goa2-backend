from typing import List, Tuple, Dict, Optional
from goa2.engine.command import Command
from goa2.domain.state import GameState
from goa2.domain.input import InputRequest, InputRequestType
from goa2.domain.models import Card, TeamColor, ActionType, MinionType, Minion, Team, CardState, CardTier, StatType
from goa2.domain.hex import Hex
from goa2.engine.phases import GamePhase, ResolutionStep
from goa2.domain.types import HeroID, CardID, UnitID, BoardEntityID
from goa2.engine.rules import validate_movement_path, validate_attack_target
from goa2.engine.combat import calculate_attack_power, calculate_defense_power, resolve_combat
import uuid

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
        hero = None
        for team in state.teams.values():
            for h in team.heroes:
                if h.id == self.hero_id:
                    hero = h
                    break
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
        
        # State Transition -> UNRESOLVED
        card_to_play.state = CardState.UNRESOLVED
        
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
            raise ValueError(f"Not waiting for Action Choice, waiting for {current_req.request_type}")
            
        hero_id, card = state.resolution_queue[0]
        
        # Identify Hero for Item lookups
        hero = None
        for t in state.teams.values():
             for h in t.heroes:
                 if h.id == hero_id:
                     hero = h
                     break
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
            
        # Logic Branch
        
        # POP the Choice Request first
        state.input_stack.pop()
        

        if self.action_type == ActionType.ATTACK:
            # Transition to Target Selection
            req_id = str(uuid.uuid4())
            req = InputRequest(
                id=req_id,
                player_id=hero_id,
                request_type=InputRequestType.SELECT_ENEMY
            )
            state.input_stack.append(req)
            return state

        elif self.action_type == ActionType.MOVEMENT:
            # Determine Movement Value
            move_val = 0
            if card.primary_action == ActionType.MOVEMENT:
                 move_val = card.primary_action_value or 0
            elif ActionType.MOVEMENT in card.secondary_actions:
                 move_val = card.secondary_actions[ActionType.MOVEMENT]

            # Apply Item Bonuses (Movement)
            move_val += hero.items.get(StatType.MOVEMENT, 0)

            # Transition to Movement Input -> PUSH new request
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
            
        elif self.action_type == ActionType.HOLD:
            # Finish immediately (Pass, but consume card)
            pass 
        
        else:
            # For Skills (no extra input needed usually, or handled specifically)
            pass
            
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
        # 1. Update Unit Location (Legacy/Quick Lookup)
        state.unit_locations[unit_id] = self.target_hex
        
        # 2. Update Tile Occupancy (New Grid System)
        if start_hex in state.board.tiles:
            state.board.tiles[start_hex].occupant_id = None
        
        if self.target_hex in state.board.tiles:
            state.board.tiles[self.target_hex].occupant_id = BoardEntityID(str(unit_id))
        
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
             
        # Find actor team
        actor_team = TeamColor.RED # Fallback
        for t in state.teams.values():
             for h in t.heroes:
                 if str(h.id) == str(unit_id):
                     actor_team = t.color
                     break
        
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
        # Must be Same Zone OR Adjacent Zone
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
                 
        # Execute Move (Teleport)
        state.unit_locations[unit_id] = self.target_hex
        
        if start_hex in state.board.tiles:
            state.board.tiles[start_hex].occupant_id = None
        
        if self.target_hex in state.board.tiles:
            state.board.tiles[self.target_hex].occupant_id = BoardEntityID(str(unit_id))
            
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
            
        # Create Minion Model
        minion = Minion(
            id=self.unit_id,
            name=f"{self.minion_type.name} Minion",
            type=self.minion_type,
            team=self.team,
            value=1 # Default value
        )
        
        if self.team not in state.teams:
             # Create team if missing (for MVP setup/debug convenience)
             state.teams[self.team] = Team(color=self.team)
             
        team_obj = state.teams.get(self.team)
        if team_obj:
            team_obj.minions.append(minion)
        
        # We still need global tracking of "ID -> Unit"?
        # GameState.unit_locations tracks location.
        # But if we need to look up Unit by ID, we now need to search Teams.
        # This is slower O(N) but acceptable for MVP.
        # Or we can keep a "unit_registry" in State if needed.
        # For now, only location is critical.
        
        state.unit_locations[self.unit_id] = self.location
        
        # Update Tile Occupancy
        if self.location in state.board.tiles:
            state.board.tiles[self.location].occupant_id = BoardEntityID(str(self.unit_id))
            
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
        if current_req.request_type != InputRequestType.SELECT_ENEMY:
            raise ValueError(f"Not waiting for enemy selection, waiting for {current_req.request_type}")
            
        # Identify Attacker
        attacker_id, card = state.resolution_queue[0]
        attacker_unit_id = UnitID(str(attacker_id))
        attacker_pos = state.unit_locations.get(attacker_unit_id)
        
        # Identify Target
        target_pos = state.unit_locations.get(self.target_unit_id)
        
        if not attacker_pos or not target_pos:
            raise ValueError("Unit not found on board")
            
        # Validate Attack (Range, Line of Sight)
        range_val = card.range_value if card.is_ranged else 1
        
        # TODO: Handle multi-step targeting if card needs it? 
        # For now, simple standard attack.
        
        if not validate_attack_target(state.unit_locations, attacker_pos, target_pos, range_val):
             raise ValueError("Invalid target (out of range/sight)")
             
        # ATTACK IS VALID. 
        # 1. Pop the 'Select Enemy' request.
        state.input_stack.pop()
        
        # 2. Push the 'Defense' request for the TARGET player.
        # We need to find which HeroID corresponds to target_unit_id.
        # Ideally UnitID == HeroID for heroes.
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
        self.card_id = card_id # None means "Pass" (Take hit)

    def execute(self, state: GameState) -> GameState:
        if not state.input_stack:
             raise ValueError("Not waiting for input")
             
        current_req = state.input_stack[-1]
        if current_req.request_type != InputRequestType.DEFENSE_CARD:
            raise ValueError("Not waiting for defense")
            
        defender_id = current_req.player_id
        
        # Power Calculation
        # Find Defender Hero
        defender = None
        for t in state.teams.values():
            for h in t.heroes:
                if h.id == defender_id:
                    defender = h
                    break
        
        defense_card: Optional[Card] = None
        if self.card_id:
            # Find card in hand
            # We must remove it from hand too!
            for i, c in enumerate(defender.hand):
                if c.id == self.card_id:
                    defense_card = c
                    defender.hand.pop(i)
                    break
            
            if not defense_card:
                 raise ValueError("Defense card not found in hand")
            
            # State Transition -> DISCARD (Defense cards are resolved immediately)
            defense_card.state = CardState.DISCARD

        # Get the attack card from the resolution queue
        _attacker_id, attack_card = state.resolution_queue[0]

        # Calculate Attack and Defense Power
        from goa2.engine.combat import calculate_attack_power, calculate_defense_power
        
        # Re-Find Attacker (needed for calculate_attack_power items)
        attacker = None
        for t in state.teams.values():
            for h in t.heroes:
                if h.id == current_req.context["attacker_id"]:
                    attacker = h
                    break

        attack_val = calculate_attack_power(attack_card, attacker)
        defense_val = calculate_defense_power(defender, state, defense_card) 
        
        # Log
        print(f"   [Combat] Attack ({attack_val}) vs Defense ({defense_val})")
        
        # Resolve
        from goa2.engine.combat import resolve_combat
        if resolve_combat(attack_val, defense_val):
            print(f"   [Result] Hero {defender_id} DEFEATED!")
            # Logic: Remove life counter, etc.
            # Pop stack
        else:
            print(f"   [Result] Attack BLOCKED!")
            
        # Done. Pop Defense Request.
        state.input_stack.pop()
        
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
        hero = None
        for t in state.teams.values():
             for h in t.heroes:
                 if h.id == self.hero_id:
                     hero = h
                     break
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
             
        # 6. Cleanup Input (Remove the specific request we handled)
        state.input_stack.pop(target_index)
        
        return state

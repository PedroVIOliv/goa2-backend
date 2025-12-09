
import pytest
from goa2.domain.state import GameState
from goa2.engine.effects import EffectRegistry, Effect, EffectContext
from goa2.domain.models import Card, CardTier, CardColor, ActionType, Hero, Team, TeamColor, Minion, MinionType
from goa2.domain.types import HeroID, CardID, UnitID, BoardEntityID
from goa2.domain.hex import Hex
from goa2.domain.board import Board, Zone
from goa2.engine.actions import PlayCardCommand, RevealCardsCommand, ResolveNextCommand, ChooseActionCommand, AttackCommand, ResolveSkillCommand, PerformMovementCommand
from goa2.domain.input import InputRequestType
from goa2.engine.phases import GamePhase

# Import Scripts (Registers Effects)
import goa2.scripts.arien 

@pytest.fixture
def effect_state():
    board = Board(
        hexes={Hex(q=0,r=0,s=0), Hex(q=1,r=-1,s=0), Hex(q=2,r=-2,s=0)},
        zones={"Z1": Zone(id="Z1", hexes={Hex(q=0,r=0,s=0), Hex(q=1,r=-1,s=0), Hex(q=2,r=-2,s=0)})},
        tiles={}
    )
    state = GameState(board=board, teams={})
    return state

def test_effect_registry():
    # Verify Arien's effects are registered
    assert EffectRegistry.get("effect_swap_enemy_minion_repeat") is not None
    assert EffectRegistry.get("effect_attack_discard_behind_repeat") is not None

def test_violent_torrent_effect(effect_state):
    state = effect_state
    
    # Setup: Arien (Attacker) and Enemy Hero (Behind Target)
    # Positions:
    # Arien: (0,0,0)
    # Target (Minion): (1,-1,0)  (East)
    # Enemy Hero: (2,-2,0) (East of Target -> Behind)
    
    arien_id = HeroID("arien")
    minion_id = UnitID("minion")
    enemy_hero_id = HeroID("enemy")
    
    # Create Units
    arien_card = Card(
        id=CardID("viol_torr"),
        name="Violent Torrent",
        tier=CardTier.III,
        color=CardColor.RED,
        initiative=9, 
        primary_action=ActionType.ATTACK,
        effect_id="effect_attack_discard_behind_repeat",
        effect_text="Discard behind"
    )
    
    arien = Hero(id=arien_id, name="Arien", deck=[], hand=[arien_card], team=TeamColor.RED)
    minion = Minion(id=minion_id, name="M", type=MinionType.MELEE, team=TeamColor.BLUE)
    
    discard_card = Card(id="c1", name="C1", tier=CardTier.I, color=CardColor.RED, initiative=1, primary_action=ActionType.ATTACK, effect_id="", effect_text="")
    enemy = Hero(id=enemy_hero_id, name="Enemy", deck=[], hand=[discard_card], team=TeamColor.BLUE)
    
    state.teams[TeamColor.RED] = Team(color=TeamColor.RED, heroes=[arien])
    state.teams[TeamColor.BLUE] = Team(color=TeamColor.BLUE, heroes=[enemy], minions=[minion])
    
    state.move_unit(UnitID(str(arien_id)), Hex(q=0,r=0,s=0))
    state.move_unit(minion_id, Hex(q=1,r=-1,s=0))
    state.move_unit(UnitID(str(enemy_hero_id)), Hex(q=2,r=-2,s=0))
    
    # Run Actions Logic
    # 0. Set Phase
    state.phase = GamePhase.PLANNING

    # 1. Play Card
    PlayCardCommand(arien_id, CardID("viol_torr")).execute(state)
    RevealCardsCommand().execute(state)
    ResolveNextCommand().execute(state) # Pushes ChooseAction
    
    # 2. Choose Attack
    ChooseActionCommand(ActionType.ATTACK).execute(state) # Pushes Select Enemy
    
    # 3. Perform Attack (Triggers Pre-Hook)
    # Mock Input Stack Context if needed by AttackCommand (usually context is empty for SELECT_ENEMY)
    # But AttackCommand populates context for Defense request.
    
    # Before AttackCommand, Enemy Has Card
    assert len(enemy.hand) == 1
    
    AttackCommand(minion_id).execute(state)

    # Effect triggers: Pushes SELECT_UNIT (Discard)
    assert state.input_stack
    assert state.input_stack[-1].request_type == InputRequestType.SELECT_UNIT
    
    # Resolve Effect (Select Enemy)
    ResolveSkillCommand(target_unit_id=enemy_hero_id).execute(state)
    
    # Effect Resolved: Enemy Discards
    assert len(enemy.hand) == 0
    assert len(enemy.discard_pile) == 1
    
    # Resume Attack (Cleanup)
    # Stack: SELECT_ENEMY (Persisted) -> Resume pushes DEFENSE_CARD
    ChooseActionCommand(ActionType.ATTACK).execute(state)


def test_ebb_and_flow_effect(effect_state):
    state = effect_state
    
    # Positions:
    # Arien: (0,0,0)
    # Enemy Minion: (1,-1,0) (Range 1)
    
    arien_id = HeroID("arien")
    minion_id = UnitID("minion")
    
    ebb_card = Card(
        id=CardID("ebb"),
        name="Ebb and Flow",
        tier=CardTier.III,
        color=CardColor.GREEN,
        initiative=3,
        primary_action=ActionType.SKILL,
        range_value=4,
        effect_id="effect_swap_enemy_minion_repeat",
        effect_text="Swap"
    )
    
    arien = Hero(id=arien_id, name="Arien", deck=[], hand=[ebb_card], team=TeamColor.RED)
    minion = Minion(id=minion_id, name="M", type=MinionType.MELEE, team=TeamColor.BLUE)
    
    state.teams[TeamColor.RED] = Team(color=TeamColor.RED, heroes=[arien])
    state.teams[TeamColor.BLUE] = Team(color=TeamColor.BLUE, minions=[minion])
    
    loc_arien = Hex(q=0,r=0,s=0)
    loc_minion = Hex(q=1,r=-1,s=0)
    
    state.move_unit(UnitID(str(arien_id)), loc_arien)
    state.move_unit(minion_id, loc_minion)
    
    # 1. Play & Reveal
    state.phase = GamePhase.PLANNING
    PlayCardCommand(arien_id, CardID("ebb")).execute(state)
    RevealCardsCommand().execute(state)
    ResolveNextCommand().execute(state)
    
    # 2. Choose Skill
    # ChooseActionCommand triggers Pre-Action Hook for Skill (else block)
    # Pre-Action Pushes SELECT_UNIT
    ChooseActionCommand(ActionType.SKILL).execute(state)
    
    # Verify Input Request
    assert state.input_stack
    req = state.input_stack[-1]
    assert req.request_type == InputRequestType.SELECT_UNIT
    assert req.context["criteria"] == "enemy_minion"
    
    # 3. Resolve Skill
    ResolveSkillCommand(target_unit_id=minion_id).execute(state)
    
    # Verify Swap
    assert state.unit_locations[UnitID(str(arien_id))] == loc_minion
    assert state.unit_locations[minion_id] == loc_arien

def test_secondary_action_no_effect(effect_state):
    """
    Verify that if a card is used for a Secondary Action, the Primary Action's effect does NOT trigger.
    """
    state = effect_state
    arien_id = HeroID("arien")
    
    # Card: Primary ATTACK (with Effect), Secondary MOVEMENT
    # Effect: EbbAndFlow (Pushes Input Request) -> Easy to detect if triggered erroneously
    card = Card(
        id=CardID("hybrid"),
        name="Hybrid",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK, # Primary
        secondary_actions={ActionType.MOVEMENT: 2}, # Secondary
        effect_id="effect_swap_enemy_minion_repeat", # Should only trigger on ATTACK
        effect_text="Swap"
    )
    
    arien = Hero(id=arien_id, name="Arien", deck=[], hand=[card], team=TeamColor.RED)
    state.teams[TeamColor.RED] = Team(color=TeamColor.RED, heroes=[arien])
    
    state.move_unit(UnitID(str(arien_id)), Hex(q=0,r=0,s=0))
    
    # 1. Play & Reveal
    state.phase = GamePhase.PLANNING
    PlayCardCommand(arien_id, CardID("hybrid")).execute(state)
    RevealCardsCommand().execute(state)
    ResolveNextCommand().execute(state)
    
    # 2. Choose Secondary Action (MOVEMENT)
    ChooseActionCommand(ActionType.MOVEMENT).execute(state)
    
    # Input stack should now have MOVEMENT_HEX request
    assert state.input_stack
    assert state.input_stack[-1].request_type == InputRequestType.MOVEMENT_HEX
    
    # 3. Perform Movement
    target_hex = Hex(q=1,r=-1,s=0)
    PerformMovementCommand(target_hex).execute(state)
    
    # If Effect triggered, it would have pushed SELECT_UNIT logic or crashed.
    # If correct, movement finished, card resolved, queue empty.
    
    # Check Input Stack is empty (Movement popped its request)
    # If Effect triggered (Pre-Move), it might have pushed something?
    # EbbAndFlow Pre-Action pushes SELECT_UNIT.
    # So if implemented incorrectly, stack would have SELECT_UNIT.
    assert not state.input_stack
    
    # Check Unit Moved
    assert state.unit_locations[UnitID(str(arien_id))] == target_hex
    
    
    # Check Card Resolved
    assert card.state.name == "RESOLVED"

def test_fast_travel_no_effect(effect_state):
    """
    Verify that Fast Travel NEVER triggers effects, even if it's the primary action.
    """
    state = effect_state
    
    # Card: Primary FAST_TRAVEL with an Effect attached
    # Effect: EbbAndFlow (chosen because it has clear side-effects: SWAP or Input Request)
    card = Card(
        id=CardID("ft_card"),
        name="FT Card",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=10,
        primary_action=ActionType.FAST_TRAVEL, 
        effect_id="effect_swap_enemy_minion_repeat",
        effect_text="Swap"
    )
    
    rogue = Hero(id=HeroID("rogue"), name="Rogue", deck=[], hand=[card], team=TeamColor.BLUE)
    state.teams[TeamColor.BLUE] = Team(color=TeamColor.BLUE, heroes=[rogue])
    
    start_hex = Hex(q=0,r=0,s=0)
    target_hex = Hex(q=1,r=-1,s=0)
    
    # Place Rogue
    state.move_unit(UnitID("rogue"), start_hex)
    
    # 1. Play & Reveal
    state.phase = GamePhase.PLANNING
    PlayCardCommand(HeroID("rogue"), CardID("ft_card")).execute(state)
    RevealCardsCommand().execute(state)
    ResolveNextCommand().execute(state)
    
    # 2. Choose Action (FAST_TRAVEL)
    # ChooseActionCommand logic for FAST_TRAVEL pushes FAST_TRAVEL_DESTINATION request
    ChooseActionCommand(ActionType.FAST_TRAVEL).execute(state)
    
    # Verify Input Type
    assert state.input_stack[-1].request_type == InputRequestType.FAST_TRAVEL_DESTINATION
    
    # 3. Perform Fast Travel
    from goa2.engine.actions import PerformFastTravelCommand
    PerformFastTravelCommand(target_hex).execute(state)
    
    # Verification:
    # 1. Unit should have moved (Teleport successful)
    assert state.unit_locations[UnitID("rogue")] == target_hex
    
    # 2. Input Stack should be empty (no SELECT_UNIT pushed by effect)
    assert not state.input_stack
    
    # 3. Queue empty
    assert not state.resolution_queue

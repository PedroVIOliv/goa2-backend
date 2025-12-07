import pytest
from goa2.domain.state import GameState
from goa2.engine.phases import GamePhase, ResolutionStep
from goa2.engine.actions import PlayCardCommand, RevealCardsCommand, ResolveNextCommand, PerformMovementCommand, ChooseActionCommand
from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, Hero, Card, CardTier, CardColor, ActionType
from goa2.domain.types import HeroID, CardID, UnitID

@pytest.fixture
def loop_state():
    """Setup a game with 2 teams, 1 hero each."""
    b = Board()
    
    # Red Hero: Initiative 10
    c1 = Card(id="c_red", name="Slow", tier=CardTier.UNTIERED, color=CardColor.GOLD, initiative=10, primary_action=ActionType.ATTACK, primary_action_value=4, effect_id="1", effect_text="foo")
    h_red = Hero(id="h_red", name="RedHero", team=TeamColor.RED, deck=[], hand=[c1])
    t_red = Team(color=TeamColor.RED, heroes=[h_red])
    
    # Blue Hero: Initiative 2
    c2 = Card(id="c_blue", name="Fast", tier=CardTier.UNTIERED, color=CardColor.GOLD, initiative=2, primary_action=ActionType.MOVEMENT, primary_action_value=3, effect_id="2", effect_text="bar")
    h_blue = Hero(id="h_blue", name="BlueHero", team=TeamColor.BLUE, deck=[], hand=[c2])
    t_blue = Team(color=TeamColor.BLUE, heroes=[h_blue])
    
    return GameState(board=b, teams={TeamColor.RED: t_red, TeamColor.BLUE: t_blue}, phase=GamePhase.PLANNING)

def test_full_loop(loop_state):
    s = loop_state
    
    # 1. PLANNING PHASE
    # Play Cards
    PlayCardCommand(HeroID("h_red"), CardID("c_red")).execute(s)
    PlayCardCommand(HeroID("h_blue"), CardID("c_blue")).execute(s)
    
    assert len(s.pending_inputs) == 2
    assert s.phase == GamePhase.PLANNING
    
    # Validate Hand Consumption
    # Note: loop_state fixture created clean objects, but s.teams references them.
    hero_red = s.teams[TeamColor.RED].heroes[0]
    assert len(hero_red.hand) == 0 # Should be empty after play
    
    # 2. REVELATION
    RevealCardsCommand().execute(s)
    
    assert s.phase == GamePhase.RESOLUTION
    assert s.resolution_step == ResolutionStep.ACTING
    assert not s.pending_inputs
    assert len(s.resolution_queue) == 2
    
    # Verify Order: Red (Init 10) should be first (Descending), Blue (Init 2) second
    first_hero, first_card = s.resolution_queue[0]
    assert first_hero == "h_red"
    assert first_card.initiative == 10
    
    # Verify Current Actor
    assert s.current_actor_id == "h_red"
    
    # Setup Locations for Movement Test
    # Blue Hero (Fast/Movement) needs a location
    from goa2.domain.hex import Hex
    s.unit_locations[UnitID("h_blue")] = Hex(q=0, r=0, s=0)
    
    # 3. RESOLUTION (Step 1)
    # Red goes first now
    ResolveNextCommand().execute(s)
    
    # Assert Waiting for Choice (Red)
    from goa2.domain.state import InputRequestType
    assert s.awaiting_input_type == InputRequestType.ACTION_CHOICE
    
    # Choose Attack
    ChooseActionCommand(ActionType.ATTACK).execute(s)

    # Now waiting for SELECT_ENEMY
    assert s.awaiting_input_type == InputRequestType.SELECT_ENEMY

    # Execute Attack (Select Target)
    # Target Blue Hero
    from goa2.engine.actions import AttackCommand, PlayDefenseCommand
    
    # We need to ensure Red and Blue have locations for range check
    s.unit_locations[UnitID("h_red")] = Hex(q=1, r=0, s=-1) # Adjacent to Blue at 0,0,0
    
    AttackCommand(UnitID("h_blue")).execute(s)
    
    # Now waiting for DEFENSE_CARD (from Blue)
    assert s.awaiting_input_type == InputRequestType.DEFENSE_CARD
    
    # Play Defense (Pass / Take Hit)
    PlayDefenseCommand(card_id=None).execute(s)
    
    # Red popped, Blue is next
    assert len(s.resolution_queue) == 1
    assert s.current_actor_id == "h_blue"
    
    # 4. RESOLUTION (Step 2)
    # 4. RESOLUTION (Step 2)
    # Blue goes (Movement)
    ResolveNextCommand().execute(s)
    
    # Assert Waiting for ACTION_CHOICE
    from goa2.domain.state import InputRequestType
    assert s.awaiting_input_type == InputRequestType.ACTION_CHOICE
    
    # Choose Primary Action (Movement)
    ChooseActionCommand(ActionType.MOVEMENT).execute(s)
    
    # Assert Waiting for Hex Input
    assert s.awaiting_input_type == InputRequestType.MOVEMENT_HEX
    assert len(s.resolution_queue) == 1 # Card not popped yet
    
    # Perform Move
    # Target: 1 West (q=-1, r=0, s=1) - Empty, away from Red.
    target = Hex(q=-1, r=0, s=1)
    PerformMovementCommand(target).execute(s)
    
    # Assert Finished
    assert s.awaiting_input_type == InputRequestType.NONE
    assert len(s.resolution_queue) == 0
    assert s.current_actor_id == None
    assert s.phase == GamePhase.SETUP 
    
    # Verify Movement
    new_loc = s.unit_locations[UnitID("h_blue")]
    assert new_loc == target

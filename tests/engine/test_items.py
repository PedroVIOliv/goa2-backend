import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import TeamColor, Team, Hero, Card, CardTier, CardColor, ActionType, CardState, StatType
from goa2.domain.hex import Hex
from goa2.engine.mechanics import run_end_phase
from goa2.engine.actions import UpgradeCardCommand, ChooseActionCommand
from goa2.engine.phases import GamePhase
from goa2.domain.input import InputRequestType

@pytest.fixture
def item_state():
    # Setup Board
    board = Board(zones={"z1": Zone(id="z1", hexes={Hex(q=0,r=0,s=0)})}, lane=["z1"], tiles={})
    board.populate_tiles_from_zones()
    
    # Hero: Red
    c_mov = Card(id="mov1", name="Move", tier=CardTier.UNTIERED, color=CardColor.GOLD, initiative=10, primary_action=ActionType.MOVEMENT, primary_action_value=2, effect_id="m1", effect_text="m1")
    
    # Upgrade Cards
    # Item Card: Gives Bonus Movement
    c_item_mov = Card(
        id="item_mov", name="Boots", tier=CardTier.II, color=CardColor.GREEN, 
        initiative=5, primary_action=ActionType.SKILL, 
        item=StatType.MOVEMENT, # +1 Movement
        effect_id="boots", effect_text="Boots"
    )
    
    # Chosen Card: Random Tier II
    c_choice = Card(
        id="choice", name="Choice", tier=CardTier.II, color=CardColor.GREEN,
        initiative=5, primary_action=ActionType.SKILL,
        effect_id="choice", effect_text="Choice"
    )
    
    # Start Item at Level 2 (Upgrade Ready)
    h1 = Hero(id="h1", name="Hero1", team=TeamColor.RED, level=2, gold=2, deck=[c_mov, c_item_mov, c_choice], hand=[c_mov]) 
    
    state = GameState(
        board=board,
        teams={
           TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1]),
           TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[])
        },
        active_zone_id="z1",
        phase=GamePhase.END_PHASE
    )
    return state

def test_item_acquisition(item_state):
    # 1. Trigger Level Up (Level 2 -> 3)
    # H1 has 2 Gold, Cost 2.
    run_end_phase(item_state)
    
    h1 = item_state.teams[TeamColor.RED].heroes[0]
    assert h1.level == 3
    
    # 2. Upgrade Choice
    req = item_state.input_stack[-1]
    assert req.request_type == InputRequestType.UPGRADE_CHOICE
    
    # 3. Choose 'Choice' card, so 'Boots' becomes ITEM
    cmd = UpgradeCardCommand(hero_id=h1.id, chosen_card_id="choice")
    cmd.execute(item_state)
    
    # 4. Verify Item State
    item_card = next(c for c in h1.deck if c.id == "item_mov")
    assert item_card.state == CardState.ITEM
    
    # 5. Verify Hero Stats
    # Should have +1 Movement
    assert h1.items.get(StatType.MOVEMENT) == 1

def test_movement_bonus_application(item_state):
    # Pre-condition: Grant item manually
    h1 = item_state.teams[TeamColor.RED].heroes[0]
    h1.items[StatType.MOVEMENT] = 1
    
    # Set Phase to RESOLUTION to simulate playing a card
    item_state.phase = GamePhase.RESOLUTION
    item_state.resolution_queue = [(h1.id, h1.hand[0])] # Card: Move 2
    
    # Trigger ResolveNext to generate Choice Request
    from goa2.engine.actions import ResolveNextCommand
    ResolveNextCommand().execute(item_state)
    
    # Check Stack for Action Choice
    assert len(item_state.input_stack) == 1
    assert item_state.input_stack[-1].request_type == InputRequestType.ACTION_CHOICE
    
    # Execute ChooseActionCommand(MOVEMENT)
    cmd = ChooseActionCommand(ActionType.MOVEMENT)
    cmd.execute(item_state)
    
    # Check Stack for Movement Input
    assert item_state.input_stack[-1].request_type == InputRequestType.MOVEMENT_HEX
    
    # CHECK CONTEXT: max_steps should be 2 (Base) + 1 (Item) = 3
    max_steps = item_state.input_stack[-1].context.get("max_steps")
    assert max_steps == 3

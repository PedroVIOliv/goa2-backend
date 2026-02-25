import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType, Card, CardTier, CardColor, ActionType
from goa2.domain.hex import Hex
from goa2.engine.steps import ResolveCardStep
from goa2.engine.handler import process_resolution_stack, push_steps

@pytest.fixture
def effect_state():
    board = Board()
    z1 = Zone(id="z1", hexes={Hex(q=0,r=0,s=0), Hex(q=1,r=0,s=-1), Hex(q=2,r=0,s=-2), Hex(q=3,r=0,s=-3)}, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()
    
    # Hero A at 0,0,0
    hero = Hero(id="A", name="Arien", team=TeamColor.RED, deck=[], level=1)
    card = Card(
        id="arcane_whirlpool",
        name="Arcane Whirlpool",
        tier=CardTier.II,
        color=CardColor.GREEN,
        initiative=4,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        is_ranged=True,
        range_value=4,
        effect_id="arcane_whirlpool",
        effect_text="Swap with an enemy minion in range.",
        is_facedown=False
    )
    hero.current_turn_card = card
    
    # Enemy Minion M1 at 2,0,-2
    minion = Minion(id="M1", name="M1", type=MinionType.MELEE, team=TeamColor.BLUE)
    
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[minion])
        }
    )
    # Use Unified Placement
    state.place_entity("A", Hex(q=0,r=0,s=0))
    state.place_entity("M1", Hex(q=2,r=0,s=-2))
    state.current_actor_id = "A"
    
    return state

def test_arcane_whirlpool_swap(effect_state):
    # 1. Start ResolveCardStep
    step = ResolveCardStep(hero_id="A")
    push_steps(effect_state, [step])
    
    # 2. CHOOSE_ACTION
    req = process_resolution_stack(effect_state)
    assert req["type"] == "CHOOSE_ACTION"
    
    # 3. Select SKILL (which is Arcane Whirlpool)
    effect_state.execution_stack[-1].pending_input = {"selection": "SKILL"}
    
    # 4. ResolveCardStep finishes -> spawns ResolveCardTextStep
    # ResolveCardTextStep runs -> spawns SelectStep (from effect)
    req = process_resolution_stack(effect_state)
    assert req["type"] == "SELECT_UNIT"
    assert "M1" in req["valid_options"]
    
    # 5. Provide Input: Select M1
    effect_state.execution_stack[-1].pending_input = {"selection": "M1"}
    
    # 6. SelectStep finishes -> spawns SwapWithSelectedStep
    # SwapWithSelectedStep runs -> spawns SwapUnitsStep
    # SwapUnitsStep runs and finishes.
    res = process_resolution_stack(effect_state)
    assert res is None # Stack finished
    
    # 7. Verify Positions
    assert effect_state.entity_locations["A"] == Hex(q=2,r=0,s=-2)
    assert effect_state.entity_locations["M1"] == Hex(q=0,r=0,s=0)

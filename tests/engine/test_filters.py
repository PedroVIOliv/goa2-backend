import pytest
from goa2.domain.state import GameState
from goa2.domain.board import Board
from goa2.domain.tile import Tile
from goa2.domain.models import Team, TeamColor, Hero, Minion, MinionType
from goa2.domain.hex import Hex
from goa2.engine.steps import SelectStep
from goa2.engine.filters import RangeFilter, TeamFilter, OccupiedFilter, UnitTypeFilter

@pytest.fixture
def filter_state():
    board = Board()
    # Create a small grid
    hexes = [Hex(q=0,r=0,s=0), Hex(q=1,r=0,s=-1), Hex(q=2,r=0,s=-2), Hex(q=1,r=-1,s=0)]
    for h in hexes:
        board.tiles[h] = Tile(hex=h)
        
    h1 = Hero(id="h1", name="H1", team=TeamColor.RED, deck=[])
    h2 = Hero(id="h2", name="H2", team=TeamColor.BLUE, deck=[])
    m1 = Minion(id="m1", name="M1", type=MinionType.MELEE, team=TeamColor.BLUE)
    
    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[h2], minions=[m1])
        },
        entity_locations={},
        current_actor_id="h1"
    )
    # Use Unified Placement (Syncs cache automatically)
    state.place_entity("h1", Hex(q=0, r=0, s=0))
    state.place_entity("h2", Hex(q=2, r=0, s=-2))
    state.place_entity("m1", Hex(q=1, r=0, s=-1))
    
    return state

def test_range_filter(filter_state):
    # Select Units in Range 1 (Should be M1 only)
    step = SelectStep(
        target_type="UNIT",
        prompt="Test",
        filters=[RangeFilter(max_range=1)]
    )
    res = step.resolve(filter_state, {})
    
    assert res.requires_input
    valid = res.input_request["valid_options"]
    assert "m1" in valid
    assert "h1" in valid # Range 0 is usually included unless min_range=1
    assert "h2" not in valid # Range 2

def test_team_filter(filter_state):
    # Select Enemy Units (H2, M1)
    step = SelectStep(
        target_type="UNIT",
        prompt="Test",
        filters=[TeamFilter(relation="ENEMY")]
    )
    res = step.resolve(filter_state, {})
    valid = res.input_request["valid_options"]
    
    assert "h2" in valid
    assert "m1" in valid
    assert "h1" not in valid

def test_composite_filter(filter_state):
    # Select Enemy Minion in Range 1 (Should be M1 only)
    step = SelectStep(
        target_type="UNIT",
        prompt="Test",
        filters=[
            TeamFilter(relation="ENEMY"),
            UnitTypeFilter(unit_type="MINION"),
            RangeFilter(max_range=1)
        ]
    )
    res = step.resolve(filter_state, {})
    valid = res.input_request["valid_options"]
    
    assert ["m1"] == valid

def test_hex_filter_occupied(filter_state):
    # Select Empty Hex in Range 1 (Should be (1,-1,0))
    # (0,0,0) is H1, (1,0,-1) is M1. (1,-1,0) is empty.
    
    step = SelectStep(
        target_type="HEX",
        prompt="Test",
        filters=[
            RangeFilter(max_range=1),
            OccupiedFilter(is_occupied=False)
        ]
    )
    res = step.resolve(filter_state, {})
    valid = res.input_request["valid_options"]
    
    target_hex = Hex(q=1, r=-1, s=0)
    assert target_hex in valid
    assert Hex(q=0, r=0, s=0) not in valid # Occupied
    assert Hex(q=1, r=0, s=-1) not in valid # Occupied

def test_auto_select(filter_state):
    # Only one enemy minion exists. Auto-select it.
    step = SelectStep(
        target_type="UNIT",
        prompt="Test",
        filters=[
            UnitTypeFilter(unit_type="MINION"),
            TeamFilter(relation="ENEMY")
        ],
        auto_select_if_one=True
    )
    context = {}
    res = step.resolve(filter_state, context)
    
    assert res.is_finished
    assert context["selection"] == "m1"

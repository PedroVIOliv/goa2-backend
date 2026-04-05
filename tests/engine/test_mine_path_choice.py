from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.tile import Tile
from goa2.domain.state import GameState
from goa2.domain.models import Team, TeamColor, Hero, Token, TokenType
from goa2.domain.types import HeroID, BoardEntityID
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.engine.steps import MoveSequenceStep


def _make_diamond_state():
    """
    Board:
      (0,0,0) --- (1,-1,0) [mine_A] --- (2,-1,-1)
          |                               /
       (0,1,-1)                         /
          \\                           /
           (1,0,-1) [mine_B] ---------

    Hero at (0,0,0), movement 3.
    To reach (2,-1,-1): through mine_A or mine_B - player must choose.
    """
    board = Board()
    for h in [
        Hex(q=0, r=0, s=0),
        Hex(q=1, r=-1, s=0),
        Hex(q=2, r=-1, s=-1),
        Hex(q=0, r=1, s=-1),
        Hex(q=1, r=0, s=-1),
    ]:
        board.tiles[h] = Tile(hex=h)

    hero = Hero(id=HeroID("hero_a"), name="A", team=TeamColor.BLUE, deck=[])
    mine_owner = Hero(id=HeroID("hero_min"), name="Min", team=TeamColor.RED, deck=[])
    state = GameState(
        board=board,
        teams={
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[hero], minions=[]),
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[mine_owner], minions=[]),
        },
        current_actor_id=HeroID("hero_a"),
    )
    state.place_entity(BoardEntityID("hero_a"), Hex(q=0, r=0, s=0))

    for mine_id, ttype, hex_pos in [
        ("mine_A", TokenType.MINE_BLAST, Hex(q=1, r=-1, s=0)),
        ("mine_B", TokenType.MINE_DUD, Hex(q=1, r=0, s=-1)),
    ]:
        mine = Token(
            id=BoardEntityID(mine_id),
            name="Mine",
            token_type=ttype,
            owner_id=HeroID("hero_min"),
            is_passable=True,
            is_facedown=True,
        )
        state.token_pool.setdefault(ttype, []).append(mine)
        state.misc_entities[BoardEntityID(mine_id)] = mine
        state.place_entity(BoardEntityID(mine_id), hex_pos)

    return state


def test_mine_path_choice_prompted():
    """When destination has multiple mine paths, player is prompted to choose."""
    state = _make_diamond_state()
    push_steps(state, [MoveSequenceStep(range_val=3)])

    req = process_resolution_stack(state)
    assert req["type"] == "SELECT_HEX"

    state.execution_stack[-1].pending_input = {"selection": {"q": 2, "r": -1, "s": -1}}
    req = process_resolution_stack(state)

    assert req is not None
    assert req["type"] == "SELECT_OPTION"
    options = req["options"]
    assert len(options) == 3  # mine_A only, mine_B only, both
    # Verify no mine IDs are leaked in metadata
    for o in options:
        assert "mine_ids" not in o["metadata"]
        assert "mine_count" in o["metadata"]
    mine_counts = sorted(o["metadata"]["mine_count"] for o in options)
    assert mine_counts == [1, 1, 2]


def test_mine_path_choice_select_then_move():
    """Full flow: select hex, choose mine path, then move triggers mine."""
    state = _make_diamond_state()
    push_steps(state, [MoveSequenceStep(range_val=3)])

    req = process_resolution_stack(state)
    assert req["type"] == "SELECT_HEX"

    state.execution_stack[-1].pending_input = {"selection": {"q": 2, "r": -1, "s": -1}}
    req = process_resolution_stack(state)
    assert req["type"] == "SELECT_OPTION"

    # Pick whichever option index corresponds to mine_A path
    opts = req["options"]
    choice_idx = next(
        o["id"] for o in opts
        if any(
            h == {"q": 1, "r": -1, "s": 0}
            for h in o["metadata"]["mine_hexes"]
        )
    )
    state.execution_stack[-1].pending_input = {"selection": choice_idx}
    process_resolution_stack(state)

    assert state.entity_locations[BoardEntityID("hero_a")] == Hex(q=2, r=-1, s=-1)
    assert BoardEntityID("mine_A") not in state.entity_locations


def test_single_mine_path_no_choice():
    """When only one mine path exists, skip choice and auto-proceed."""
    board = Board()
    for h in [Hex(q=0, r=0, s=0), Hex(q=1, r=-1, s=0), Hex(q=2, r=-2, s=0)]:
        board.tiles[h] = Tile(hex=h)

    hero = Hero(id=HeroID("hero_a"), name="A", team=TeamColor.BLUE, deck=[])
    mine_owner = Hero(id=HeroID("hero_min"), name="Min", team=TeamColor.RED, deck=[])
    state = GameState(
        board=board,
        teams={
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[hero], minions=[]),
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[mine_owner], minions=[]),
        },
        current_actor_id=HeroID("hero_a"),
    )
    state.place_entity(BoardEntityID("hero_a"), Hex(q=0, r=0, s=0))

    mine = Token(
        id=BoardEntityID("mine_1"),
        name="Mine",
        token_type=TokenType.MINE_BLAST,
        owner_id=HeroID("hero_min"),
        is_passable=True,
    )
    state.token_pool[TokenType.MINE_BLAST] = [mine]
    state.misc_entities[BoardEntityID("mine_1")] = mine
    state.place_entity(BoardEntityID("mine_1"), Hex(q=1, r=-1, s=0))

    push_steps(state, [MoveSequenceStep(range_val=2)])

    req = process_resolution_stack(state)
    assert req["type"] == "SELECT_HEX"

    state.execution_stack[-1].pending_input = {"selection": {"q": 2, "r": -2, "s": 0}}
    req = process_resolution_stack(state)

    assert state.entity_locations[BoardEntityID("hero_a")] == Hex(q=2, r=-2, s=0)
    assert BoardEntityID("mine_1") not in state.entity_locations

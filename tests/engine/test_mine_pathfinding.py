from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.tile import Tile
from goa2.domain.state import GameState
from goa2.domain.models import Team, TeamColor, Hero, Token, TokenType
from goa2.domain.types import HeroID, BoardEntityID
from goa2.engine.rules import find_reachable_with_mines


def _mine_sets(options):
    """Extract just the mine_ids sets from MinePathOption list for easy assertion."""
    return [opt.mine_ids for opt in options]


def _make_line_board(length: int) -> Board:
    board = Board()
    for i in range(length):
        h = Hex(q=i, r=-i, s=0)
        board.tiles[h] = Tile(hex=h)
    return board


def _make_state(board: Board) -> GameState:
    hero = Hero(id=HeroID("hero_a"), name="A", team=TeamColor.BLUE, deck=[])
    state = GameState(
        board=board,
        teams={TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[hero], minions=[])},
        current_actor_id=HeroID("hero_a"),
    )
    state.place_entity(BoardEntityID("hero_a"), Hex(q=0, r=0, s=0))
    return state


def _place_mine(state: GameState, mine_id: str, token_type: TokenType, hex: Hex):
    mine = Token(
        id=BoardEntityID(mine_id),
        name="Mine",
        token_type=token_type,
        is_passable=True,
    )
    pool = state.token_pool.setdefault(token_type, [])
    pool.append(mine)
    state.misc_entities[BoardEntityID(mine_id)] = mine
    state.place_entity(BoardEntityID(mine_id), hex)


def test_no_mines_all_reachable():
    board = _make_line_board(4)
    state = _make_state(board)

    result = find_reachable_with_mines(
        board=board,
        start=Hex(q=0, r=0, s=0),
        max_steps=3,
        state=state,
        actor_id="hero_a",
    )
    assert Hex(q=1, r=-1, s=0) in result
    assert _mine_sets(result[Hex(q=1, r=-1, s=0)]) == [set()]


def test_mine_blocks_but_traversable():
    board = _make_line_board(4)
    state = _make_state(board)
    _place_mine(state, "mine_1", TokenType.MINE_BLAST, Hex(q=1, r=-1, s=0))

    result = find_reachable_with_mines(
        board=board,
        start=Hex(q=0, r=0, s=0),
        max_steps=3,
        state=state,
        actor_id="hero_a",
    )
    assert Hex(q=1, r=-1, s=0) not in result
    assert Hex(q=2, r=-2, s=0) in result
    assert _mine_sets(result[Hex(q=2, r=-2, s=0)]) == [{"mine_1"}]


def test_reachable_without_mine_has_empty_set():
    """
    Destination reachable via a clean path (0 mines) and via a mine path (1 mine).
    Both options should be returned so the player can choose to trigger mines.

    Linear board: mine at (2,-2,0). Hex (1,-1,0) is reachable clean (set())
    but also via a longer path through the mine.
    """
    board = _make_line_board(4)
    state = _make_state(board)
    _place_mine(state, "mine_1", TokenType.MINE_BLAST, Hex(q=2, r=-2, s=0))

    result = find_reachable_with_mines(
        board=board,
        start=Hex(q=0, r=0, s=0),
        max_steps=3,
        state=state,
        actor_id="hero_a",
    )
    assert Hex(q=1, r=-1, s=0) in result
    sets = _mine_sets(result[Hex(q=1, r=-1, s=0)])
    assert set() in sets  # Clean path always available


def test_two_paths_different_mines():
    """
    Two paths to same destination, each through a different mine.
    Both mines are on the only routes to the destination.

    Board:
      (0,0,0) --- (1,-1,0) [mine_A] --- (2,-1,-1)
          |                               /
       (0,1,-1)                         /
          \\                           /
           (1,0,-1) [mine_B] ---------

    (2,-1,-1) is a neighbor of both (1,-1,0) and (1,0,-1).
    To reach (2,-1,-1), you MUST pass through a mine.
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
    state = _make_state(board)
    _place_mine(state, "mine_A", TokenType.MINE_BLAST, Hex(q=1, r=-1, s=0))
    _place_mine(state, "mine_B", TokenType.MINE_DUD, Hex(q=1, r=0, s=-1))

    result = find_reachable_with_mines(
        board=board,
        start=Hex(q=0, r=0, s=0),
        max_steps=3,
        state=state,
        actor_id="hero_a",
    )
    dest = Hex(q=2, r=-1, s=-1)
    options = result[dest]
    sets = _mine_sets(options)
    # All distinct mine sets: each single mine + both together
    assert {"mine_A"} in sets
    assert {"mine_B"} in sets
    assert {"mine_A", "mine_B"} in sets


def test_no_path_without_mine():
    board = _make_line_board(3)
    state = _make_state(board)
    _place_mine(state, "mine_1", TokenType.MINE_BLAST, Hex(q=1, r=-1, s=0))

    result = find_reachable_with_mines(
        board=board,
        start=Hex(q=0, r=0, s=0),
        max_steps=2,
        state=state,
        actor_id="hero_a",
    )
    assert Hex(q=2, r=-2, s=0) in result
    assert _mine_sets(result[Hex(q=2, r=-2, s=0)]) == [{"mine_1"}]


def test_multiple_mines_on_single_path():
    board = _make_line_board(4)
    state = _make_state(board)
    _place_mine(state, "mine_1", TokenType.MINE_BLAST, Hex(q=1, r=-1, s=0))
    _place_mine(state, "mine_2", TokenType.MINE_DUD, Hex(q=2, r=-2, s=0))

    result = find_reachable_with_mines(
        board=board,
        start=Hex(q=0, r=0, s=0),
        max_steps=3,
        state=state,
        actor_id="hero_a",
    )
    assert Hex(q=3, r=-3, s=0) in result
    assert _mine_sets(result[Hex(q=3, r=-3, s=0)]) == [{"mine_1", "mine_2"}]
    assert Hex(q=1, r=-1, s=0) not in result
    assert Hex(q=2, r=-2, s=0) not in result

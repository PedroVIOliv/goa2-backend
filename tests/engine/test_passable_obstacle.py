from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.tile import Tile
from goa2.domain.state import GameState
from goa2.domain.models import Team, TeamColor, Hero, Token, TokenType
from goa2.domain.types import HeroID, BoardEntityID


def _make_state():
    board = Board()
    for h in [Hex(q=0, r=0, s=0), Hex(q=1, r=-1, s=0), Hex(q=2, r=-2, s=0)]:
        board.tiles[h] = Tile(hex=h)

    hero = Hero(id=HeroID("hero_a"), name="A", team=TeamColor.RED, deck=[])
    state = GameState(
        board=board,
        teams={TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[])},
    )
    return state


def test_passable_token_is_obstacle():
    """Passable tokens are still obstacles (can't land on them)."""
    state = _make_state()
    mine = Token(
        id=BoardEntityID("mine_1"),
        name="Mine",
        token_type=TokenType.MINE_BLAST,
        is_passable=True,
    )
    state.token_pool[TokenType.MINE_BLAST] = [mine]
    state.place_entity(BoardEntityID("mine_1"), Hex(q=1, r=-1, s=0))

    assert state.validator.is_obstacle_for_actor(state, Hex(q=1, r=-1, s=0)) is True


def test_passable_token_detected():
    """is_passable_token returns True for passable token hexes."""
    state = _make_state()
    mine = Token(
        id=BoardEntityID("mine_1"),
        name="Mine",
        token_type=TokenType.MINE_BLAST,
        is_passable=True,
    )
    state.token_pool[TokenType.MINE_BLAST] = [mine]
    state.place_entity(BoardEntityID("mine_1"), Hex(q=1, r=-1, s=0))

    assert state.validator.is_passable_token(state, Hex(q=1, r=-1, s=0)) is True


def test_non_passable_token_not_detected():
    """is_passable_token returns False for non-passable tokens."""
    state = _make_state()
    smoke = Token(
        id=BoardEntityID("smoke_1"),
        name="Smoke",
        token_type=TokenType.SMOKE_BOMB,
        is_passable=False,
    )
    state.token_pool[TokenType.SMOKE_BOMB] = [smoke]
    state.place_entity(BoardEntityID("smoke_1"), Hex(q=1, r=-1, s=0))

    assert state.validator.is_passable_token(state, Hex(q=1, r=-1, s=0)) is False


def test_empty_hex_not_passable_token():
    """Empty hexes are not passable tokens."""
    state = _make_state()
    assert state.validator.is_passable_token(state, Hex(q=1, r=-1, s=0)) is False

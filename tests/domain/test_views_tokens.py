from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.tile import Tile
from goa2.domain.state import GameState
from goa2.domain.models import Team, TeamColor, Hero, Token, TokenType
from goa2.domain.types import HeroID, BoardEntityID
from goa2.domain.views import build_view


def _make_state_with_mine():
    board = Board()
    board.tiles[Hex(q=0, r=0, s=0)] = Tile(hex=Hex(q=0, r=0, s=0))
    board.tiles[Hex(q=1, r=-1, s=0)] = Tile(hex=Hex(q=1, r=-1, s=0))

    hero_red = Hero(id=HeroID("hero_red"), name="Red", team=TeamColor.RED, deck=[])
    hero_blue = Hero(id=HeroID("hero_blue"), name="Blue", team=TeamColor.BLUE, deck=[])

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero_red], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[hero_blue], minions=[]),
        },
    )

    mine = Token(
        id=BoardEntityID("mine_blast_1"),
        name="Mine",
        token_type=TokenType.MINE_BLAST,
        owner_id=HeroID("hero_red"),
        is_facedown=True,
        is_passable=True,
    )
    state.token_pool[TokenType.MINE_BLAST] = [mine]
    state.place_entity(BoardEntityID("mine_blast_1"), Hex(q=1, r=-1, s=0))
    return state


def test_facedown_token_hidden_from_enemy():
    """Enemy sees 'mine' not 'mine_blast'."""
    state = _make_state_with_mine()
    view = build_view(state, for_hero_id=HeroID("hero_blue"))
    token_view = view["tokens"][0]
    assert token_view["token_type"] == "mine"
    assert token_view["is_facedown"] is True


def test_facedown_token_visible_to_owner():
    """Owner sees actual token_type."""
    state = _make_state_with_mine()
    view = build_view(state, for_hero_id=HeroID("hero_red"))
    token_view = view["tokens"][0]
    assert token_view["token_type"] == "mine_blast"
    assert token_view["is_facedown"] is True


def test_facedown_token_hidden_from_spectator():
    """Spectator sees 'mine' not 'mine_blast'."""
    state = _make_state_with_mine()
    view = build_view(state, for_hero_id=None)
    token_view = view["tokens"][0]
    assert token_view["token_type"] == "mine"


def test_faceup_token_visible_to_all():
    """Non-facedown tokens show real type to everyone."""
    state = _make_state_with_mine()
    state.token_pool[TokenType.MINE_BLAST][0].is_facedown = False
    view = build_view(state, for_hero_id=HeroID("hero_blue"))
    token_view = view["tokens"][0]
    assert token_view["token_type"] == "mine_blast"

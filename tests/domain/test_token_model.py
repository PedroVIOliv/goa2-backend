from goa2.domain.models.token import Token
from goa2.domain.models.enums import TokenType
from goa2.domain.types import BoardEntityID
import goa2.engine.step_types  # noqa: F401 — triggers model patching for serialization


def test_token_passable_default_false():
    t = Token(
        id=BoardEntityID("smoke_1"), name="Smoke", token_type=TokenType.SMOKE_BOMB
    )
    assert t.is_passable is False


def test_token_mine_blast_passable():
    t = Token(
        id=BoardEntityID("mine_1"),
        name="Mine",
        token_type=TokenType.MINE_BLAST,
        is_passable=True,
    )
    assert t.is_passable is True


def test_token_facedown_default_false():
    t = Token(
        id=BoardEntityID("smoke_1"), name="Smoke", token_type=TokenType.SMOKE_BOMB
    )
    assert t.is_facedown is False


def test_token_mine_facedown():
    t = Token(
        id=BoardEntityID("mine_1"),
        name="Mine",
        token_type=TokenType.MINE_BLAST,
        is_facedown=True,
    )
    assert t.is_facedown is True


def test_misc_entities_survive_serialization_roundtrip():
    """Tokens in misc_entities must remain Token instances after JSON round-trip
    (simulates rollback). Without AnyMiscEntity, they become plain dicts and
    is_passable checks break."""
    from goa2.domain.state import GameState
    from goa2.domain.board import Board
    from goa2.domain.hex import Hex
    from goa2.domain.tile import Tile
    from goa2.domain.models import Team, TeamColor, Hero
    from goa2.domain.types import HeroID

    board = Board()
    board.tiles[Hex(q=0, r=0, s=0)] = Tile(hex=Hex(q=0, r=0, s=0))

    hero = Hero(id=HeroID("hero_a"), name="A", team=TeamColor.BLUE, deck=[])
    state = GameState(
        board=board,
        teams={TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[hero], minions=[])},
    )

    mine = Token(
        id=BoardEntityID("mine_1"), name="Mine",
        token_type=TokenType.MINE_BLAST, is_passable=True, is_facedown=True,
    )
    state.misc_entities[BoardEntityID("mine_1")] = mine
    state.place_entity(BoardEntityID("mine_1"), Hex(q=0, r=0, s=0))

    # Round-trip through JSON (same as rollback)
    snapshot = state.model_dump(mode="json")
    restored = GameState.model_validate(snapshot)

    entity = restored.get_entity(BoardEntityID("mine_1"))
    assert isinstance(entity, Token), f"Expected Token, got {type(entity)}"
    assert entity.is_passable is True
    assert restored.validator.is_passable_token(restored, Hex(q=0, r=0, s=0))

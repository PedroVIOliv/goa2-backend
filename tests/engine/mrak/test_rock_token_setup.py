"""Rock token supply and persistence setup (Mrak)."""

from __future__ import annotations

from goa2.domain.board import Board
from goa2.domain.models import Team, TeamColor, TokenType
from goa2.domain.models.token import TOKEN_SUPPLY
from goa2.domain.state import GameState
from goa2.engine.setup import GameSetup


def _state() -> GameState:
    return GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        },
    )


def test_rock_token_supply_is_three() -> None:
    assert TOKEN_SUPPLY[TokenType.ROCK] == 3


def test_rock_tokens_do_not_persist_and_block_movement() -> None:
    state = _state()
    GameSetup._initialize_token_pool(state)

    rocks = state.token_pool[TokenType.ROCK]
    assert len(rocks) == 3
    for rock in rocks:
        # Removed at end of round (not in the persists list).
        assert rock.persists_end_of_round is False
        # Rocks are obstacles that block movement.
        assert rock.is_passable is False

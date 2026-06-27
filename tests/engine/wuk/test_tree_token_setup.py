"""Tree token supply and persistence setup (Wuk)."""

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


def test_tree_token_supply_is_three() -> None:
    assert TOKEN_SUPPLY[TokenType.TREE] == 3


def test_tree_tokens_persist_and_block_movement() -> None:
    state = _state()
    GameSetup._initialize_token_pool(state)

    trees = state.token_pool[TokenType.TREE]
    assert len(trees) == 3
    for tree in trees:
        assert tree.persists_end_of_round is True
        assert tree.is_passable is False

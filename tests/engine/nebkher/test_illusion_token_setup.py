"""Illusion token supply and standard-token properties (NebKher).

Locked interpretation (2026-07-07): supply 3; standard tokens — obstacle,
non-passable, removed at end of round.
"""

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


def test_illusion_token_supply_is_three() -> None:
    assert TOKEN_SUPPLY[TokenType.ILLUSION] == 3


def test_illusion_tokens_do_not_persist_and_block_movement() -> None:
    state = _state()
    GameSetup._initialize_token_pool(state)

    illusions = state.token_pool[TokenType.ILLUSION]
    assert len(illusions) == 3
    for token in illusions:
        # Removed at end of round (not in the persists list).
        assert token.persists_end_of_round is False
        # Standard obstacle token: blocks movement, not passable.
        assert token.is_passable is False

"""F0c — Magma token: Ignatia's obstacle token.

Locked rulings: new TokenType.MAGMA, supply 4, does NOT persist end of round,
plain obstacle (is_passable=False), does not block LOS.
"""

from goa2.domain.models import TOKEN_SUPPLY, TokenType
from goa2.engine.setup import GameSetup


def test_magma_token_registered_with_supply_four():
    assert TokenType.MAGMA in TokenType
    assert TOKEN_SUPPLY[TokenType.MAGMA] == 4


def test_magma_pool_initialized_at_setup():
    state = GameSetup.create_game("src/goa2/data/maps/forgotten_island.json", ["Arien"], ["Wasp"])
    assert len(state.token_pool[TokenType.MAGMA]) == 4
    # Plain obstacle: not passable, not facedown.
    magma = state.token_pool[TokenType.MAGMA][0]
    assert magma.is_passable is False
    assert magma.is_facedown is False
    assert magma.persists_end_of_round is False

"""Server-specific exception classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from goa2.domain.state import GameState


class GameNotFoundError(Exception):
    """Raised when a game_id doesn't exist in the registry."""

    def __init__(self, game_id: str):
        self.game_id = game_id
        super().__init__(f"Game '{game_id}' not found")


class CardNotInHandError(Exception):
    """Raised when a card_id isn't in the hero's hand."""

    def __init__(self, card_id: str, hero_id: str):
        self.card_id = card_id
        self.hero_id = hero_id
        super().__init__(f"Card '{card_id}' not in {hero_id}'s hand")


class InvalidPhaseError(Exception):
    """Raised when an operation is attempted in the wrong game phase."""

    def __init__(self, expected: str, actual: str):
        self.expected = expected
        self.actual = actual
        super().__init__(f"Expected phase {expected}, but game is in {actual}")


class AlreadyCommittedError(Exception):
    """Raised when a hero tries to commit a card twice in the same turn."""

    def __init__(self, hero_id: str):
        self.hero_id = hero_id
        super().__init__(f"{hero_id} has already committed a card this turn")


class NotYourTurnError(Exception):
    """Raised when a player submits input meant for another player."""

    def __init__(self, authenticated_hero: str, expected_hero: str):
        self.authenticated_hero = authenticated_hero
        self.expected_hero = expected_hero
        super().__init__(
            f"Input expected from '{expected_hero}', not '{authenticated_hero}'"
        )


def validate_input_turn(expected: str, hero_id: str, state: GameState) -> None:
    """Check that hero_id is allowed to respond to the current input request.

    Supports:
    - ``"simultaneous"`` – anyone may respond
    - exact hero id match
    - ``"team:RED"`` / ``"team:BLUE"`` – any hero on that team
    """
    if expected == "simultaneous" or expected == hero_id:
        return
    if expected.startswith("team:"):
        team_name = expected[5:]
        from goa2.domain.types import HeroID

        hero = state.get_hero(HeroID(hero_id))
        if hero and hero.team.value == team_name:
            return
    raise NotYourTurnError(hero_id, expected)

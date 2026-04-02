from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from goa2.domain.models import Minion, MinionType, TeamColor, Token, TokenType
from goa2.domain.types import BoardEntityID

if TYPE_CHECKING:
    from goa2.domain.state import GameState


class EntityFactory:
    """
    Central factory for creating Board Entities with guaranteed unique IDs.
    """

    @staticmethod
    def create_minion(state: GameState, team: TeamColor, m_type: MinionType) -> Minion:
        """
        Creates a new Minion with a unique ID.
        Format: minion_{seq}
        """
        uid = state.create_entity_id("minion")
        return Minion(
            id=BoardEntityID(uid),
            name=f"{team.name} {m_type.name} Minion",
            team=team,
            type=m_type,
        )

    @staticmethod
    def create_token(
        state: GameState,
        token_type: TokenType,
        name: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> Token:
        """
        Creates a new Token/Obstacle with a unique ID.
        Format: token_{seq}
        """
        uid = state.create_entity_id(token_type.value)
        owner = BoardEntityID(owner_id) if owner_id else None
        return Token(
            id=BoardEntityID(uid),
            name=name or token_type.value.replace("_", " ").title(),
            token_type=token_type,
            owner_id=owner,
        )

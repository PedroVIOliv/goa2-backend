from __future__ import annotations

from typing import TYPE_CHECKING

from goa2.domain.models import Minion, MinionType, TeamColor, Token, TokenType
from goa2.domain.types import BoardEntityID

if TYPE_CHECKING:
    from goa2.domain.state import GameState


class EntityFactory:
    """
    Central factory for creating Board Entities with guaranteed unique IDs.
    """

    @staticmethod
    def create_minion(
        state: GameState,
        team: TeamColor,
        m_type: MinionType,
        lane_id: str | None = None,
    ) -> Minion:
        """
        Creates a new Minion with a unique ID.
        Format: minion_{seq}
        Binds the minion to `lane_id` (defaults to the model's single-lane id).
        """
        uid = state.create_entity_id("minion")
        minion = Minion(
            id=BoardEntityID(uid),
            name=f"{team.name} {m_type.name} Minion",
            team=team,
            type=m_type,
        )
        if lane_id:
            minion.lane_id = lane_id
        return minion

    @staticmethod
    def create_token(
        state: GameState,
        token_type: TokenType,
        name: str,
        owner_id: str | None = None,
    ) -> Token:
        """
        Creates a new Token/Obstacle with a unique ID.
        Format: token_{seq}
        """
        uid = state.create_entity_id(token_type.value)
        owner = BoardEntityID(owner_id) if owner_id else None
        return Token(
            id=BoardEntityID(uid),
            name=name,
            token_type=token_type,
            owner_id=owner,
        )

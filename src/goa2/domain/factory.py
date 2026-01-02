from __future__ import annotations
from typing import TYPE_CHECKING
from goa2.domain.models import Minion, MinionType, TeamColor, Token
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
            id=uid,
            name=f"{team.name} {m_type.name} Minion",
            team=team,
            type=m_type
        )

    @staticmethod
    def create_token(state: GameState, name: str, owner_id: str = None) -> Token:
        """
        Creates a new Token/Obstacle with a unique ID.
        Format: token_{seq}
        """
        uid = state.create_entity_id("token")
        return Token(
            id=uid,
            name=name,
            owner_id=owner_id
        )

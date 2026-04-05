from __future__ import annotations
from typing import Literal, Optional
from goa2.domain.models.base import BoardEntity
from goa2.domain.models.enums import TokenType
from goa2.domain.types import HeroID


TOKEN_SUPPLY: dict[TokenType, int] = {
    TokenType.SMOKE_BOMB: 1,
    TokenType.GRENADE: 1,
    TokenType.MINE_BLAST: 2,
    TokenType.MINE_DUD: 2,
}


class Token(BoardEntity):
    """
    A BoardEntity that represents an object on the board that is NOT a Unit.
    Inherits `id` and `name` from GameEntity/BoardEntity.
    """

    entity_kind: Literal["token"] = "token"
    token_type: TokenType
    owner_id: Optional[HeroID] = None
    is_passable: bool = False
    is_facedown: bool = False

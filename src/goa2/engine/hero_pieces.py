"""Helpers for multi-piece heroes (Razzle): piece creation and supply."""

from __future__ import annotations

from goa2.domain.models import Hero
from goa2.domain.models.unit import HeroPiece
from goa2.domain.state import GameState
from goa2.domain.types import BoardEntityID


def piece_id(hero_id: str, index: int) -> str:
    """Stable board-entity ID for piece #index of a multi-piece hero."""
    return f"{hero_id}_piece_{index}"


def create_hero_pieces(state: GameState, hero: Hero) -> list[HeroPiece]:
    """Register all supply pieces for a multi-piece hero into misc_entities.

    Does NOT place them on the board. Idempotent: existing pieces are kept.
    """
    pieces: list[HeroPiece] = []
    for i in range(1, hero.piece_supply + 1):
        pid = BoardEntityID(piece_id(str(hero.id), i))
        existing = state.misc_entities.get(pid)
        if isinstance(existing, HeroPiece):
            pieces.append(existing)
            continue
        piece = HeroPiece(
            id=pid,
            name=hero.name,
            team=hero.team,
            owner_hero_id=str(hero.id),
        )
        state.register_entity(piece, "misc")
        pieces.append(piece)
    return pieces


def pieces_in_supply(state: GameState, hero: Hero) -> list[str]:
    """Piece IDs registered but not currently on the board."""
    return [
        piece_id(str(hero.id), i)
        for i in range(1, hero.piece_supply + 1)
        if BoardEntityID(piece_id(str(hero.id), i)) not in state.entity_locations
    ]

"""In-memory game registry mapping game_id -> ManagedGame."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

from fastapi import WebSocket

from goa2.engine.session import GameSession, SessionResult
from goa2.server.errors import GameNotFoundError


@dataclass
class ManagedGame:
    game_id: str
    session: GameSession
    player_tokens: Dict[str, str]  # token -> hero_id
    spectator_token: str
    hero_to_token: Dict[str, str]  # hero_id -> token (reverse)
    created_at: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_result: Optional[SessionResult] = None
    ws_connections: Dict[str, WebSocket] = field(default_factory=dict)


class GameRegistry:
    """Thread-safe in-memory store for active games."""

    def __init__(self) -> None:
        self._games: Dict[str, ManagedGame] = {}

    def create_game(self, session: GameSession, hero_ids: list[str]) -> ManagedGame:
        """Register a new game and generate tokens for each hero + spectator."""
        game_id = uuid.uuid4().hex[:12]
        player_tokens: Dict[str, str] = {}
        hero_to_token: Dict[str, str] = {}
        for hero_id in hero_ids:
            token = uuid.uuid4().hex
            player_tokens[token] = hero_id
            hero_to_token[hero_id] = token

        spectator_token = uuid.uuid4().hex

        game = ManagedGame(
            game_id=game_id,
            session=session,
            player_tokens=player_tokens,
            spectator_token=spectator_token,
            hero_to_token=hero_to_token,
        )
        self._games[game_id] = game
        return game

    def get(self, game_id: str) -> ManagedGame:
        """Get a game by ID or raise GameNotFoundError."""
        game = self._games.get(game_id)
        if game is None:
            raise GameNotFoundError(game_id)
        return game

    def resolve_token(self, token: str) -> Optional[tuple[str, str, bool]]:
        """Resolve a bearer token to (game_id, hero_id, is_spectator).

        Returns None if the token is unknown.
        """
        for game_id, game in self._games.items():
            if token in game.player_tokens:
                return (game_id, game.player_tokens[token], False)
            if token == game.spectator_token:
                return (game_id, "", True)
        return None

    def remove(self, game_id: str) -> None:
        self._games.pop(game_id, None)

    def __len__(self) -> int:
        return len(self._games)

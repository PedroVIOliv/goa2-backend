"""In-memory game registry mapping game_id -> ManagedGame."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

from fastapi import WebSocket

from goa2.engine.session import GameSession, SessionResult
from goa2.server.errors import GameNotFoundError

logger = logging.getLogger(__name__)


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
    """Thread-safe in-memory store for active games with optional file persistence."""

    def __init__(self, save_dir: Optional[str] = None) -> None:
        self._games: Dict[str, ManagedGame] = {}
        self._save_dir = save_dir

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

        if self._save_dir:
            self.save_game(game_id)

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
        if self._save_dir:
            from goa2.engine.persistence import delete_game_save

            delete_game_save(game_id, self._save_dir)

    def save_game(self, game_id: str) -> None:
        """Persist a game to disk. No-op if save_dir is not configured."""
        if not self._save_dir:
            return
        game = self._games.get(game_id)
        if game is None:
            return
        from goa2.engine.persistence import save_game

        try:
            save_game(
                game_id=game.game_id,
                state=game.session.state,
                player_tokens=game.player_tokens,
                spectator_token=game.spectator_token,
                hero_to_token=game.hero_to_token,
                created_at=game.created_at,
                save_dir=self._save_dir,
            )
        except Exception:
            logger.exception("Failed to save game %s", game_id)

    def restore_all(self) -> int:
        """Load all saved games from disk into the registry.

        Returns the number of games restored.
        """
        if not self._save_dir:
            return 0
        from goa2.engine.persistence import load_all_games

        games_data = load_all_games(self._save_dir)
        count = 0
        for data in games_data:
            game = ManagedGame(
                game_id=data["game_id"],
                session=data["session"],
                player_tokens=data["player_tokens"],
                spectator_token=data["spectator_token"],
                hero_to_token=data["hero_to_token"],
                created_at=data["created_at"],
                last_result=data["last_result"],
            )
            self._games[game.game_id] = game
            count += 1
            logger.info("Restored game %s", game.game_id)
        return count

    def __len__(self) -> int:
        return len(self._games)

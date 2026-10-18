"""In-memory game registry mapping game_id -> ManagedGame."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import WebSocket

from goa2.engine.session import GameSession, SessionResult
from goa2.server.errors import GameNotFoundError
from goa2.server.game_logger import GameLogger, create_game_logger
from goa2.server.replay import ReplayRecorder, create_replay_recorder

logger = logging.getLogger(__name__)

FINISHED_GAME_IDLE_SECONDS = 3600


@dataclass(frozen=True)
class UnloadedGame:
    """A finished game held only on disk: just enough to authenticate its tokens."""

    player_tokens: dict[str, str]
    spectator_token: str


@dataclass
class ManagedGame:
    game_id: str
    session: GameSession
    player_tokens: dict[str, str]  # token -> hero_id
    spectator_token: str
    hero_to_token: dict[str, str]  # hero_id -> token (reverse)
    # Display name per hero, from the draft lobby or manual creation. Empty is
    # the normal case for a game created without names.
    hero_names: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    outbound_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_result: SessionResult | None = None
    ws_connections: dict[str, WebSocket] = field(default_factory=dict)
    spectator_ws_connections: dict[int, WebSocket] = field(default_factory=dict)
    game_logger: GameLogger | None = None
    replay_recorder: ReplayRecorder | None = None
    timer_task: asyncio.Task[None] | None = None
    # Consensus-override negotiation state. Coordination, not game state:
    # never saved, never in views; unresolved proposals die on restart.
    # Typed loosely to avoid a registry <-> overrides import cycle
    # (OverrideProposal lives in server/overrides.py).
    pending_override: Any | None = None
    override_expiry_task: asyncio.Task[None] | None = None
    last_access: float = field(default_factory=time.monotonic)

    @property
    def current_responder(self) -> str | None:
        """The single source of truth for *who may act on the current input*.

        This is the ``player_id`` of the pending ``InputRequest`` — which
        already accounts for control remaps (under Hanu's ultimate the
        controlled action's inputs are addressed to the controller). Falls back
        to the current actor when there is no pending input. The submit-input
        and rollback paths (REST and WebSocket) authorize against this so their
        derivations cannot drift apart.
        """
        ir = self.last_result.input_request if self.last_result else None
        if ir is not None:
            return ir.player_id
        actor = self.session.state.current_actor_id
        return str(actor) if actor is not None else None


class GameRegistry:
    """Thread-safe in-memory store for active games with optional file persistence."""

    def __init__(self, save_dir: str | None = None) -> None:
        self._games: dict[str, ManagedGame] = {}
        self._unloaded: dict[str, UnloadedGame] = {}
        # Unloaded games are loaded back from worker threads (auth dependency,
        # WebSocket connect) so the slow load stays off the event loop.
        self._load_lock = threading.Lock()
        self._save_dir = save_dir

    def create_game(
        self,
        session: GameSession,
        hero_ids: list[str],
        game_id: str | None = None,
        hero_names: dict[str, str] | None = None,
    ) -> ManagedGame:
        """Register a new game and generate tokens for each hero + spectator."""
        game_id = game_id or uuid.uuid4().hex[:12]
        player_tokens: dict[str, str] = {}
        hero_to_token: dict[str, str] = {}
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
            hero_names=hero_names or {},
            game_logger=create_game_logger(game_id),
            replay_recorder=create_replay_recorder(game_id),
        )
        self._games[game_id] = game

        if self._save_dir:
            self.save_game(game_id)

        return game

    def get(self, game_id: str) -> ManagedGame:
        """Get a game by ID or raise GameNotFoundError."""
        game = self._games.get(game_id)
        if game is None:
            if game_id not in self._unloaded:
                raise GameNotFoundError(game_id)
            game = self._load_unloaded(game_id)
        game.last_access = time.monotonic()
        return game

    def is_loaded(self, game_id: str) -> bool:
        return game_id in self._games

    def _load_unloaded(self, game_id: str) -> ManagedGame:
        from goa2.engine.persistence import load_game

        with self._load_lock:
            game = self._games.get(game_id)
            if game is not None:
                return game
            assert self._save_dir is not None
            try:
                data = load_game(str(Path(self._save_dir) / f"{game_id}.json"))
            except Exception:
                logger.exception("Failed to load unloaded game %s", game_id)
                self._unloaded.pop(game_id, None)
                raise GameNotFoundError(game_id) from None
            game = self._managed_from_save(data)
            self._games[game_id] = game
            self._unloaded.pop(game_id, None)
            logger.info("Loaded finished game %s back into memory", game_id)
            return game

    def resolve_token(self, token: str) -> tuple[str, str, bool] | None:
        """Resolve a bearer token to (game_id, hero_id, is_spectator).

        Returns None if the token is unknown.
        """
        # Snapshots: a worker thread may load a game back while this iterates.
        holders: list[tuple[str, ManagedGame | UnloadedGame]] = [
            *list(self._games.items()),
            *list(self._unloaded.items()),
        ]
        for game_id, holder in holders:
            if token in holder.player_tokens:
                return (game_id, holder.player_tokens[token], False)
            if token == holder.spectator_token:
                return (game_id, "", True)
        return None

    def remove(self, game_id: str) -> None:
        self._unloaded.pop(game_id, None)
        game = self._games.pop(game_id, None)
        if game is not None and game.timer_task is not None:
            game.timer_task.cancel()
        if game is not None and game.override_expiry_task is not None:
            game.override_expiry_task.cancel()
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
                hero_names=game.hero_names,
                created_at=game.created_at,
                save_dir=self._save_dir,
                rollback_snapshot=game.session._rollback_snapshot,
                rollback_actor_id=game.session._rollback_actor_id,
                replay_log=game.replay_recorder.records if game.replay_recorder else None,
            )
        except Exception:
            logger.exception("Failed to save game %s", game_id)

    def restore_all(self) -> int:
        """Load saved games from disk into the registry.

        Finished games stay on disk as UnloadedGame entries and load on first
        access. Returns the number of games loaded into memory.
        """
        if not self._save_dir:
            return 0
        from goa2.engine.persistence import is_finished_payload, load_game_payload

        count = 0
        for file_path in sorted(Path(self._save_dir).glob("*.json")):
            try:
                with open(file_path) as f:
                    payload = json.load(f)
                if is_finished_payload(payload):
                    self._unloaded[payload["game_id"]] = UnloadedGame(
                        player_tokens=payload["player_tokens"],
                        spectator_token=payload["spectator_token"],
                    )
                    continue
                data = load_game_payload(payload)
            except Exception:
                logger.exception("Failed to load game from %s", file_path)
                continue
            game = self._managed_from_save(data)
            self._games[game.game_id] = game
            count += 1
            logger.info("Restored game %s", game.game_id)

        if self._unloaded:
            logger.info("Left %d finished game(s) on disk until accessed", len(self._unloaded))
        self._cleanup_orphaned_logs()
        return count

    def _managed_from_save(self, data: dict[str, Any]) -> ManagedGame:
        replay_recorder = create_replay_recorder(data["game_id"])
        if data["replay_log"] is not None:
            try:
                replay_recorder.restore_from_save(data["replay_log"])
            except Exception:
                logger.exception("Failed to restore replay log for game %s", data["game_id"])
        return ManagedGame(
            game_id=data["game_id"],
            session=data["session"],
            player_tokens=data["player_tokens"],
            spectator_token=data["spectator_token"],
            hero_to_token=data["hero_to_token"],
            hero_names=data["hero_names"],
            created_at=data["created_at"],
            last_result=data["last_result"],
            game_logger=create_game_logger(data["game_id"]),
            replay_recorder=replay_recorder,
        )

    async def unload_idle_finished_games(
        self, idle_seconds: float = FINISHED_GAME_IDLE_SECONDS
    ) -> int:
        """Drop finished games nobody has touched for idle_seconds from memory.

        Their save stays on disk and get() loads it back. Returns the number unloaded.
        """
        if not self._save_dir:
            return 0
        cutoff = time.monotonic() - idle_seconds
        unloaded = 0
        for game in list(self._games.values()):
            if not _is_idle_finished(game, cutoff):
                continue
            async with game.lock:
                if self._games.get(game.game_id) is not game or not _is_idle_finished(game, cutoff):
                    continue
                self._unloaded[game.game_id] = UnloadedGame(
                    player_tokens=dict(game.player_tokens),
                    spectator_token=game.spectator_token,
                )
                del self._games[game.game_id]
                if game.timer_task is not None:
                    game.timer_task.cancel()
                if game.override_expiry_task is not None:
                    game.override_expiry_task.cancel()
                if game.game_logger is not None:
                    game.game_logger.close()
            unloaded += 1
            logger.info("Unloaded idle finished game %s from memory", game.game_id)
        return unloaded

    def cleanup_stale_games(self, max_age_seconds: int = 86400) -> int:
        """Remove games whose save file hasn't been updated in max_age_seconds.

        Returns the number of games removed.
        """
        if not self._save_dir:
            return 0

        save_path = Path(self._save_dir)
        now = time.time()
        removed = 0

        for game_id in [*list(self._games), *list(self._unloaded)]:
            file_path = save_path / f"{game_id}.json"
            if file_path.is_file():
                mtime = file_path.stat().st_mtime
                if now - mtime > max_age_seconds:
                    logger.info(
                        "Removing stale game %s (last updated %.0f hours ago)",
                        game_id,
                        (now - mtime) / 3600,
                    )
                    self.remove(game_id)
                    removed += 1
            else:
                # No save file — remove from memory
                self.remove(game_id)
                removed += 1

        return removed

    def _cleanup_orphaned_logs(self) -> None:
        """Remove log files for games that no longer have a save file."""
        from goa2.server.game_logger import delete_game_logs

        log_dir = os.environ.get("GOA2_LOG_DIR", "logs/games")
        log_path = Path(log_dir)
        if not log_path.is_dir():
            return
        seen_ids: set[str] = set()
        for f in log_path.iterdir():
            if not f.is_file():
                continue
            # Extract game_id: either "{game_id}.log" or legacy "{game_id}_{ts}.log"
            game_id = f.stem.split("_")[0]
            if (
                game_id not in self._games
                and game_id not in self._unloaded
                and game_id not in seen_ids
            ):
                seen_ids.add(game_id)
                delete_game_logs(game_id, log_dir)
                logger.info("Cleaned up orphaned logs for game %s", game_id)

    def __len__(self) -> int:
        return len(self._games)

    def all_games(self) -> list[ManagedGame]:
        """Return a stable snapshot used to resume/cancel deadline tasks."""
        return list(self._games.values())


def _is_idle_finished(game: ManagedGame, cutoff: float) -> bool:
    return (
        game.session.state.is_game_over
        and not game.ws_connections
        and not game.spectator_ws_connections
        and game.pending_override is None
        and game.last_access <= cutoff
    )

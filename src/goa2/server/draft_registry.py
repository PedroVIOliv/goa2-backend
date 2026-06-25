"""In-memory game-draft registry mapping draft_id -> ManagedDraft."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from fastapi import WebSocket

from goa2.draft.errors import DraftNotFoundError
from goa2.draft.models import DraftState


@dataclass
class ManagedDraft:
    draft_id: str
    state: DraftState
    host_token: str
    spectator_token: str
    player_tokens: dict[str, str] = field(default_factory=dict)
    player_to_token: dict[str, str] = field(default_factory=dict)
    player_game_tokens: dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    ws_connections: dict[str, WebSocket] = field(default_factory=dict)


class DraftRegistry:
    """In-memory store for draft lobbies. No disk persistence."""

    def __init__(self) -> None:
        self._drafts: dict[str, ManagedDraft] = {}

    def create(self, state: DraftState, now: float | None = None) -> ManagedDraft:
        host_token = uuid.uuid4().hex
        md = ManagedDraft(
            draft_id=state.draft_id,
            state=state,
            host_token=host_token,
            spectator_token=uuid.uuid4().hex,
            created_at=now if now is not None else time.time(),
        )
        # Host is always p1.
        md.player_tokens[host_token] = "p1"
        md.player_to_token["p1"] = host_token
        self._drafts[state.draft_id] = md
        return md

    def get(self, draft_id: str) -> ManagedDraft:
        md = self._drafts.get(draft_id)
        if md is None:
            raise DraftNotFoundError(f"Draft '{draft_id}' not found")
        return md

    def add_player_token(self, draft_id: str, player_id: str) -> str:
        md = self.get(draft_id)
        token = uuid.uuid4().hex
        md.player_tokens[token] = player_id
        md.player_to_token[player_id] = token
        return token

    def resolve_token(self, token: str) -> tuple[str, str, bool, bool] | None:
        for draft_id, md in self._drafts.items():
            if token in md.player_tokens:
                player_id = md.player_tokens[token]
                return (draft_id, player_id, False, token == md.host_token)
            if token == md.spectator_token:
                return (draft_id, "", True, False)
        return None

    def remove(self, draft_id: str) -> None:
        self._drafts.pop(draft_id, None)

    def __len__(self) -> int:
        return len(self._drafts)

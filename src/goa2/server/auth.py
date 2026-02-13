"""Bearer-token authentication dependency for FastAPI."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request

from goa2.server.registry import GameRegistry


@dataclass
class PlayerContext:
    game_id: str
    hero_id: str
    is_spectator: bool


def get_registry(request: Request) -> GameRegistry:
    return request.app.state.registry


def get_current_player(
    request: Request, registry: GameRegistry = Depends(get_registry)
) -> PlayerContext:
    """Extract and validate bearer token, returning a PlayerContext."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth[len("Bearer "):]
    result = registry.resolve_token(token)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    game_id, hero_id, is_spectator = result

    # Verify the token belongs to the game in the URL (if path has game_id)
    path_game_id = request.path_params.get("game_id")
    if path_game_id and path_game_id != game_id:
        raise HTTPException(status_code=403, detail="Token does not match this game")

    return PlayerContext(game_id=game_id, hero_id=hero_id, is_spectator=is_spectator)

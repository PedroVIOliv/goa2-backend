"""API request/response Pydantic models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# -- Requests --


class CreateGameRequest(BaseModel):
    map_name: str = "forgotten_island"
    red_heroes: list[str]
    blue_heroes: list[str]
    cheats_enabled: bool = False
    game_type: str = "LONG"


class CommitCardRequest(BaseModel):
    card_id: str


class SubmitInputRequest(BaseModel):
    request_id: str = ""
    selection: Any = None


class GiveGoldRequest(BaseModel):
    hero_id: str
    amount: int


# -- Responses --


class HeroMetadata(BaseModel):
    id: str
    difficulty_stars: int


class PlayerToken(BaseModel):
    hero_id: str
    token: str


class CreateGameResponse(BaseModel):
    game_id: str
    player_tokens: list[PlayerToken]
    spectator_token: str


class GameViewResponse(BaseModel):
    """Wraps the dict returned by build_view."""

    view: dict[str, Any]
    input_request: dict[str, Any] | None = None
    winner: str | None = None


class ActionResultResponse(BaseModel):
    result_type: str
    current_phase: str
    events: list[dict[str, Any]] = []
    input_request: dict[str, Any] | None = None
    winner: str | None = None


class ErrorResponse(BaseModel):
    detail: str

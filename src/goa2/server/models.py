"""API request/response Pydantic models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# -- Requests --


class CreateGameRequest(BaseModel):
    map_name: str = "forgotten_island"
    red_heroes: List[str]
    blue_heroes: List[str]
    cheats_enabled: bool = False


class CommitCardRequest(BaseModel):
    card_id: str


class SubmitInputRequest(BaseModel):
    request_id: str = ""
    selection: Any = None


class GiveGoldRequest(BaseModel):
    hero_id: str
    amount: int


# -- Responses --


class PlayerToken(BaseModel):
    hero_id: str
    token: str


class CreateGameResponse(BaseModel):
    game_id: str
    player_tokens: List[PlayerToken]
    spectator_token: str


class GameViewResponse(BaseModel):
    """Wraps the dict returned by build_view."""

    view: Dict[str, Any]
    input_request: Optional[Dict[str, Any]] = None


class ActionResultResponse(BaseModel):
    result_type: str
    current_phase: str
    events: List[Dict[str, Any]] = []
    input_request: Optional[Dict[str, Any]] = None
    winner: Optional[str] = None


class ErrorResponse(BaseModel):
    detail: str

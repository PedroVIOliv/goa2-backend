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


# -- Draft requests --


class CreateDraftRequest(BaseModel):
    """Open a lobby. All match settings (map, game type, draft mode, cheats) and team
    sizes are decided inside the lobby, not here. The optional fields seed the defaults."""

    host_name: str
    map_name: str = "forgotten_island"
    game_type: str = "LONG"
    draft_mode: str = "sequential_ban_pick"
    cheats_enabled: bool = False


class UpdateDraftSettingsRequest(BaseModel):
    """Host-only, LOBBY-only. Any omitted field is left unchanged."""

    map_name: str | None = None
    game_type: str | None = None
    draft_mode: str | None = None
    cheats_enabled: bool | None = None


class JoinDraftRequest(BaseModel):
    display_name: str


class SetTeamRequest(BaseModel):
    team: str  # "RED" | "BLUE"


class SetCaptainRequest(BaseModel):
    player_id: str


class DraftActionRequest(BaseModel):
    hero: str


class ClaimHeroRequest(BaseModel):
    hero: str


# -- Draft responses --


class DraftModeInfo(BaseModel):
    name: str
    description: str


class CreateDraftResponse(BaseModel):
    draft_id: str
    player_id: str
    player_token: str
    spectator_token: str


class JoinDraftResponse(BaseModel):
    draft_id: str
    player_id: str
    player_token: str


class DraftViewResponse(BaseModel):
    draft: dict[str, Any]
    you: dict[str, Any] | None = None
    game_id: str | None = None
    game_token: str | None = None

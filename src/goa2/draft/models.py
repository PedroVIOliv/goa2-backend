from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from goa2.domain.models import TeamColor


class DraftStatus(StrEnum):
    LOBBY = "LOBBY"
    DRAFTING = "DRAFTING"
    CLAIMING = "CLAIMING"
    COMPLETE = "COMPLETE"


class DraftActionType(StrEnum):
    BAN = "BAN"
    PICK = "PICK"


class DraftPlayer(BaseModel):
    id: str
    display_name: str
    team: TeamColor | None = None
    is_host: bool = False
    is_captain: bool = False
    claimed_hero: str | None = None


class DraftStep(BaseModel):
    index: int
    action: DraftActionType
    team: TeamColor


def _empty_team_lists() -> dict[TeamColor, list[str]]:
    return {TeamColor.RED: [], TeamColor.BLUE: []}


class DraftState(BaseModel):
    draft_id: str
    status: DraftStatus = DraftStatus.LOBBY
    map_name: str
    game_type: str
    draft_mode: str
    cheats: bool = False
    # Team sizes are derived from membership at start_draft (no preset; 0 in LOBBY).
    red_size: int = 0
    blue_size: int = 0
    players: list[DraftPlayer] = Field(default_factory=list)
    hero_pool: list[str] = Field(default_factory=list)
    sequence: list[DraftStep] = Field(default_factory=list)
    current_index: int = 0
    bans: dict[TeamColor, list[str]] = Field(default_factory=_empty_team_lists)
    picks: dict[TeamColor, list[str]] = Field(default_factory=_empty_team_lists)
    first_team: TeamColor | None = None
    game_id: str | None = None
    created_at: float

"""REST endpoints under /drafts (pre-game draft lobby)."""

from __future__ import annotations

import os
import random
import time
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from goa2.data.heroes.registry import HeroRegistry
from goa2.domain.models import TeamColor
from goa2.draft import service
from goa2.draft.errors import InvalidTeamError, NotHostError
from goa2.draft.models import DraftStatus
from goa2.draft.modes import DRAFT_MODES
from goa2.engine.session import GameSession
from goa2.engine.setup import GameSetup
from goa2.server.draft_registry import DraftRegistry, ManagedDraft
from goa2.server.draft_ws import broadcast_draft, draft_view_payload
from goa2.server.models import (
    ClaimHeroRequest,
    CreateDraftRequest,
    CreateDraftResponse,
    DraftActionRequest,
    DraftModeInfo,
    DraftViewResponse,
    JoinDraftRequest,
    JoinDraftResponse,
    SetCaptainRequest,
    SetTeamRequest,
    UpdateDraftSettingsRequest,
)

router = APIRouter(prefix="/drafts", tags=["drafts"])

# Exact total player counts the engine supports as match brackets.
VALID_TOTALS = frozenset({2, 4, 5, 6})


def get_draft_registry(request: Request) -> DraftRegistry:
    return request.app.state.draft_registry


DraftRegistryDep = Annotated[DraftRegistry, Depends(get_draft_registry)]


@dataclass
class DraftContext:
    draft_id: str
    player_id: str
    is_spectator: bool
    is_host: bool


def get_draft_player(request: Request, registry: DraftRegistryDep) -> DraftContext:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth[len("Bearer ") :]
    resolved = registry.resolve_token(token)
    if resolved is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    draft_id, player_id, is_spectator, is_host = resolved
    path_draft_id = request.path_params.get("draft_id")
    if path_draft_id and path_draft_id != draft_id:
        raise HTTPException(status_code=403, detail="Token does not match this draft")
    return DraftContext(draft_id, player_id, is_spectator, is_host)


DraftPlayerDep = Annotated[DraftContext, Depends(get_draft_player)]


def _maps_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "data", "maps")


def _map_path(map_name: str) -> str:
    path = os.path.normpath(os.path.join(_maps_dir(), f"{map_name}.json"))
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"Map '{map_name}' not found")
    return path


def _list_maps() -> list[str]:
    base = _maps_dir()
    if not os.path.isdir(base):
        return []
    return sorted(f[:-5] for f in os.listdir(base) if f.endswith(".json"))


def _draft_view(md: ManagedDraft, player_id: str, is_spectator: bool) -> DraftViewResponse:
    return DraftViewResponse(**draft_view_payload(md, player_id, is_spectator))


def _reject_spectator(player: DraftContext) -> None:
    if player.is_spectator:
        raise HTTPException(status_code=403, detail="Spectators cannot modify the draft")


def _maybe_create_game(request: Request, md: ManagedDraft) -> None:
    if not service.is_ready_to_create_game(md.state):
        return
    state = md.state
    red_heroes, blue_heroes = service.team_hero_lists(state)
    game_seed_id = uuid.uuid4().hex
    game_id = game_seed_id[:12]
    seed = int(game_seed_id, 16)
    game_state = GameSetup.create_game(
        _map_path(state.map_name),
        red_heroes,
        blue_heroes,
        state.cheats,
        state.game_type,
        seed=seed,
    )
    session = GameSession(game_state)
    hero_ids = [h.id for team in game_state.teams.values() for h in team.heroes]
    game_registry = request.app.state.registry
    game = game_registry.create_game(session, hero_ids, game_id=game_id)
    if game.replay_recorder:
        game.replay_recorder.record_setup(
            map_name=state.map_name,
            red_heroes=red_heroes,
            blue_heroes=blue_heroes,
            game_type=state.game_type,
            cheats=state.cheats,
            seed=seed,
        )
    name_to_id = {h.name: h.id for team in game_state.teams.values() for h in team.heroes}
    for player in state.players:
        if player.claimed_hero:
            hero_id = name_to_id[player.claimed_hero]
            md.player_game_tokens[player.id] = game.hero_to_token[hero_id]
    state.game_id = game.game_id
    state.status = DraftStatus.COMPLETE


# ---- Endpoints ----


@router.get("/modes", response_model=list[DraftModeInfo])
async def list_modes() -> list[DraftModeInfo]:
    return [DraftModeInfo(name=m.name, description=m.description) for m in DRAFT_MODES.values()]


@router.get("/maps", response_model=list[str])
async def list_maps() -> list[str]:
    """Available map names for the in-lobby map picker."""
    return _list_maps()


@router.post("", response_model=CreateDraftResponse, status_code=201)
async def create_draft(body: CreateDraftRequest, registry: DraftRegistryDep) -> CreateDraftResponse:
    # Match settings can be tweaked in the lobby, but seed/validate the initial values now.
    if body.game_type not in ("QUICK", "LONG"):
        raise HTTPException(status_code=400, detail="game_type must be QUICK or LONG")
    if body.draft_mode not in DRAFT_MODES:
        raise HTTPException(status_code=400, detail=f"Unknown draft_mode '{body.draft_mode}'")
    _map_path(body.map_name)
    draft_id = uuid.uuid4().hex[:12]
    state = service.create_draft(
        draft_id,
        body.map_name,
        body.game_type,
        body.draft_mode,
        body.host_name,
        now=time.time(),
        cheats=body.cheats_enabled,
    )
    md = registry.create(state)
    return CreateDraftResponse(
        draft_id=draft_id,
        player_id="p1",
        player_token=md.host_token,
        spectator_token=md.spectator_token,
    )


@router.patch("/{draft_id}/settings", response_model=DraftViewResponse)
async def update_settings(
    draft_id: str,
    body: UpdateDraftSettingsRequest,
    player: DraftPlayerDep,
    registry: DraftRegistryDep,
) -> DraftViewResponse:
    if not player.is_host:
        raise NotHostError("Only the host may change draft settings")
    if body.game_type is not None and body.game_type not in ("QUICK", "LONG"):
        raise HTTPException(status_code=400, detail="game_type must be QUICK or LONG")
    if body.draft_mode is not None and body.draft_mode not in DRAFT_MODES:
        raise HTTPException(status_code=400, detail=f"Unknown draft_mode '{body.draft_mode}'")
    if body.map_name is not None:
        _map_path(body.map_name)  # 404 if missing
    md = registry.get(draft_id)
    async with md.lock:
        service.update_settings(
            md.state,
            map_name=body.map_name,
            game_type=body.game_type,
            draft_mode=body.draft_mode,
            cheats=body.cheats_enabled,
        )
    await broadcast_draft(md, registry)
    return _draft_view(md, player.player_id, player.is_spectator)


@router.post("/{draft_id}/join", response_model=JoinDraftResponse)
async def join_draft(
    draft_id: str, body: JoinDraftRequest, registry: DraftRegistryDep
) -> JoinDraftResponse:
    md = registry.get(draft_id)
    async with md.lock:
        player = service.join(md.state, body.display_name)
        token = registry.add_player_token(draft_id, player.id)
    await broadcast_draft(md, registry)
    return JoinDraftResponse(draft_id=draft_id, player_id=player.id, player_token=token)


@router.get("/{draft_id}", response_model=DraftViewResponse)
async def get_draft(
    draft_id: str, player: DraftPlayerDep, registry: DraftRegistryDep
) -> DraftViewResponse:
    md = registry.get(draft_id)
    return _draft_view(md, player.player_id, player.is_spectator)


@router.post("/{draft_id}/team", response_model=DraftViewResponse)
async def set_team(
    draft_id: str,
    body: SetTeamRequest,
    player: DraftPlayerDep,
    registry: DraftRegistryDep,
) -> DraftViewResponse:
    _reject_spectator(player)
    md = registry.get(draft_id)
    try:
        team = TeamColor(body.team)
    except ValueError as exc:
        raise InvalidTeamError(f"Invalid team '{body.team}'") from exc
    async with md.lock:
        service.set_team(md.state, player.player_id, team)
    await broadcast_draft(md, registry)
    return _draft_view(md, player.player_id, player.is_spectator)


@router.post("/{draft_id}/leave-team", response_model=DraftViewResponse)
async def leave_team(
    draft_id: str,
    player: DraftPlayerDep,
    registry: DraftRegistryDep,
) -> DraftViewResponse:
    _reject_spectator(player)
    md = registry.get(draft_id)
    async with md.lock:
        service.leave_team(md.state, player.player_id)
    await broadcast_draft(md, registry)
    return _draft_view(md, player.player_id, player.is_spectator)


@router.post("/{draft_id}/randomize-teams", response_model=DraftViewResponse)
async def randomize_teams(
    draft_id: str, player: DraftPlayerDep, registry: DraftRegistryDep
) -> DraftViewResponse:
    if not player.is_host:
        raise NotHostError("Only the host may randomize teams")
    md = registry.get(draft_id)
    async with md.lock:
        service.randomize_teams(md.state, random.Random())
    await broadcast_draft(md, registry)
    return _draft_view(md, player.player_id, player.is_spectator)


@router.post("/{draft_id}/captain", response_model=DraftViewResponse)
async def set_captain(
    draft_id: str,
    body: SetCaptainRequest,
    player: DraftPlayerDep,
    registry: DraftRegistryDep,
) -> DraftViewResponse:
    if not player.is_host:
        raise NotHostError("Only the host may set captains")
    md = registry.get(draft_id)
    async with md.lock:
        service.set_captain(md.state, body.player_id)
    await broadcast_draft(md, registry)
    return _draft_view(md, player.player_id, player.is_spectator)


@router.post("/{draft_id}/start", response_model=DraftViewResponse)
async def start_draft(
    draft_id: str, player: DraftPlayerDep, registry: DraftRegistryDep
) -> DraftViewResponse:
    if not player.is_host:
        raise NotHostError("Only the host may start the draft")
    md = registry.get(draft_id)
    async with md.lock:
        # Team sizes emerge from membership; the total must be an exact engine bracket.
        total = sum(1 for p in md.state.players if p.team is not None)
        if total not in VALID_TOTALS:
            raise HTTPException(
                status_code=400,
                detail=f"{total} assigned players is not a valid match size "
                f"(must be one of {sorted(VALID_TOTALS)}).",
            )
        service.start_draft(md.state, HeroRegistry.list_heroes(), random.Random())
    await broadcast_draft(md, registry)
    return _draft_view(md, player.player_id, player.is_spectator)


@router.post("/{draft_id}/action", response_model=DraftViewResponse)
async def draft_action(
    draft_id: str,
    body: DraftActionRequest,
    player: DraftPlayerDep,
    registry: DraftRegistryDep,
) -> DraftViewResponse:
    _reject_spectator(player)
    md = registry.get(draft_id)
    async with md.lock:
        service.apply_action(md.state, player.player_id, body.hero)
    await broadcast_draft(md, registry)
    return _draft_view(md, player.player_id, player.is_spectator)


@router.post("/{draft_id}/claim", response_model=DraftViewResponse)
async def claim_hero(
    draft_id: str,
    body: ClaimHeroRequest,
    player: DraftPlayerDep,
    registry: DraftRegistryDep,
    request: Request,
) -> DraftViewResponse:
    _reject_spectator(player)
    md = registry.get(draft_id)
    async with md.lock:
        service.claim_hero(md.state, player.player_id, body.hero)
        _maybe_create_game(request, md)
    await broadcast_draft(md, registry)
    return _draft_view(md, player.player_id, player.is_spectator)

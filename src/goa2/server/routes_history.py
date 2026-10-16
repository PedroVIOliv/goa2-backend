"""Authenticated, read-only player history; never exposes the audit timeline."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response

from goa2.server.auth import PlayerDep, RegistryDep
from goa2.server.live_history import HistoryUnavailable, public_position
from goa2.server.models import HistoryFramesResponse, HistoryIndexResponse, HistoryStateResponse
from goa2.server.replay_codec import GroupBuilder, encode, for_delivery

router = APIRouter(prefix="/games/{game_id}/history", tags=["history"])


def _check(history: Any, revision: int | None) -> None:
    if revision is not None and revision != history.revision:
        raise HTTPException(409, "History changed; refresh the index")


def _position(history: Any, position_id: int) -> int:
    if not 0 <= position_id < len(history.records):
        raise HTTPException(404, "Unknown history position")
    try:
        return history.active.index(position_id)
    except ValueError:
        raise HTTPException(410, "History position was superseded") from None


async def _game(game_id: str, registry: Any) -> Any:
    game = registry.get(game_id)
    async with game.lock:
        registry._bind_history(game)
    from goa2.server.history_backfill import ensure_backfill

    await ensure_backfill(game, registry)
    return game


@router.get("", response_model=HistoryIndexResponse)
async def history_index(
    game_id: str,
    player: PlayerDep,
    registry: RegistryDep,
    response: Response,
    before_position_id: int | None = Query(None, ge=0),
    revision: int | None = Query(None, ge=0),
    limit: int = Query(30, ge=1, le=100),
) -> dict[str, Any]:
    game = await _game(game_id, registry)
    response.headers["Cache-Control"] = "private, no-store"
    async with game.lock:
        history = game.history
        _check(history, revision)
        end = (
            _position(history, before_position_id)
            if before_position_id is not None
            else len(history.active)
        )
        ids = history.active[max(0, end - limit) : end]
        return {
            **history.metadata(),
            "positions": [public_position(history.records[i]) for i in ids],
            "has_more": end > limit,
            "before_position_id": ids[0] if ids else None,
        }


async def _read(
    game: Any,
    registry: Any,
    viewer: str,
    position_id: int,
    limit: int,
    revision: int | None,
) -> dict[str, Any]:
    async with game.lock:
        history = game.history
        _check(history, revision)
        start = _position(history, position_id)
        ids = history.active[start : start + limit]
        epoch, version = history.epoch, history.revision
        positions = [public_position(history.records[i]) for i in ids]
        reader = history.reader()

    def materialize() -> dict[str, Any]:
        bodies = reader.read_many(ids, viewer) if len(ids) > 1 else [reader.read(ids[0], viewer)]
        builder = GroupBuilder(0, bodies[0], max_patches=limit + 1, copy_values=False)
        for index, body in enumerate(bodies[1:], 1):
            # API pages are bounded to 30. Do not split a requested page on
            # storage budget; use the same codec with budget checks disabled.
            builder.check_every = limit + 1
            builder.append(index, body)
        return builder.group

    try:
        group = await asyncio.to_thread(materialize)
    except HistoryUnavailable as exc:
        async with game.lock:
            if history is game.history and history.backfill_status == "complete":
                from goa2.server.history_backfill import start_backfill

                history.backfill_status = "pending"
                start_backfill(game, registry)
        raise HTTPException(503, str(exc)) from exc
    async with game.lock:
        if (
            history is not game.history
            or history.epoch != epoch
            or (revision is not None and history.revision != version)
        ):
            raise HTTPException(409, "History changed; refresh the index")
        for record_id in ids:
            _position(history, record_id)
    return {**group, "positions": positions, "revision": version, "epoch": epoch}


@router.get("/state", response_model=HistoryStateResponse)
async def history_state(
    game_id: str,
    player: PlayerDep,
    registry: RegistryDep,
    response: Response,
    position_id: int = Query(..., ge=0),
    revision: int | None = Query(None, ge=0),
) -> dict[str, Any]:
    game = await _game(game_id, registry)
    group = await _read(
        game,
        registry,
        "spectator" if player.is_spectator else player.hero_id,
        position_id,
        1,
        revision,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return {
        **group["keyframe"],
        "position": group["positions"][0],
        "revision": group["revision"],
        "epoch": group["epoch"],
    }


@router.get("/frames", response_model=HistoryFramesResponse)
async def history_frames(
    game_id: str,
    player: PlayerDep,
    registry: RegistryDep,
    request: Request,
    from_position_id: int = Query(..., ge=0),
    limit: int = Query(30, ge=1, le=30),
    revision: int | None = Query(None, ge=0),
) -> Response:
    game = await _game(game_id, registry)
    group = await _read(
        game,
        registry,
        "spectator" if player.is_spectator else player.hero_id,
        from_position_id,
        limit,
        revision,
    )
    stored = await asyncio.to_thread(encode, group, quality=1)
    body, encoding = for_delivery(
        stored, accepts_brotli="br" in request.headers.get("accept-encoding", "")
    )
    async with game.lock:
        if game.history.epoch != group["epoch"] or (
            revision is not None and game.history.revision != group["revision"]
        ):
            raise HTTPException(409, "History changed; refresh the index")
    return Response(
        body,
        media_type="application/json",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Encoding": encoding,
            "Vary": "Accept-Encoding",
        },
    )

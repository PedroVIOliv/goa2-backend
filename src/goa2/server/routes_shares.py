"""Public read-only access to a baked, shared replay.

Unlike ``routes_replays``, this router is mounted unconditionally: the share
token IS the credential, and recipients are not admins. Only two handlers are
public, both pure file reads — no engine, no game registry, no shared mutable
state. Minting and revoking a share stay on the admin router.

The token is opaque and carries no game id, so a recipient cannot enumerate
other games by editing the URL.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from goa2.server import shares
from goa2.server.admin import require_admin
from goa2.server.replay import index_for_round_turn

__all__ = ["admin_router", "router"]

router = APIRouter(prefix="/shared", tags=["shared"])

# Revocation is privileged and lives on its own path so the public router stays
# read-only. Minting is in routes_replays, where the reconstruction machinery is.
admin_router = APIRouter(prefix="/shares", tags=["shares"], dependencies=[Depends(require_admin)])


@admin_router.get("")
def list_shares() -> list[dict[str, Any]]:
    """Live shares, newest first — what the replay list uses to badge rows."""
    return [
        {
            "token": m["token"],
            "game_id": m["game_id"],
            "total_decisions": m.get("total_decisions", 0),
            "created_at": m.get("created_at"),
            "engine": m.get("engine"),
            "size_bytes": m.get("size_bytes", 0),
        }
        for m in shares.list_shares()
    ]


@admin_router.delete("/{token}", status_code=204)
def revoke_share(token: str) -> None:
    if not shares.revoke_share(token):
        raise HTTPException(status_code=404, detail="Share not found")


def _meta_or_404(token: str) -> dict[str, Any]:
    meta = shares.load_meta(token)
    if meta is None:
        # Unknown, malformed and revoked are all 404: probing distinguishes nothing.
        raise HTTPException(status_code=404, detail="Share not found")
    return meta


@router.get("/{token}")
def get_shared_meta(token: str) -> dict[str, Any]:
    """Setup header plus the decision list, mirroring GET /replays/{game_id}."""
    meta = _meta_or_404(token)
    return {"setup": meta["setup"], "decisions": meta["decisions"]}


@router.get("/{token}/state")
def get_shared_state(
    request: Request,
    token: str,
    decision: int | None = Query(None, description="Position after N decisions"),
    round: int | None = Query(None, description="Position at the start of round R"),
    turn: int | None = Query(None, description="With round: position at turn T"),
) -> Response:
    """Return the baked group holding a position.

    The body is ``{start, keyframe, patches}``: one full ``{view, position,
    winner}`` snapshot plus an RFC 6902 patch per following position. The caller
    reaches position N by applying ``patches[0 .. N-start-1]`` to ``keyframe``.
    Every snapshot carries its own ``position``, so a reconstructed one is
    indistinguishable from ``GET /replays/{game_id}/state`` at that index.

    Serving a group rather than a position means scrubbing inside it costs no
    further requests. The file is stored brotli-compressed and served as-is to
    any client that accepts brotli; no JSON is parsed on this path.

    Shares baked before groups existed still return a single position body.
    """
    meta = _meta_or_404(token)
    total = int(meta["total_decisions"])

    if decision is not None:
        target = decision
    elif round is not None:
        target = index_for_round_turn(meta["decisions"], round, turn)
    else:
        target = total
    target = max(0, min(target, total))

    cache = "public, max-age=31536000, immutable"

    if not shares.is_grouped(meta):
        path = shares.position_path(token, target)
        if path is None:
            raise HTTPException(status_code=500, detail=f"Share is missing position {target}")
        return Response(
            content=path.read_bytes(),
            media_type="application/json",
            headers={"Content-Encoding": "gzip", "Cache-Control": cache},
        )

    start = shares.group_start_for(meta, target)
    accepts_brotli = "br" in request.headers.get("accept-encoding", "")
    found = shares.read_group(token, start, accepts_brotli=accepts_brotli)
    if found is None:
        # meta and groups are written together, so this means a damaged share.
        raise HTTPException(status_code=500, detail=f"Share is missing position {target}")
    content, encoding = found

    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Encoding": encoding,
            # Two encodings live behind one URL, so a cache must key on which.
            "Vary": "Accept-Encoding",
            "Cache-Control": cache,
            # Lets a caller that did not resolve the target itself (curl, a
            # round/turn jump) know which position it asked for.
            "X-Replay-Position": str(target),
            "X-Replay-Group-Start": str(start),
        },
    )

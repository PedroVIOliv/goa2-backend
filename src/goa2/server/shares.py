"""Shareable, pre-baked replay artifacts.

A share is a capability token that grants read-only access to exactly one
*finished* game's replay, without an admin token. It exists so a tester can be
shown a game for bug triage without being handed `GOA2_ADMIN_TOKEN`, which also
grants bug-report mutation.

Storage mirrors ``bug_reports.py``: one directory per share under
``GOA2_SHARE_DIR`` (default ``data/shares``)::

    data/shares/<token>/meta.json        setup, decision list, total, engine, game_id
    data/shares/<token>/g0000.json.br    positions 0..K, brotli
    data/shares/<token>/g0175.json.br    positions 175.., brotli
    ...

A group holds one full snapshot (its *keyframe*) plus an RFC 6902 JSON Patch per
following position::

    {"start": 175, "keyframe": {...}, "patches": [[op, ...], ...]}

Consecutive positions differ by one decision, so a patch is ~1.7 KB against a
~120 KB snapshot. Storing each position whole cost ~16.5 KB compressed; grouping
brings a 703-position game from 10.5 MB to ~90 KB, and lets the client scrub the
whole group without another request. The reader never expands a group — the
bytes are served exactly as baked, so this path still parses no JSON.

Why bake instead of reconstructing per request: a finished game's log never
changes, so its positions are immutable. Reconstruction is *re-simulation* —
``ReplayCursor.seek`` has no un-apply, so every backward seek rebuilds from the
seed (measured on the deployment target: 0.82 s to build the empty session plus
18.4 ms per decision, i.e. ~5.4 s for a 249-decision game). That work is pure
Python holding the GIL, so it competes with the event loop serving live games.
Baking once at mint time turns every subsequent read into one small file read
with no engine work at all.

A baked share is fully self-contained: it does not read the ``.jsonl`` log, so
it cannot fail on engine drift the way live reconstruction can.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import re
import secrets
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import brotli
import jsonpatch

logger = logging.getLogger(__name__)

DEFAULT_SHARE_DIR = "data/shares"

# Bumped when the on-disk layout changes. Shares baked before groups existed
# carry no marker and are still served position-by-position.
SHARE_FORMAT = 2

# Brotli beats gzip here by ~1.7x because its window spans the whole group,
# so the board topology repeated in every snapshot is visible to it (gzip's
# 32 KB window cannot reach across a ~120 KB snapshot). Quality 9 rather than
# 11: on the deployment target 11 costs 1.7 s per group against 47 ms, for 15%.
_BROTLI_QUALITY = 9

# Groups are stored only in brotli. A client that cannot take it gets one
# transcoded per request — measured on the deployment target at 1 ms to
# decompress plus 17 ms to gzip, on a path no browser has taken since brotli
# became universal. Storing a gzip twin instead would cost 1.5x the brotli
# bytes on every share forever to serve that path in zero.
_GZIP_FALLBACK_LEVEL = 6

# A group closes once its patches outweigh its keyframe, so no single request
# ever costs more than ~2x the keyframe it is anchored on. Falls out at K~175.
_BUDGET_MULTIPLE = 2

# Sizing the group exactly at every position would recompress a growing blob
# K times per group. Checking periodically against a cheap compression level
# costs a fraction of that and moves a boundary by at most 7 positions.
_CHECK_EVERY = 8
_PROXY_LEVEL = 1

# Hard ceiling regardless of budget, so one pathologically static stretch
# cannot produce a group that must be downloaded in full to see its last position.
_MAX_GROUP = 512

# Tokens are secrets.token_urlsafe output: URL-safe base64 alphabet.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _share_dir() -> str:
    return os.environ.get("GOA2_SHARE_DIR", DEFAULT_SHARE_DIR)


def _share_path(token: str) -> Path:
    """Resolve a token to its share directory, rejecting path traversal.

    Raises FileNotFoundError for anything that is not a plausible token, so a
    malformed token is indistinguishable from a revoked one to the caller.
    """
    if not token or not _TOKEN_RE.match(token):
        raise FileNotFoundError(f"Share not found: {token!r}")
    return Path(_share_dir()) / token


def _position_name(index: int) -> str:
    return f"{index:03d}.json.gz"


def _group_name(start: int, encoding: str) -> str:
    return f"g{start:04d}.json.{encoding}"


def _dumps(obj: Any) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode()


def _write_groups(directory: Path, render: Any, positions: int) -> tuple[list[dict[str, int]], int]:
    """Write every group for positions 0..positions-1 into ``directory``.

    ``render(index) -> dict`` is called once per position, in order, so a caller
    that can only walk forward (a replay being re-simulated) is never asked to
    go back. Returns the group index for meta.json and the bytes written.
    """
    groups: list[dict[str, int]] = []
    size_bytes = 0

    def flush(start: int, keyframe: dict[str, Any], patches: list[list[dict[str, Any]]]) -> None:
        nonlocal size_bytes
        raw = _dumps({"start": start, "keyframe": keyframe, "patches": patches})
        compressed = brotli.compress(raw, quality=_BROTLI_QUALITY)
        (directory / _group_name(start, "br")).write_bytes(compressed)
        size_bytes += len(compressed)
        groups.append({"start": start, "count": len(patches) + 1})

    start = 0
    keyframe = render(0)
    previous = keyframe
    keyframe_raw = _dumps(keyframe)
    keyframe_proxy = len(gzip.compress(keyframe_raw, _PROXY_LEVEL))
    patches: list[list[dict[str, Any]]] = []
    patches_raw: list[bytes] = []

    def over_budget() -> bool:
        if len(patches) >= _MAX_GROUP:
            return True
        if len(patches) % _CHECK_EVERY:
            return False
        blob = keyframe_raw + b"".join(patches_raw)
        grown = len(gzip.compress(blob, _PROXY_LEVEL)) - keyframe_proxy
        return grown > _BUDGET_MULTIPLE * keyframe_proxy

    for index in range(1, positions):
        body = render(index)
        patches.append(jsonpatch.make_patch(previous, body).patch)
        patches_raw.append(_dumps(patches[-1]))
        previous = body
        if over_budget():
            # The patch that broke the budget is dropped and its target becomes
            # the next keyframe, so no position is ever unreachable.
            patches.pop()
            patches_raw.pop()
            flush(start, keyframe, patches)
            start, keyframe = index, body
            keyframe_raw = _dumps(body)
            keyframe_proxy = len(gzip.compress(keyframe_raw, _PROXY_LEVEL))
            patches, patches_raw = [], []

    flush(start, keyframe, patches)
    return groups, size_bytes


def bake_share(
    *,
    game_id: str,
    setup: dict[str, Any],
    decisions: list[dict[str, Any]],
    render: Any,
    validate: Any = None,
) -> str | None:
    """Bake every position of a finished game and return the new share token.

    ``render`` is called as ``render(index) -> dict`` for index 0..len(decisions)
    and must return the same body ``GET /replays/{id}/state`` produces at that
    index. Keeping reconstruction in the caller leaves this module free of engine
    imports and makes the bake trivially testable with a stub.

    ``validate`` (optional) is called with no arguments after the last render and
    before the artifact is published. Returning False discards it and yields
    None — that is how "only finished games" is enforced without a second
    reconstruction pass, since whether the game finished is only known once every
    decision has been applied.

    The artifact is built in a temp directory and moved into place atomically, so
    a crash or full disk never leaves a half-written share readable.
    """
    token = secrets.token_urlsafe(32)
    root = Path(_share_dir())
    root.mkdir(parents=True, exist_ok=True)

    staging = Path(tempfile.mkdtemp(prefix=f".{token}.", dir=root))
    try:
        groups, size_bytes = _write_groups(staging, render, len(decisions) + 1)

        if validate is not None and not validate():
            shutil.rmtree(staging, ignore_errors=True)
            return None

        meta = {
            "token": token,
            "game_id": game_id,
            "setup": setup,
            "decisions": [
                {
                    "index": i,
                    "type": d.get("type"),
                    "r": d.get("r"),
                    "t": d.get("t"),
                    "hero": d.get("hero"),
                    "card": d.get("card"),
                    "sel": d.get("sel"),
                }
                for i, d in enumerate(decisions)
            ],
            "total_decisions": len(decisions),
            "engine": setup.get("engine"),
            "created_at": time.time(),
            "format": SHARE_FORMAT,
            # Start index and length of every group, in order. The read path
            # scans this to map a position to its file — the same kind of
            # metadata lookup round/turn resolution already does.
            "groups": groups,
            # Recorded at bake time so listing shares never stats hundreds of files.
            "size_bytes": size_bytes,
        }
        (staging / "meta.json").write_text(json.dumps(meta, indent=2))
        os.replace(staging, root / token)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return token


def load_meta(token: str) -> dict[str, Any] | None:
    """The share's meta.json, or None if the token is unknown or revoked."""
    try:
        path = _share_path(token) / "meta.json"
    except FileNotFoundError:
        return None
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read share meta for %s", token)
        return None


def position_path(token: str, index: int) -> Path | None:
    """Path to a baked position's gzip file, or None if absent.

    Only format 1 shares have these; groups replaced them.
    """
    try:
        path = _share_path(token) / _position_name(index)
    except FileNotFoundError:
        return None
    return path if path.is_file() else None


def is_grouped(meta: dict[str, Any]) -> bool:
    """Whether this share stores keyframe groups rather than one file per position."""
    return int(meta.get("format", 1)) >= 2


def group_start_for(meta: dict[str, Any], index: int) -> int:
    """Start index of the group holding ``index``.

    Groups are contiguous and ordered, so the last one starting at or before the
    target owns it. Falls back to 0 for a meta with no usable group list, which
    keeps a damaged share serving its first group instead of erroring.
    """
    start = 0
    for group in meta.get("groups") or []:
        if int(group["start"]) <= index:
            start = int(group["start"])
        else:
            break
    return start


def group_path(token: str, start: int) -> Path | None:
    """Path to a baked group, or None if absent."""
    try:
        path = _share_path(token) / _group_name(start, "br")
    except FileNotFoundError:
        return None
    return path if path.is_file() else None


def read_group(token: str, start: int, *, accepts_brotli: bool) -> tuple[bytes, str] | None:
    """Group bytes plus the Content-Encoding they are in, or None if absent.

    Brotli clients get the stored bytes untouched, which is the whole point of
    baking: the read path compresses nothing and parses nothing. Anything else
    is transcoded here rather than kept on disk.
    """
    path = group_path(token, start)
    if path is None:
        return None
    stored = path.read_bytes()
    if accepts_brotli:
        return stored, "br"
    return gzip.compress(brotli.decompress(stored), _GZIP_FALLBACK_LEVEL), "gzip"


def migrate_share_to_groups(token: str) -> dict[str, Any] | None:
    """Rebuild a format 1 share as keyframe groups, keeping its token and URL.

    The positions are already baked, so this reads them back instead of
    re-simulating: no engine, no replay log, and therefore no way for engine
    drift to change a share that recipients may already be looking at.

    The steps are ordered so an interrupted run always leaves a share that
    serves correctly and a rerun finishes the job: groups are written first and
    ignored by a format 1 reader, replacing meta.json is the atomic moment the
    share becomes format 2, and only then are the old position files removed.

    Returns the updated meta, or None if the token is unknown or already grouped.
    """
    meta = load_meta(token)
    if meta is None or is_grouped(meta):
        return None
    directory = _share_path(token)

    positions = int(meta["total_decisions"]) + 1
    cache: dict[int, dict[str, Any]] = {}

    def render(index: int) -> dict[str, Any]:
        if index not in cache:
            path = directory / _position_name(index)
            cache[index] = json.loads(gzip.decompress(path.read_bytes()))
            cache.pop(index - 2, None)
        return cache[index]

    groups, size_bytes = _write_groups(directory, render, positions)

    meta = {**meta, "format": SHARE_FORMAT, "groups": groups, "size_bytes": size_bytes}
    staged = directory / "meta.json.tmp"
    staged.write_text(json.dumps(meta, indent=2))
    os.replace(staged, directory / "meta.json")

    for index in range(positions):
        (directory / _position_name(index)).unlink(missing_ok=True)
    return meta


def revoke_share(token: str) -> bool:
    """Delete a share directory. Returns False if it did not exist."""
    try:
        path = _share_path(token)
    except FileNotFoundError:
        return False
    if not path.is_dir():
        return False
    shutil.rmtree(path)
    return True


def list_shares() -> list[dict[str, Any]]:
    """All shares, newest first. Unreadable directories are skipped."""
    directory = Path(_share_dir())
    if not directory.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for child in directory.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        meta = load_meta(child.name)
        if meta is not None:
            out.append(meta)
    out.sort(key=lambda m: m.get("created_at") or 0, reverse=True)
    return out


def share_for_game(game_id: str) -> dict[str, Any] | None:
    """The newest live share for a game, if any."""
    return next((m for m in list_shares() if m.get("game_id") == game_id), None)


def shared_game_ids() -> set[str]:
    """Game ids with at least one live share (their replays are pinned).

    The baked artifact does not need the log, so this pin is belt-and-braces —
    it keeps the original available for re-baking and debugging.
    """
    return {m["game_id"] for m in list_shares() if m.get("game_id")}

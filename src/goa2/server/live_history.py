"""Viewer-scoped captured history and the effective (correction-free) timeline.

The save manifest is the commit point. Closed groups never change; each open
tail version gets a new content-addressed file before the save references it.
No engine code is needed to read a captured position.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import time
from collections import OrderedDict
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from goa2.domain.models.enums import HistoryScope
from goa2.domain.types import HeroID
from goa2.domain.views import HeroViewCache, _build_board_view, build_view
from goa2.engine.session import GameSession
from goa2.server.replay import winner_of
from goa2.server.replay_codec import (
    GroupBuilder,
    apply_patch,
    decode,
    encode,
    make_patch,
    project_member,
    reconstruct,
    reconstruct_many,
)

logger = logging.getLogger(__name__)
FORMAT = 3
_CACHE: OrderedDict[tuple[str, str, int], dict[str, Any]] = OrderedDict()
_CACHE_LOCK = RLock()
_FILE = re.compile(r"^[0-9a-f]{64}\.br$")
# Live decisions favor bounded capture work. Shares retain the codec's
# compressed-size policy; live groups use phase boundaries and a cheap byte
# budget, with at most 31 forward patches between keyframes.
_GROUP_OPTIONS: dict[str, Any] = {"max_patches": 32, "budget_mode": "raw"}


class HistoryUnavailable(ValueError):
    """A known record cannot currently be reconstructed."""


def canonical_views(
    session: GameSession,
    *,
    hero_cache: HeroViewCache | None = None,
    tile_cache: dict | None = None,
) -> dict[str, Any]:
    state = session.state
    board = _build_board_view(state, tile_cache=tile_cache)
    viewers = [None, *(h.id for team in state.teams.values() for h in team.heroes)]
    result = {}
    hero_views = hero_cache.prepare(state) if hero_cache is not None else {}
    public_view = None
    for viewer in viewers:
        view = build_view(
            state,
            for_hero_id=HeroID(viewer) if viewer else None,
            prebuilt_board_view=board,
            prebuilt_hero_views=hero_views,
            prebuilt_public_view=public_view,
            include_transient=False,
        )
        view["clock"] = None
        result[viewer or "spectator"] = {"view": view, "winner": winner_of(state)}
        if viewer is None:
            public_view = view
    # build_view constructs independent snapshots; the shared board is freshly
    # built too. Transfer ownership to the codec to avoid cloning 11 views twice.
    return result


def history_directory(save_dir: str, game_id: str) -> Path:
    return Path(save_dir) / ".history" / hashlib.sha256(game_id.encode()).hexdigest()


def pack_views(views: dict[str, Any], hero_patches: dict | None = None) -> dict[str, Any]:
    public = views["spectator"]
    memo: dict[tuple[int, int], bool] = {}
    cached: dict[tuple[str, int, int], list[dict[str, Any]] | None] = {}
    pairs = {}
    if hero_patches is not None:
        for team, projection in public["view"].get("teams", {}).items():
            for index, hero in enumerate(projection["heroes"]):
                viewer = hero["id"]
                private = views[viewer]["view"]["teams"][team]["heroes"][index]
                escaped = team.replace("~", "~0").replace("/", "~1")
                path = f"/view/teams/{escaped}/heroes/{index}"
                key = (path, id(hero), id(private))
                previous = hero_patches.get(viewer)
                cached[key] = (
                    previous[3]
                    if previous
                    and previous[0] is hero
                    and previous[1] is private
                    and previous[2] == path
                    else None
                )
                pairs[viewer] = (hero, private, path, key)
    packed = {
        "public": public,
        "private": {
            viewer: make_patch(public, body, _memo=memo, _cache=cached)
            for viewer, body in views.items()
            if viewer != "spectator"
        },
    }
    if hero_patches is not None:
        hero_patches.clear()
        hero_patches.update(
            {
                viewer: (hero, private, path, cached[key])
                for viewer, (hero, private, path, key) in pairs.items()
            }
        )
    return packed


def unpack_views(packed: dict[str, Any]) -> dict[str, Any]:
    public = packed["public"]
    return {
        "spectator": public,
        **{
            viewer: apply_patch(deepcopy(public), patch)
            for viewer, patch in packed["private"].items()
        },
    }


def _atomic_bytes(path: Path, data: bytes) -> None:
    """Flush an immutable payload before its manifest can publish it.

    A new hash name is not referenced by any committed manifest, so exclusive
    creation needs no rename. Failed/unpublished files are removed here or by
    restart orphan cleanup. Repairing an existing damaged name still uses
    atomic replacement, preserving readers' previous file until repair ends.
    """
    if not path.parent.is_dir():
        path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        with path.open("r+b") as existing:
            if existing.read() == data:
                # An unpublished file may contain all bytes but have been
                # interrupted before its flush completed. Verify and flush it
                # before allowing a new manifest to reference it.
                os.fsync(existing.fileno())
                return
    else:
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            with suppress(OSError):
                path.unlink()
            raise
        return

    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class LiveHistory:
    def __init__(
        self, directory: Path | None = None, *, scope: HistoryScope = HistoryScope.CURRENT_ROUND
    ) -> None:
        self.scope = scope
        self.directory = directory
        self.cache_id = uuid4().hex
        self.records: list[dict[str, Any]] = []
        self.active: list[int] = []
        self.edits: list[dict[str, Any]] = []
        self.anchors: dict[str, int] = {}
        self.groups: list[dict[str, Any]] = []
        self.builder: GroupBuilder | None = None
        self.revision = 0
        self.epoch = 0
        self.raw_count = 0
        self.gaps: list[dict[str, Any]] = []
        self.backfill_status = "complete"
        self.last_manifest: dict[str, Any] | None = None
        self._dirty = False
        self._latest_views: dict[str, Any] | None = None
        self._last_anchor: tuple[str | None, str | None] = (None, None)
        self._hero_cache = HeroViewCache()
        self._tile_cache: dict = {}
        self._hero_patches: dict = {}
        self._retired_files: set[str] = set()
        self._legacy_anchor = False

    def anchor_key(self, session: GameSession, raw_count: int, decision: dict | None) -> str | None:
        anchor = session.rollback_anchor_id
        if anchor != self._last_anchor[0]:
            key = None
            if anchor is not None:
                key = f"decision:{raw_count}"
                if decision and decision.get("type") == "ov_rewind":
                    prefix = self.index_at(int(decision["to"]))
                    if prefix:
                        key = self.records[prefix[-1]]["anchor"] or key
                elif key in self.anchors:
                    # More than one unrecorded capture at the same raw prefix.
                    # Keep distinct engine generations distinct too.
                    key += f":{anchor}"
            self._last_anchor = (anchor, key)
        return self._last_anchor[1]

    def bind_session(self, session: GameSession, *, legacy: bool = False) -> None:
        """Attach a restored/merged anchor without hashing every new snapshot."""
        key = self.records[self.active[-1]]["anchor"] if self.active else None
        if legacy and session.rollback_anchor_id is not None:
            # Format 2 used canonical snapshot digests. Pay that conversion
            # once on restore; retain its existing anchor/index association.
            key = hashlib.sha256(
                json.dumps(session._rollback_snapshot, sort_keys=True).encode()
            ).hexdigest()
        self._last_anchor = (
            session.rollback_anchor_id,
            key if session.rollback_anchor_id is not None else None,
        )

    @property
    def latest_views(self) -> dict[str, Any]:
        if self._latest_views is None and self.builder is not None:
            self._latest_views = unpack_views(self.builder.previous)
        return self._latest_views or {}

    def index_at(self, raw_count: int) -> list[int]:
        active: list[int] = []
        for edit in self.edits:
            if edit["at"] > raw_count:
                break
            active[edit["keep"] :] = edit["add"]
        return active

    def capture(
        self,
        session: GameSession,
        raw_count: int,
        decision: dict[str, Any] | None = None,
        *,
        reconstructed: bool = False,
    ) -> None:
        self.capture_views(
            canonical_views(session, hero_cache=self._hero_cache, tile_cache=self._tile_cache),
            raw_count,
            decision,
            anchor=self.anchor_key(session, raw_count, decision),
            reconstructed=reconstructed,
        )

    def capture_views(
        self,
        views: dict[str, Any],
        raw_count: int,
        decision: dict[str, Any] | None = None,
        *,
        anchor: str | None = None,
        reconstructed: bool = False,
    ) -> None:
        """Consume independently built views; callers must not mutate them later."""
        decision = decision or {}
        kind = decision.get("type")
        before = self.active.copy()
        target = before.copy()
        if kind == "ov_rewind":
            target = self.index_at(int(decision["to"]))
            # A later rollback may have refreshed this anchor to a record
            # outside the target prefix. Re-bind it to that prefix's earliest
            # surviving anchored position before installing the restored head.
            anchored = [i for i in target if anchor and self.records[i]["anchor"] == anchor]
            if anchor and anchored:
                self.anchors[anchor] = anchored[0]
            if not target:
                self.gaps.append({"from_decision": 0, "to_decision": int(decision["to"])})
        elif kind == "rollback":
            anchor_id = self.anchors.get(anchor or "")
            if anchor_id in target:
                target = target[: target.index(anchor_id) + 1]
            else:
                # A legacy baseline cannot claim to know a pre-baseline anchor.
                target = []
                self.gaps.append({"from_decision": 0, "to_decision": raw_count})

        public = views["spectator"]["view"]
        window_changed = bool(
            before and self._window_start(self.records[before[-1]]) != self._window_start(public)
        )
        if self.builder is not None and "board" in public:
            previous_board = self.latest_views["spectator"]["view"].get("board")
            # This renderer has a fixed typed schema. Reuse a frozen board when
            # unchanged rather than comparing all tiles once per viewer.
            if previous_board == public["board"]:
                for body in views.values():
                    body["view"]["board"] = previous_board
        replace = kind in ("ov_rewind", "rollback")
        if target:
            previous = self.records[target[-1]]
            replace |= previous["phase"] == public["phase"] == "PLANNING" and (
                previous["round"],
                previous["turn"],
            ) == (public["round"], public["turn"])
        identical = self.builder is not None and self.latest_views == views
        if identical and before == target and kind is None:
            self.raw_count = raw_count
            if anchor and target and self.anchors.get(anchor) not in target:
                self.anchors[anchor] = target[-1]
            return

        if replace and target:
            target.pop()
        record_id = len(self.records)
        packed = pack_views(views, self._hero_patches)
        if self.builder is None:
            self.builder = GroupBuilder(record_id, packed, copy_values=False, **_GROUP_OPTIONS)
            self.groups.append({"start": record_id, "count": 1})
        else:
            previous_phase = self.builder.previous["public"]["view"]["phase"]
            closed = self.builder.append(
                record_id, packed, force_keyframe=previous_phase != public["phase"]
            )
            if closed is not None:
                if self._dirty or "file" not in self.groups[-1]:
                    self.groups[-1]["body"] = closed
                self.groups[-1]["count"] = len(closed["patches"]) + 1
                self.groups.append({"start": record_id, "count": 1})
        self.groups[-1]["count"] = len(self.builder.group["patches"]) + 1
        self.records.append(
            {
                "position_id": record_id,
                "phase": public["phase"],
                "round": public["round"],
                "turn": public["turn"],
                "timestamp": decision.get("ts", time.time()),
                "decision_count": raw_count,
                "reconstructed": reconstructed,
                "anchor": anchor,
                "correction": kind if kind in ("rollback", "ov_rewind") else None,
                "rewind_to": decision.get("to"),
                "kind": kind,
            }
        )
        self._dirty = True
        self._latest_views = views
        target.append(record_id)
        keep = 0
        while keep < min(len(before), len(target)) and before[keep] == target[keep]:
            keep += 1
        self.edits.append({"at": raw_count, "keep": keep, "add": target[keep:]})
        if keep < len(before) or window_changed:
            self.epoch += 1
        self.active = target
        self.revision += 1
        self.raw_count = raw_count
        if anchor and self.anchors.get(anchor) not in target:
            self.anchors[anchor] = record_id

    def capture_safely(
        self, session: GameSession, count: int, decision: dict | None = None
    ) -> None:
        try:
            self.capture(session, count, decision)
        except Exception:
            logger.exception("Live history capture failed at decision %s", count)
            self.note_gap(count)

    def note_gap(self, count: int) -> None:
        self.gaps.append({"from_decision": count, "to_decision": count})
        self.raw_count = count
        if self.builder is not None:
            self.groups[-1]["body"] = deepcopy(self.builder.group)
        self.builder = None
        if self.backfill_status == "complete":
            self.backfill_status = "pending"
        self.epoch += 1
        self.revision += 1

    def _window_start(self, view: dict[str, Any]) -> tuple[int, int]:
        if self.scope == HistoryScope.EVERYTHING:
            return (0, 0)
        round_num, turn = view["round"], view["turn"]
        if self.scope == HistoryScope.CURRENT_TURN:
            if view["phase"] == "PLANNING":
                turn = max(1, turn - 1)
            return (round_num, turn)
        # Upgrading still belongs to the old round. The next round's first
        # planning retains it until the engine actually completes planning,
        # including passes and two-card heroes' finish-planning decisions.
        if turn == 1 and view["phase"] == "PLANNING":
            round_num = max(1, round_num - 1)
        return (round_num, 0)

    def visible_active(
        self, viewer: str | None = None, *, view: dict[str, Any] | None = None
    ) -> list[int]:
        """Filter browsing access only; retain the full effective/audit history.

        Routes supply the live round/turn/phase, so a failed capture cannot
        leave an expired window accessible through an older captured head.
        """
        if viewer in (None, "spectator") or self.scope == HistoryScope.EVERYTHING:
            return self.active
        if not self.active:
            return []
        view = view if view is not None else self.records[self.active[-1]]
        first_round, first_turn = self._window_start(view)
        return [
            i
            for i in self.active
            if first_round <= self.records[i]["round"] <= view["round"]
            and (first_turn == 0 or first_turn <= self.records[i]["turn"] <= view["turn"])
        ]

    def metadata(
        self,
        *,
        matches_live: bool = True,
        viewer: str | None = None,
        view: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active = self.visible_active(viewer, view=view)
        return {
            "scope": HistoryScope.EVERYTHING if viewer in (None, "spectator") else self.scope,
            "first_position_id": active[0] if active else None,
            "revision": self.revision,
            "epoch": self.epoch,
            "position_id": active[-1] if active and matches_live else None,
            "predecessor_id": active[-2] if len(active) > 1 else None,
            "total": len(active),
            "availability": self.backfill_status,
            "gaps": deepcopy(self.gaps),
        }

    def metadata_for_view(self, view: dict, viewer: str | None) -> dict[str, Any]:
        canonical = {**view, "clock": None, "starting_position": None}
        latest = self.latest_views.get(viewer or "spectator") if self.builder else None
        return self.metadata(
            matches_live=bool(latest and latest["view"] == canonical), viewer=viewer, view=view
        )

    def reader(self) -> HistoryReader:
        groups = [dict(group) for group in self.groups]
        if self.builder is not None:
            # Keyframe, patch operations and their values are immutable once
            # captured. Only the outer patch list grows (or rolls over).
            group = self.builder.group
            groups[-1]["body"] = {**group, "patches": list(group["patches"])}
        return HistoryReader(self.directory, self.cache_id, groups)

    def resume_group(self, group: dict) -> None:
        self.builder = GroupBuilder.restore(group, copy_values=False, **_GROUP_OPTIONS)

    def prepare_manifest(self) -> dict[str, Any]:
        if self.builder is not None and self._dirty:
            self.groups[-1]["body"] = self.builder.group
        for group in self.groups:
            if "body" not in group:
                continue
            stored = (
                self.builder.encode(quality=1)
                if self.builder is not None and group["body"] is self.builder.group
                else encode(group["body"], quality=1)
            )
            filename = hashlib.sha256(stored).hexdigest() + ".br"
            if self.directory is not None:
                path = self.directory / filename
                if group.get("file") != filename or not path.is_file():
                    _atomic_bytes(path, stored)
                previous = group.get("file")
                if previous and previous != filename and _FILE.fullmatch(previous):
                    self._retired_files.add(previous)
            group["file"] = filename
        return {
            "format": FORMAT,
            "records": list(self.records),
            "active": self.active.copy(),
            "edits": list(self.edits),
            "anchors": dict(self.anchors),
            "groups": [{k: v for k, v in g.items() if k != "body"} for g in self.groups],
            "revision": self.revision,
            "epoch": self.epoch,
            "raw_count": self.raw_count,
            "gaps": list(self.gaps),
            "backfill_status": self.backfill_status,
            "last_anchor": list(self._last_anchor),
        }

    def committed(self) -> None:
        if self.directory is None:
            return
        for group in self.groups:
            group.pop("body", None)
        self._dirty = False
        keep = {group["file"] for group in self.groups}
        for filename in self._retired_files - keep:
            (self.directory / filename).unlink(missing_ok=True)
        self._retired_files.clear()

    def cleanup_orphans(self) -> None:
        if self.directory is None or not self.directory.is_dir():
            return
        keep = {g.get("file") for g in self.groups}
        for path in self.directory.iterdir():
            if (
                path.is_file()
                and path.name not in keep
                and (_FILE.fullmatch(path.name) or path.suffix == ".tmp")
            ):
                path.unlink(missing_ok=True)

    @classmethod
    def restore(
        cls,
        directory: Path,
        manifest: dict[str, Any],
        *,
        scope: HistoryScope = HistoryScope.CURRENT_ROUND,
    ) -> LiveHistory:
        if manifest.get("format") not in (2, FORMAT):
            raise HistoryUnavailable("Unsupported history storage format")
        history = cls(directory, scope=scope)
        history._legacy_anchor = manifest.get("format") == 2
        last_anchor = manifest.get("last_anchor", (None, None))
        history._last_anchor = (last_anchor[0], last_anchor[1])
        for name in (
            "records",
            "active",
            "edits",
            "anchors",
            "groups",
            "revision",
            "epoch",
            "raw_count",
            "gaps",
            "backfill_status",
        ):
            if name in manifest:
                setattr(history, name, deepcopy(manifest[name]))
        history.cleanup_orphans()
        if history.backfill_status == "unavailable":
            history.backfill_status = "pending"
        if history.groups:
            try:
                history.resume_group(history.reader().group(history.groups[-1]))
                if history.groups[-1]["start"] + history.groups[-1]["count"] != len(
                    history.records
                ):
                    history.note_gap(history.raw_count)
            except Exception as exc:
                logger.warning("History tail unavailable: %s", exc)
                history.note_gap(history.raw_count)
        return history


class HistoryReader:
    """Immutable read snapshot; safe to use outside the async game lock."""

    def __init__(self, directory: Path | None, cache_id: str, groups: list[dict]) -> None:
        self.directory, self.cache_id, self.groups = directory, cache_id, groups

    def group(self, descriptor: dict) -> dict:
        if "body" in descriptor:
            return descriptor["body"]
        filename = descriptor.get("file", "")
        if self.directory is None or not _FILE.fullmatch(filename):
            raise HistoryUnavailable("Missing history group")
        try:
            stored = (self.directory / filename).read_bytes()
            if hashlib.sha256(stored).hexdigest() + ".br" != filename:
                raise ValueError("History content hash does not match")
            return decode(stored)
        except Exception as exc:
            raise HistoryUnavailable("History group is missing or damaged") from exc

    def read(self, record_id: int, viewer: str) -> dict[str, Any]:
        key = (self.cache_id, viewer, record_id)
        with _CACHE_LOCK:
            if key in _CACHE:
                _CACHE.move_to_end(key)
                return deepcopy(_CACHE[key])
        body = self.read_many([record_id], viewer)[0]
        with _CACHE_LOCK:
            _CACHE[key] = deepcopy(body)
            while len(_CACHE) > 128:
                _CACHE.popitem(last=False)
        return body

    def read_many(self, record_ids: list[int], viewer: str) -> list[dict[str, Any]]:
        result = {}
        try:
            for descriptor in self.groups:
                ids = [
                    i
                    for i in record_ids
                    if descriptor["start"] <= i < descriptor["start"] + descriptor["count"]
                ]
                if ids:
                    group = self.group(descriptor)
                    public = reconstruct_many(project_member(group, "public"), ids)
                    if viewer == "spectator":
                        result.update(public)
                    else:
                        private_group = project_member(project_member(group, "private"), viewer)
                        private = reconstruct_many(private_group, ids)
                        result.update({i: apply_patch(public[i], private[i]) for i in ids})
            return [result[i] for i in record_ids]
        except Exception as exc:
            raise HistoryUnavailable("History position is unavailable") from exc

    def read_all(self, record_id: int) -> dict[str, Any]:
        descriptor = next(
            (g for g in self.groups if g["start"] <= record_id < g["start"] + g["count"]), None
        )
        if descriptor is None:
            raise HistoryUnavailable("History position is unavailable")
        try:
            body = unpack_views(reconstruct(self.group(descriptor), record_id))
        except Exception as exc:
            raise HistoryUnavailable("History position is unavailable") from exc
        return body


def public_position(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key not in ("anchor", "correction", "rewind_to", "kind")
    }

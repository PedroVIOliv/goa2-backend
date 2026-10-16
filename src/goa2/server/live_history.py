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
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from goa2.domain.types import HeroID
from goa2.domain.views import _build_board_view, build_view
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
FORMAT = 2
_CACHE: OrderedDict[tuple[str, str, int], dict[str, Any]] = OrderedDict()
_CACHE_LOCK = RLock()
_FILE = re.compile(r"^[0-9a-f]{64}\.br$")


class HistoryUnavailable(ValueError):
    """A known record cannot currently be reconstructed."""


def canonical_views(session: GameSession) -> dict[str, Any]:
    state = session.state
    board = _build_board_view(state)
    viewers = [None, *(h.id for team in state.teams.values() for h in team.heroes)]
    result = {}
    hero_views: dict[tuple[str, bool], dict[str, Any]] = {}
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


def pack_views(views: dict[str, Any]) -> dict[str, Any]:
    public = views["spectator"]
    return {
        "public": public,
        "private": {
            viewer: make_patch(public, body)
            for viewer, body in views.items()
            if viewer != "spectator"
        },
    }


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
    path.parent.mkdir(parents=True, exist_ok=True)
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
    def __init__(self, directory: Path | None = None) -> None:
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

    def anchor_key(self, session: GameSession) -> str | None:
        anchor = session.rollback_anchor_id
        if anchor != self._last_anchor[0]:
            # Digest allows anchors reconstructed in another process to match
            # anchors in a restored live session, whose generation ID differs.
            snapshot = session._rollback_snapshot
            digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
            self._last_anchor = (anchor, digest if anchor is not None else None)
        return self._last_anchor[1]

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
            canonical_views(session),
            raw_count,
            decision,
            anchor=self.anchor_key(session),
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
        packed = pack_views(views)
        if self.builder is None:
            self.builder = GroupBuilder(record_id, packed, copy_values=False)
            self.groups.append({"start": record_id, "count": 1})
        else:
            closed = self.builder.append(record_id, packed)
            if closed is not None:
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
        if keep < len(before):
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

    def metadata(self, *, matches_live: bool = True) -> dict[str, Any]:
        return {
            "revision": self.revision,
            "epoch": self.epoch,
            "position_id": self.active[-1] if self.active and matches_live else None,
            "predecessor_id": self.active[-2] if len(self.active) > 1 else None,
            "total": len(self.active),
            "availability": self.backfill_status,
            "gaps": deepcopy(self.gaps),
        }

    def metadata_for_view(self, view: dict, viewer: str | None) -> dict[str, Any]:
        canonical = {**view, "clock": None, "starting_position": None}
        latest = self.latest_views.get(viewer or "spectator") if self.builder else None
        return self.metadata(matches_live=bool(latest and latest["view"] == canonical))

    def reader(self) -> HistoryReader:
        groups = [dict(group) for group in self.groups]
        if self.builder is not None:
            # Keyframe, patch operations and their values are immutable once
            # captured. Only the outer patch list grows (or rolls over).
            group = self.builder.group
            groups[-1]["body"] = {**group, "patches": list(group["patches"])}
        return HistoryReader(self.directory, self.cache_id, groups)

    def prepare_manifest(self) -> dict[str, Any]:
        if self.builder is not None and self._dirty:
            self.groups[-1]["body"] = self.builder.group
        for group in self.groups:
            if "body" not in group:
                continue
            stored = encode(group["body"], quality=1)
            filename = hashlib.sha256(stored).hexdigest() + ".br"
            if self.directory is not None:
                path = self.directory / filename
                if not path.is_file():
                    _atomic_bytes(path, stored)
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
        }

    def committed(self) -> None:
        if self.directory is None:
            return
        for group in self.groups:
            group.pop("body", None)
        self._dirty = False
        self.cleanup_orphans()

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
    def restore(cls, directory: Path, manifest: dict[str, Any]) -> LiveHistory:
        if manifest.get("format") != FORMAT:
            raise HistoryUnavailable("Unsupported history storage format")
        history = cls(directory)
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
                history.builder = GroupBuilder.restore(
                    history.reader().group(history.groups[-1]), copy_values=False
                )
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

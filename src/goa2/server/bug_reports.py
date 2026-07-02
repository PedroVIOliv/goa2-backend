"""File-backed bug reports linked to replay moments.

One JSON file per report in ``data/bug_reports/`` (override with
``GOA2_BUG_REPORT_DIR``), mirroring how replays are stored. A report ties a
player-written title/description to the game's replay log via
``decision_index`` — the number of decisions already recorded at the moment
the report was submitted, which is exactly the seek position for
``ReplayCursor.seek()`` / ``GET /replays/{game_id}/state?decision=N``.

Reports with ``status == "open"`` pin their game's replay against TTL cleanup
(see ``replay.cleanup_old_replays``); resolving or deleting a report releases
the pin.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

from goa2.server.replay import _replay_dir

logger = logging.getLogger(__name__)

DEFAULT_BUG_REPORT_DIR = "data/bug_reports"
MAX_REPORTS_PER_GAME = 10


def _bug_report_dir() -> str:
    return os.environ.get("GOA2_BUG_REPORT_DIR", DEFAULT_BUG_REPORT_DIR)


def _report_path(report_id: str) -> Path:
    """Resolve a report id to its file, rejecting path traversal."""
    if not report_id or "/" in report_id or "\\" in report_id or report_id.startswith("."):
        raise FileNotFoundError(f"Bug report not found: {report_id}")
    return Path(_bug_report_dir()) / f"{report_id}.json"


def count_replay_decisions(game_id: str) -> int | None:
    """Number of decision (non-setup) lines in the game's replay log.

    This is the ``decision`` seek index for the moment "now". Returns None if
    the replay file doesn't exist.
    """
    path = Path(_replay_dir()) / f"{game_id}.jsonl"
    if not path.is_file():
        return None
    count = 0
    try:
        with open(path) as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if record.get("type") != "setup":
                    count += 1
    except OSError:
        logger.exception("Failed to read replay log for game %s", game_id)
        return None
    return count


def create_report(
    *,
    game_id: str,
    title: str,
    description: str,
    reporter_hero: str | None,
    decision_index: int | None,
    round_num: int,
    turn: int,
) -> dict[str, Any]:
    """Write a new open report to disk and return it."""
    report = {
        "id": f"br_{uuid.uuid4().hex[:8]}",
        "game_id": game_id,
        "title": title,
        "description": description,
        "reporter_hero": reporter_hero,
        "decision_index": decision_index,
        "round": round_num,
        "turn": turn,
        "status": "open",
        "created_at": time.time(),
        "resolved_at": None,
    }
    _write_report(report)
    return report


def _write_report(report: dict[str, Any]) -> None:
    directory = Path(_bug_report_dir())
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report['id']}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2))
    os.replace(tmp, path)


def load_report(report_id: str) -> dict[str, Any] | None:
    path = _report_path(report_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to read bug report %s", report_id)
        return None


def list_reports() -> list[dict[str, Any]]:
    """All reports, newest first. Malformed files are skipped."""
    directory = Path(_bug_report_dir())
    if not directory.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for f in directory.glob("*.json"):
        try:
            report = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            logger.warning("Skipping malformed bug report file %s", f.name)
            continue
        if isinstance(report, dict) and "id" in report:
            out.append(report)
    out.sort(key=lambda r: r.get("created_at") or 0, reverse=True)
    return out


def set_status(report_id: str, status: str) -> dict[str, Any] | None:
    """Set a report's status to 'open' or 'resolved'. Returns the updated report."""
    report = load_report(report_id)
    if report is None:
        return None
    report["status"] = status
    report["resolved_at"] = time.time() if status == "resolved" else None
    _write_report(report)
    return report


def delete_report(report_id: str) -> bool:
    path = _report_path(report_id)
    if not path.is_file():
        return False
    path.unlink()
    return True


def count_reports_for_game(game_id: str) -> int:
    return sum(1 for r in list_reports() if r.get("game_id") == game_id)


def open_report_game_ids() -> set[str]:
    """Game ids that have at least one open report (their replays are pinned)."""
    return {r["game_id"] for r in list_reports() if r.get("status") == "open" and r.get("game_id")}

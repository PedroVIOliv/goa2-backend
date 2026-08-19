"""Shared server-test fixtures."""

import os

import pytest

# Every on-disk location the server writes to, and the temp dir name to give it.
# Server tests build a real app via create_app(), which reads and writes these
# for real — without isolation the suite leaks fixture games into data/games and
# loads the developer's actual saves at startup (noisy, and a bad save can
# influence a test).
_ISOLATED_DIRS = {
    "GOA2_REPLAY_DIR": "replays",
    "GOA2_SHARE_DIR": "shares",
    "GOA2_SAVE_DIR": "games",
    "GOA2_BUG_REPORT_DIR": "bug_reports",
    "GOA2_LOG_DIR": "game_logs",
}


@pytest.fixture(autouse=True)
def _no_worker_subprocesses():
    """Server tests build hundreds of apps; don't spawn worker processes for each.

    Replay verification at game over would spawn one too, for every finished
    fixture game.
    """
    previous = {v: os.environ.get(v) for v in ("GOA2_PREWARM_WORKERS", "GOA2_VERIFY_REPLAYS")}
    os.environ["GOA2_PREWARM_WORKERS"] = "0"
    os.environ["GOA2_VERIFY_REPLAYS"] = "0"
    try:
        yield
    finally:
        for var, prev in previous.items():
            if prev is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = prev


@pytest.fixture(autouse=True)
def _isolate_data_dirs(tmp_path_factory):
    """Point every server data directory at a fresh temp dir, per test."""
    previous = {var: os.environ.get(var) for var in _ISOLATED_DIRS}
    for var, name in _ISOLATED_DIRS.items():
        os.environ[var] = str(tmp_path_factory.mktemp(name))
    try:
        yield
    finally:
        for var, prev in previous.items():
            if prev is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = prev

"""Shared server-test fixtures."""

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_replay_dir(tmp_path_factory):
    """Point replay logs at a temp dir so server tests never write data/replays."""
    prev = os.environ.get("GOA2_REPLAY_DIR")
    os.environ["GOA2_REPLAY_DIR"] = str(tmp_path_factory.mktemp("replays"))
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("GOA2_REPLAY_DIR", None)
        else:
            os.environ["GOA2_REPLAY_DIR"] = prev

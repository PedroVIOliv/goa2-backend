"""A finished game's replay is checked against itself, so breakage is visible.

A log that cannot be reconstructed is useless for sharing, viewing and
rewinding, and nothing notices until someone tries months later.

Both fixtures come from a real match; the corrupted one names a card that was
never in hand. Effects are registered explicitly: reconstruction silently
diverges without the registry, so a test that relied on another module having
imported the app would pass or fail by import order.
"""

from pathlib import Path

import pytest

from goa2.server.replay import verify_replay

FIXTURES = Path(__file__).parent.parent / "fixtures" / "replays"


@pytest.fixture(autouse=True)
def _effects_registered():
    from goa2.server.app import register_all_effects

    register_all_effects()


def test_a_sound_replay_verifies():
    result = verify_replay(str(FIXTURES / "reconstructs_ok.jsonl"))
    assert result["ok"] is True, result["error"]
    assert result["applied"] == result["total"] == 120
    assert result["error"] is None


def test_a_corrupted_replay_is_reported_with_the_failing_decision():
    result = verify_replay(str(FIXTURES / "corrupted.jsonl"))
    assert result["ok"] is False
    assert result["at"] is not None
    assert "no_such_card_xyz" in result["error"]


def test_reconstruction_needs_the_effect_registry():
    """Guards the trap that made this bug look like a replay defect.

    Without registered card effects every card resolves to nothing, the
    reconstruction diverges from the real match, and the failure surfaces far
    from its cause. The worker pool registers them in its initializer; this
    records why that matters.
    """
    from goa2.engine.effects import CardEffectRegistry

    assert CardEffectRegistry.get("liquid_leap") is not None


def test_a_missing_log_is_reported_not_raised():
    result = verify_replay("/nonexistent/replay.jsonl")
    assert result["ok"] is False
    assert result["error"]


def test_scheduling_is_disabled_by_env(monkeypatch):
    """The flag server tests rely on to avoid spawning a worker per finished game."""
    from goa2.server import replay as replay_module

    monkeypatch.setenv("GOA2_VERIFY_REPLAYS", "0")
    called = []
    monkeypatch.setattr(replay_module, "run_heavy", lambda *a: called.append(a))
    replay_module.verify_replay_in_background("whatever.jsonl", "game1")
    assert called == []


def test_scheduling_without_a_running_loop_is_a_noop(monkeypatch):
    """Called from sync code it must not raise — verification is best effort."""
    from goa2.server import replay as replay_module

    monkeypatch.setenv("GOA2_VERIFY_REPLAYS", "1")
    replay_module.verify_replay_in_background("whatever.jsonl", "game1")


def test_result_reports_which_engine_recorded_the_log():
    """A failure after an engine change is expected, not mysterious.

    Fixing game logic necessarily invalidates replays of games that exercised
    the old behaviour, so the verdict has to say which engine wrote the log.
    """
    result = verify_replay(str(FIXTURES / "reconstructs_ok.jsonl"))
    assert result["recorded_engine"] == "7d94633"
    assert result["current_engine"]
    assert result["engine_changed"] is True


def test_engine_is_unchanged_when_the_shas_match(monkeypatch):
    from goa2.server import replay as replay_module

    monkeypatch.setattr(replay_module, "_engine_revision", lambda: "7d94633")
    result = verify_replay(str(FIXTURES / "reconstructs_ok.jsonl"))
    assert result["engine_changed"] is False

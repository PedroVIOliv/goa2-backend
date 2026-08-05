"""Tests for trajectory recording (Seam 4 / T4).

Assert recording is off by default (behavior-neutral), that a recorded game
emits a decision row per decision plus one outcome, that JSONL streams to disk
and reloads, and that a state snapshot round-trips back into a GameState.
"""

from __future__ import annotations

import json

from automata.agents.heuristic_agent import HeuristicAgent
from automata.runtime.effects import register_all_effects
from automata.runtime.harness import run_game
from automata.runtime.trajectory import InMemoryRecorder, JsonlRecorder
from goa2.domain.state import GameState

RED = ["Wasp", "Xargatha"]
BLUE = ["Arien", "Brogan"]


def _agents() -> dict[str, HeuristicAgent]:
    a = HeuristicAgent(1)
    return {
        "hero_wasp": a,
        "hero_xargatha": a,
        "hero_arien": a,
        "hero_brogan": a,
    }


def test_recording_off_by_default_is_behavior_neutral() -> None:
    register_all_effects()

    def outcome() -> tuple[str | None, int, int]:
        r = run_game(RED, BLUE, _agents(), seed=3, max_steps=400)
        return (r.winner, r.rounds, r.steps)

    with_none = outcome()
    # Explicitly no recorder passed => identical result to default.
    r2 = run_game(RED, BLUE, _agents(), seed=3, max_steps=400, recorder=None)
    assert with_none == (r2.winner, r2.rounds, r2.steps)


def test_inmemory_recorder_captures_decisions_and_outcome() -> None:
    register_all_effects()
    rec = InMemoryRecorder()
    r = run_game(RED, BLUE, _agents(), seed=3, max_steps=400, recorder=rec)
    # At least a few decisions were made, all indexed contiguously.
    assert len(rec.decisions) >= 3
    assert [d["decision_index"] for d in rec.decisions] == list(range(len(rec.decisions)))
    # Every decision is CARD or INPUT and carries a state snapshot + legal keys.
    for d in rec.decisions:
        assert d["decision_kind"] in ("CARD", "INPUT")
        assert isinstance(d["state"], dict)
        assert isinstance(d["legal_keys"], list)
    # Exactly one outcome, consistent with the run result.
    assert rec.outcome is not None
    assert rec.outcome["winner"] == r.winner
    assert rec.outcome["reason"] == r.reason


def test_recording_does_not_change_the_game() -> None:
    register_all_effects()
    plain = run_game(RED, BLUE, _agents(), seed=5, max_steps=400)
    rec = InMemoryRecorder()
    recorded = run_game(RED, BLUE, _agents(), seed=5, max_steps=400, recorder=rec)
    assert (plain.winner, plain.rounds, plain.steps) == (
        recorded.winner,
        recorded.rounds,
        recorded.steps,
    )


def test_jsonl_recorder_streams_and_reloads(tmp_path) -> None:
    register_all_effects()
    path = tmp_path / "traj.jsonl"
    with JsonlRecorder(path, game_id="g0") as rec:
        run_game(RED, BLUE, _agents(), seed=3, max_steps=400, recorder=rec)

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    decisions = [r for r in rows if r["kind"] == "decision"]
    outcomes = [r for r in rows if r["kind"] == "outcome"]
    assert len(decisions) >= 3
    assert len(outcomes) == 1
    assert outcomes[0]["game_id"] == "g0"
    assert outcomes[0]["decisions"] == len(decisions)
    # decision_index is contiguous and game_id is stamped on every row.
    assert [d["decision_index"] for d in decisions] == list(range(len(decisions)))
    assert all(d["game_id"] == "g0" for d in decisions)


def test_snapshot_roundtrips_into_gamestate(tmp_path) -> None:
    register_all_effects()
    rec = InMemoryRecorder()
    run_game(RED, BLUE, _agents(), seed=3, max_steps=200, recorder=rec)
    assert rec.decisions
    snap = rec.decisions[0]["state"]
    # A recorded snapshot must validate back into a GameState with the same
    # round/turn — the contract learned-model data loaders rely on.
    restored = GameState.model_validate(snap)
    assert isinstance(restored, GameState)
    assert restored.round == snap["round"]
    assert restored.turn == snap["turn"]

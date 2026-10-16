"""Local ten-seat history benchmark, including real turn/upgrade progression.

Run from the repository: python tools/benchmark_live_history.py --decisions 700
Uses the same deterministic HOLD/pass fallback as automatic play. Timings exclude
engine resolution, and the paired baseline saves the same state without history.
All generated saves/logs stay in an owned temporary directory under .agent/.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import tempfile
from functools import partial
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from goa2.bootstrap import register_all_effects  # noqa: E402
from goa2.domain.input import InputResponse  # noqa: E402
from goa2.domain.models import GamePhase  # noqa: E402
from goa2.engine.persistence import save_game  # noqa: E402
from goa2.engine.session import GameSession  # noqa: E402
from goa2.engine.setup import GameSetup  # noqa: E402
from goa2.server.live_history import _CACHE  # noqa: E402
from goa2.server.map_paths import resolve_map_path  # noqa: E402
from goa2.server.registry import GameRegistry  # noqa: E402
from goa2.server.time_control import _timeout_selection, _upgrade_card_ids  # noqa: E402


def summarize(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "p50_ms": round(statistics.median(samples), 3),
        "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 3),
    }


def retained_bytes(value: Any, seen: set[int] | None = None) -> int:
    """Reachable Python storage estimate; excludes native buffers and process RSS."""
    seen = set() if seen is None else seen
    if id(value) in seen:
        return 0
    seen.add(id(value))
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(retained_bytes(k, seen) + retained_bytes(v, seen) for k, v in value.items())
    elif isinstance(value, (list, tuple)):
        size += sum(retained_bytes(v, seen) for v in value)
    elif hasattr(value, "__dict__"):
        size += retained_bytes(vars(value), seen)
    return size


def run(decisions: int) -> dict[str, Any]:
    register_all_effects()
    base = (ROOT / ".agent").resolve()
    base.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=base, prefix="history-benchmark-") as temporary:
        directory = Path(temporary).resolve()
        assert directory.is_relative_to(base)
        os.environ["GOA2_REPLAY_DIR"] = str(directory / "replays")
        os.environ["GOA2_LOG_DIR"] = str(directory / "logs")
        red = ["Arien", "Min", "Brogan", "Tali", "Swift"]
        blue = ["Wasp", "Razzle", "Emmitt", "Sabina", "Snorri"]
        state = GameSetup.create_game(resolve_map_path("forgotten_island"), red, blue, seed=42)
        registry = GameRegistry(str(directory / "games"))
        hero_ids = [h.id for team in state.teams.values() for h in team.heroes]
        game = registry.create_game(GameSession(state), hero_ids, game_id="benchmark")
        recorder = game.replay_recorder
        recorder.record_setup(
            map_name="forgotten_island",
            red_heroes=red,
            blue_heroes=blue,
            game_type="LONG",
            cheats=False,
            seed=42,
        )
        capture, persistence, total, baseline = [], [], [], []
        rng, result = random.Random(7), None
        try:
            while len(total) < decisions:
                session, state = game.session, game.session.state
                round_num, turn = state.round, state.turn
                if state.phase == GamePhase.GAME_OVER:
                    break
                if state.phase == GamePhase.PLANNING:
                    hero_id = next((h for h in hero_ids if h not in state.pending_inputs), None)
                    if hero_id is None:
                        hero_id = next(h for h in hero_ids if h not in state.planning_done)
                        result = session.finish_planning(hero_id)
                        record = partial(recorder.record_finish_planning, hero_id, round_num, turn)
                    else:
                        hero = state.get_hero(hero_id)
                        if hero.hand:
                            card = hero.hand[0]
                            result = session.commit_card(hero_id, card)
                            record = partial(
                                recorder.record_commit, hero_id, card.id, round_num, turn
                            )
                        else:
                            result = session.pass_turn(hero_id)
                            record = partial(recorder.record_pass, hero_id, round_num, turn)
                else:
                    if result is None or result.input_request is None:
                        result = session.advance()
                    request = result.input_request
                    if request is None:
                        continue
                    if request.player_id == "simultaneous":
                        hero_id = next(iter(request.context["players"]))
                        selection = {
                            "hero_id": hero_id,
                            "card_id": rng.choice(_upgrade_card_ids(request, hero_id)),
                        }
                    else:
                        selection = _timeout_selection(request, rng)
                    result = session.advance(
                        InputResponse(request_id=request.id, selection=selection)
                    )
                    record = partial(
                        recorder.record_input, request.player_id, selection, round_num, turn
                    )
                game.last_result = result
                start = perf_counter()
                record()
                captured = perf_counter()
                registry.save_game(game.game_id)
                saved = perf_counter()
                capture.append((captured - start) * 1000)
                persistence.append((saved - captured) * 1000)
                total.append((saved - start) * 1000)
                start = perf_counter()
                save_game(
                    game_id="baseline",
                    state=session.state,
                    player_tokens=game.player_tokens,
                    spectator_token=game.spectator_token,
                    hero_to_token=game.hero_to_token,
                    created_at=game.created_at,
                    save_dir=str(directory / "games"),
                    rollback_snapshot=session._rollback_snapshot,
                    rollback_actor_id=session._rollback_actor_id,
                    replay_log=recorder.records,
                    hero_names=game.hero_names,
                )
                baseline.append((perf_counter() - start) * 1000)
            history = game.history
            reader, positions = history.reader(), history.active
            cold, warm, pages = [], [], []
            for _ in range(20):
                offset = rng.randrange(len(positions))
                position = positions[offset]
                _CACHE.clear()
                start = perf_counter()
                reader.read(position, "hero_arien")
                cold.append((perf_counter() - start) * 1000)
                start = perf_counter()
                reader.read(position, "hero_arien")
                warm.append((perf_counter() - start) * 1000)
                start = perf_counter()
                reader.read_many(positions[offset : offset + 30], "hero_arien")
                pages.append((perf_counter() - start) * 1000)
            return {
                "decisions": len(total),
                "active_positions": len(positions),
                "round": session.state.round,
                "capture": summarize(capture),
                "save_including_history": summarize(persistence),
                "record_and_save": summarize(total),
                "baseline_save": summarize(baseline),
                "paired_history_overhead": summarize(
                    [a - b for a, b in zip(total, baseline, strict=True)]
                ),
                "cold_read": summarize(cold),
                "warm_read": summarize(warm),
                "page_materialization": summarize(pages),
                "retained_python_bytes": retained_bytes((history, _CACHE)),
                "history_bytes": sum(p.stat().st_size for p in history.directory.iterdir()),
                "save_bytes": (directory / "games" / "benchmark.json").stat().st_size,
                "groups": len(history.groups),
            }
        finally:
            game.game_logger.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decisions", type=int, default=700)
    args = parser.parse_args()
    if args.decisions < 1:
        parser.error("--decisions must be positive")
    print(json.dumps(run(args.decisions), indent=2))

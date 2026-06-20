"""CLI to reconstruct a game from its replay log for bug investigation.

Examples:
    # Replay the whole game and print where it ended up
    python -m goa2.scripts.replay data/replays/<game_id>.jsonl

    # Stop at the start of round 3, turn 2 (the moment a bug was reported)
    python -m goa2.scripts.replay data/replays/<game_id>.jsonl --round 3 --turn 2

    # Stop right before the 47th decision
    python -m goa2.scripts.replay data/replays/<game_id>.jsonl --decision 47

    # Also dump a player-scoped view at the stop point
    python -m goa2.scripts.replay data/replays/<game_id>.jsonl --round 3 --view hero_arien
"""

from __future__ import annotations

import argparse
import json
import sys

from goa2.domain.types import HeroID
from goa2.domain.views import build_view
from goa2.server.replay import load_replay, replay_game


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="goa2-replay", description=__doc__)
    parser.add_argument("file", help="Path to a replay .jsonl file")
    parser.add_argument("--round", type=int, default=None, help="Stop at the start of this round")
    parser.add_argument("--turn", type=int, default=None, help="Stop at this turn (with --round)")
    parser.add_argument(
        "--decision", type=int, default=None, help="Stop before the Nth recorded decision"
    )
    parser.add_argument(
        "--view", default=None, help="Dump build_view() scoped to this hero id at the stop point"
    )
    args = parser.parse_args(argv)

    try:
        setup, decisions = load_replay(args.file)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Replay: map={setup['map']} red={setup['red']} blue={setup['blue']} "
        f"game_type={setup.get('game_type')} engine={setup.get('engine')} "
        f"decisions={len(decisions)}"
    )

    session = replay_game(
        args.file,
        until_round=args.round,
        until_turn=args.turn,
        until_decision=args.decision,
    )
    state = session.state
    print(
        f"Stopped at: phase={state.phase.value} round={state.round} turn={state.turn} "
        f"current_actor={state.current_actor_id}"
    )

    if args.view:
        view = build_view(state, for_hero_id=HeroID(args.view))
        print(json.dumps(view, indent=2, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Persistence regressions that require an isolated production import order."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


def test_nested_composite_filters_survive_production_import_order():
    """Server-first imports must not cache a depth-limited filter schema."""
    repo_root = Path(__file__).resolve().parents[2]
    script = textwrap.dedent("""
        import tempfile

        import goa2.server.app
        from goa2.domain.board import Board
        from goa2.domain.hex import Hex
        from goa2.domain.models import GamePhase, Hero, Team, TeamColor
        from goa2.domain.models.enums import TargetType
        from goa2.domain.state import GameState
        from goa2.domain.tile import Tile
        from goa2.engine.filters import AndFilter, OrFilter, RangeFilter, SpawnPointFilter
        from goa2.engine.handler import push_steps
        from goa2.engine.persistence import load_game, save_game
        from goa2.engine.steps import SelectStep

        origin = Hex(q=0, r=0, s=0)
        board = Board()
        board.tiles[origin] = Tile(hex=origin)
        hero = Hero(id="hero_test", name="Test", team=TeamColor.RED, deck=[])
        state = GameState(
            board=board,
            teams={
                TeamColor.RED: Team(color=TeamColor.RED, heroes=[hero], minions=[]),
                TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
            },
            current_actor_id="hero_test",
            phase=GamePhase.RESOLUTION,
        )
        state.place_entity("hero_test", origin)
        push_steps(
            state,
            [
                SelectStep(
                    target_type=TargetType.HEX,
                    prompt="Choose a hex",
                    filters=[
                        OrFilter(
                            filters=[
                                AndFilter(
                                    filters=[
                                        RangeFilter(max_range=3),
                                        SpawnPointFilter(has_spawn_point=False),
                                    ]
                                )
                            ]
                        )
                    ],
                )
            ],
        )

        with tempfile.TemporaryDirectory() as save_dir:
            path = save_game(
                game_id="nested",
                state=state,
                player_tokens={"token": "hero_test"},
                spectator_token="spectator",
                hero_to_token={"hero_test": "token"},
                created_at=0,
                save_dir=save_dir,
            )
            loaded = load_game(str(path))

        assert loaded["last_result"].input_request is not None
        step = loaded["session"].state.execution_stack[-1]
        inner = step.filters[0].filters[0].filters
        assert type(inner[0]).__name__ == "RangeFilter"
        assert inner[0].max_range == 3
        assert type(inner[1]).__name__ == "SpawnPointFilter"
        assert inner[1].has_spawn_point is False
        """)
    env = {**os.environ, "PYTHONPATH": str(repo_root / "src")}
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

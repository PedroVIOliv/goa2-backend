"""Evaluation harness: measure one agent against another over many games.

Every stronger agent must beat the previous baseline over a statistically
meaningful sample, so this is the yardstick the whole AI effort is judged on.

Design:
- Two agent *factories* (seed -> Agent) play a fixed hero matchup.
- **Sides are alternated** across games so first-mover / tie-breaker-coin bias
  cancels out (agent A plays Red half the time, Blue the other half).
- Deterministic given ``base_seed`` (game i uses seed base_seed + i).
- Win-rate is reported with a **Wilson score interval** (sane for proportions,
  including near 0/1 and small samples).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

from ..agents.base import Agent
from ..runtime.harness import DEFAULT_MAP, run_game

AgentFactory = Callable[[int], Agent]


def hero_id(name: str) -> str:
    """Engine hero id from a hero name, e.g. 'Wasp' -> 'hero_wasp'."""
    return f"hero_{name.lower()}"


@dataclass
class MatchupResult:
    label_a: str
    label_b: str
    games: int
    a_wins: int
    b_wins: int
    draws: int
    avg_rounds: float

    @property
    def decisive(self) -> int:
        return self.a_wins + self.b_wins

    @property
    def a_winrate(self) -> float:
        """A's win-rate among decisive games (draws excluded)."""
        return self.a_wins / self.decisive if self.decisive else 0.0

    def wilson_ci(self, z: float = 1.96) -> tuple[float, float]:
        """Wilson score interval for A's win-rate over decisive games."""
        n = self.decisive
        if n == 0:
            return (0.0, 1.0)
        p = self.a_wins / n
        denom = 1 + z * z / n
        center = (p + z * z / (2 * n)) / denom
        half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
        return (max(0.0, center - half), min(1.0, center + half))

    def summary(self) -> str:
        lo, hi = self.wilson_ci()
        return (
            f"{self.label_a} vs {self.label_b}: "
            f"{self.a_wins}-{self.b_wins}"
            f"{f' ({self.draws} draws)' if self.draws else ''} "
            f"over {self.games} games | {self.label_a} win-rate "
            f"{self.a_winrate:.1%} (95% CI {lo:.1%}-{hi:.1%}) | "
            f"avg {self.avg_rounds:.1f} rounds"
        )


@dataclass(frozen=True)
class _GameOutcome:
    a_won: bool | None  # True/False for decisive, None for draw
    rounds: int


def _play_game(
    i: int,
    a_factory: AgentFactory,
    b_factory: AgentFactory,
    red_heroes: list[str],
    blue_heroes: list[str],
    base_seed: int,
    alternate_sides: bool,
    map_path: str,
    game_type: str,
) -> _GameOutcome:
    """Play one game (index ``i``) and return its outcome from A's perspective.

    Pure and self-contained (depends only on its args + the per-game seed), so it
    is safe to run in a worker process. Determinism is per-game, so parallel
    execution yields the same aggregate as serial.
    """
    seed = base_seed + i
    # A plays Red on even games, Blue on odd games (when alternating).
    a_is_red = (i % 2 == 0) or not alternate_sides
    a_agent = a_factory(seed * 2 + 1)
    b_agent = b_factory(seed * 2 + 2)

    red_agent, blue_agent = (a_agent, b_agent) if a_is_red else (b_agent, a_agent)
    agents: dict[str, Agent] = {}
    for name in red_heroes:
        agents[hero_id(name)] = red_agent
    for name in blue_heroes:
        agents[hero_id(name)] = blue_agent

    result = run_game(
        red_heroes, blue_heroes, agents, map_path=map_path, game_type=game_type, seed=seed
    )
    winner = (result.winner or "").upper()
    if winner not in ("RED", "BLUE"):
        return _GameOutcome(a_won=None, rounds=result.rounds)
    return _GameOutcome(a_won=(winner == "RED") == a_is_red, rounds=result.rounds)


# Module-level shim so ProcessPoolExecutor can pickle the per-game call. It
# receives one tuple of (index, all fixed args) and unpacks it.
def _play_game_star(args: tuple[object, ...]) -> _GameOutcome:
    return _play_game(*args)  # type: ignore[arg-type]


def evaluate(
    a_factory: AgentFactory,
    b_factory: AgentFactory,
    *,
    red_heroes: list[str],
    blue_heroes: list[str],
    games: int = 100,
    base_seed: int = 0,
    alternate_sides: bool = True,
    map_path: str = DEFAULT_MAP,
    game_type: str = "QUICK",
    label_a: str = "A",
    label_b: str = "B",
    workers: int = 1,
) -> MatchupResult:
    """Play ``games`` matches of A vs B and aggregate the outcome.

    ``workers`` > 1 runs games across a process pool (games are independent and
    CPU-bound, so this is a near-linear speedup). Results are identical to serial
    because each game is fully determined by its seed. Two requirements when
    ``workers`` > 1:

    * the ``a_factory`` / ``b_factory`` must be picklable (module-level callables
      or picklable objects, not lambdas/closures);
    * the calling script must guard its entry point with
      ``if __name__ == "__main__":`` — on spawn-start platforms (macOS/Windows)
      the workers re-import the caller's module, and an unguarded call spawns
      recursively. The CLI (``automata.evaluation.cli``) already does this.
    """
    fixed = (
        a_factory,
        b_factory,
        red_heroes,
        blue_heroes,
        base_seed,
        alternate_sides,
        map_path,
        game_type,
    )

    if workers <= 1:
        outcomes = [_play_game(i, *fixed) for i in range(games)]
    else:
        tasks = [(i, *fixed) for i in range(games)]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            outcomes = list(pool.map(_play_game_star, tasks))

    a_wins = sum(1 for o in outcomes if o.a_won is True)
    b_wins = sum(1 for o in outcomes if o.a_won is False)
    draws = sum(1 for o in outcomes if o.a_won is None)
    total_rounds = sum(o.rounds for o in outcomes)

    return MatchupResult(
        label_a=label_a,
        label_b=label_b,
        games=games,
        a_wins=a_wins,
        b_wins=b_wins,
        draws=draws,
        avg_rounds=total_rounds / games if games else 0.0,
    )

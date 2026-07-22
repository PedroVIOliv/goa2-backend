"""State evaluation features for heuristic (and later, learned) agents.

`state_features(state, team)` returns a named feature vector (differentials
from ``team``'s perspective); `evaluate_state(state, team)` is the hand-weighted
dot product of that vector — positive = good for ``team``. Splitting the two
lets the same features feed a *learned* value/policy later (Rungs 2-3) without
recomputing anything, while keeping today's behavior byte-identical.

It reuses the engine's own lane/push helpers so "winning the push" matches the
rules exactly.

Signals (rulebook win conditions first):
- Life-counter differential  — a team loses at 0 (hero-kill race).
- Push progress differential — zones each team has pushed the battle toward the
  enemy throne (`endgame_totals`); the other win condition.
- Battle-zone minion control — who is winning the current minion battle.
- Tempo — hero levels, gold, and how many heroes are alive on the board.
"""

from __future__ import annotations

from goa2.domain.models import TeamColor
from goa2.domain.state import GameState
from goa2.engine.map_logic import endgame_totals

# Terminal sentinel; dwarfs positional signal so wins/losses dominate.
WIN_SCORE = 1_000_000.0

# Feature weights (hand-tuned; life and push are the win conditions). Keyed by
# feature name so weights and features stay aligned as the set grows.
FEATURE_WEIGHTS: dict[str, float] = {
    "life_diff": 100.0,
    "push_diff": 60.0,
    "minion_diff": 8.0,
    "level_diff": 5.0,
    "alive_diff": 15.0,
    "gold_diff": 1.0,
}

# Stable ordering for callers that want a plain vector (e.g. learned models).
FEATURE_NAMES: tuple[str, ...] = tuple(FEATURE_WEIGHTS.keys())


def _enemy(team: TeamColor) -> TeamColor:
    return TeamColor.BLUE if team == TeamColor.RED else TeamColor.RED


def _battle_zone_minion_counts(state: GameState) -> dict[TeamColor, int]:
    """Minions each team currently has standing in a battle zone."""
    counts = {TeamColor.RED: 0, TeamColor.BLUE: 0}
    battle_hexes = set()
    for zone_id in state.battle_zones.values():
        zone = state.board.zones.get(zone_id)
        if zone:
            battle_hexes.update(zone.hexes)
    for color, team in state.teams.items():
        for minion in team.minions:
            loc = state.unit_locations.get(minion.id)
            if loc is not None and loc in battle_hexes:
                counts[color] = counts.get(color, 0) + 1
    return counts


def _heroes_alive(state: GameState, team: TeamColor) -> int:
    return sum(1 for h in state.teams[team].heroes if state.has_board_presence(h.id))


def state_features(state: GameState, team: TeamColor) -> dict[str, float]:
    """Named feature differentials for ``state`` from ``team``'s perspective.

    Non-terminal only — terminal states are handled by ``evaluate_state`` (and,
    for learning, by the recorded game outcome). Every value is an *own minus
    enemy* differential so the sign already encodes "good for us".
    """
    enemy = _enemy(team)

    my_life = state.teams[team].life_counters
    en_life = state.teams[enemy].life_counters

    push = endgame_totals(state)  # {team: zones between own throne and battle zones}
    minions = _battle_zone_minion_counts(state)

    my_level = sum(h.level for h in state.teams[team].heroes)
    en_level = sum(h.level for h in state.teams[enemy].heroes)
    my_gold = sum(h.gold for h in state.teams[team].heroes)
    en_gold = sum(h.gold for h in state.teams[enemy].heroes)

    return {
        "life_diff": float(my_life - en_life),
        "push_diff": float(push.get(team, 0) - push.get(enemy, 0)),
        "minion_diff": float(minions.get(team, 0) - minions.get(enemy, 0)),
        "level_diff": float(my_level - en_level),
        "alive_diff": float(_heroes_alive(state, team) - _heroes_alive(state, enemy)),
        "gold_diff": float(my_gold - en_gold),
    }


def feature_vector(state: GameState, team: TeamColor) -> list[float]:
    """``state_features`` as a plain vector in canonical ``FEATURE_NAMES`` order."""
    feats = state_features(state, team)
    return [feats[name] for name in FEATURE_NAMES]


def evaluate_state(state: GameState, team: TeamColor) -> float:
    """Score ``state`` from ``team``'s perspective (higher = better).

    Terminal states dominate; otherwise the hand-weighted dot product of
    ``state_features``.
    """
    if state.winner is not None:
        winner = state.winner.upper() if isinstance(state.winner, str) else state.winner
        won = winner == team.value or winner == team.name
        return WIN_SCORE if won else -WIN_SCORE

    feats = state_features(state, team)
    return sum(FEATURE_WEIGHTS[name] * feats[name] for name in FEATURE_WEIGHTS)

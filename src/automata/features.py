"""State evaluation features for heuristic (and later, MCTS rollout) agents.

`evaluate_state(state, team)` returns a scalar from ``team``'s perspective:
positive = good for that team. It reuses the engine's own lane/push helpers so
the notion of "winning the push" matches the rules exactly.

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

# Feature weights (hand-tuned; life and push are the win conditions).
W_LIFE = 100.0
W_PUSH = 60.0
W_MINION = 8.0
W_LEVEL = 5.0
W_ALIVE = 15.0
W_GOLD = 1.0


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


def evaluate_state(state: GameState, team: TeamColor) -> float:
    """Score ``state`` from ``team``'s perspective (higher = better)."""
    enemy = _enemy(team)

    # Terminal.
    if state.winner is not None:
        winner = state.winner.upper() if isinstance(state.winner, str) else state.winner
        won = winner == team.value or winner == team.name
        return WIN_SCORE if won else -WIN_SCORE

    my_life = state.teams[team].life_counters
    en_life = state.teams[enemy].life_counters

    push = endgame_totals(state)  # {team: zones between own throne and battle zones}
    minions = _battle_zone_minion_counts(state)

    my_level = sum(h.level for h in state.teams[team].heroes)
    en_level = sum(h.level for h in state.teams[enemy].heroes)
    my_gold = sum(h.gold for h in state.teams[team].heroes)
    en_gold = sum(h.gold for h in state.teams[enemy].heroes)

    return (
        W_LIFE * (my_life - en_life)
        + W_PUSH * (push.get(team, 0) - push.get(enemy, 0))
        + W_MINION * (minions.get(team, 0) - minions.get(enemy, 0))
        + W_LEVEL * (my_level - en_level)
        + W_ALIVE * (_heroes_alive(state, team) - _heroes_alive(state, enemy))
        + W_GOLD * (my_gold - en_gold)
    )

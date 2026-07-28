"""Greedy heuristic agent.

Picks locally-best decisions from the engine's enumerated legal options using
fast static scoring.

Priorities, roughly:
- Play impactful cards (attack when a target is reachable, else advance).
- Attack enemy heroes > enemy minions (esp. in the battle zone).
- Move toward the enemy throne / the fight (push the objective).
- Defend rather than die; take the biggest number when asked.
"""

from __future__ import annotations

from typing import Any

from goa2.domain.input import InputRequest
from goa2.domain.models import ActionType, TeamColor
from goa2.domain.models.card import Card
from goa2.domain.models.unit import Hero
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.engine.map_logic import zones_between

from .base import option_selection_value

# CHOOSE_ACTION priority (higher = preferred as the played action).
_ACTION_PRIORITY = {
    ActionType.ATTACK: 5,
    ActionType.SKILL: 4,
    ActionType.MOVEMENT: 3,
    ActionType.FAST_TRAVEL: 2,
    ActionType.DEFENSE: 2,
    ActionType.CLEAR: 1,
    ActionType.HOLD: 0,
}


def _qrs(loc: Any) -> tuple[int, int, int] | None:
    if loc is None:
        return None
    if isinstance(loc, dict):
        q, r = int(loc.get("q", 0)), int(loc.get("r", 0))
        return (q, r, int(loc.get("s", -q - r)))
    q, r = getattr(loc, "q", None), getattr(loc, "r", None)
    if q is None or r is None:
        return None
    s = getattr(loc, "s", None)
    return (int(q), int(r), int(s if s is not None else -q - r))


def _dist(a: Any, b: Any) -> int:
    ca, cb = _qrs(a), _qrs(b)
    if ca is None or cb is None:
        return 99
    return (abs(ca[0] - cb[0]) + abs(ca[1] - cb[1]) + abs(ca[2] - cb[2])) // 2


class HeuristicAgent:
    def __init__(self, seed: int = 0) -> None:
        import random

        self._rng = random.Random(seed)

    # --- helpers -----------------------------------------------------------
    def _enemy_positions(self, state: GameState, team: TeamColor) -> list[Any]:
        enemy = TeamColor.BLUE if team == TeamColor.RED else TeamColor.RED
        out = []
        for unit in [*state.teams[enemy].heroes, *state.teams[enemy].minions]:
            loc = state.unit_locations.get(unit.id)
            if loc is not None:
                out.append(loc)
        return out

    def _unit_team(self, state: GameState, uid: str) -> TeamColor | None:
        for color, team in state.teams.items():
            if any(u.id == uid for u in [*team.heroes, *team.minions]):
                return color
        return None

    def _is_hero(self, state: GameState, uid: str) -> bool:
        return any(h.id == uid for t in state.teams.values() for h in t.heroes)

    def _zone_of(self, state: GameState, loc: Any) -> str | None:
        for zid, zone in state.board.zones.items():
            if loc in zone.hexes:
                return zid
        return None

    # --- planning ----------------------------------------------------------
    def choose_card(self, state: GameState, hero: Hero) -> Card | None:
        if not hero.hand:
            return None
        team = hero.team or TeamColor.RED
        pos = state.unit_locations.get(hero.id)
        enemies = self._enemy_positions(state, team)
        nearest = min((_dist(pos, e) for e in enemies), default=99) if pos else 99

        def score(card: Card) -> float:
            pa = card.primary_action
            val = card.primary_action_value or 0
            if pa == ActionType.ATTACK:
                reach = card.range_value or 1
                reachable = nearest <= reach
                return 10 + val + (5 if reachable else -3)
            if pa == ActionType.SKILL:
                return 6
            if pa == ActionType.MOVEMENT:
                return 5 + (3 if nearest > 2 else 0)
            if pa == ActionType.DEFENSE:
                return 4
            return 3

        # Highest score; break ties by initiative (act earlier), then rng.
        best = max(hero.hand, key=lambda c: (score(c), c.initiative, self._rng.random()))
        return best

    # --- resolution --------------------------------------------------------
    def choose_input(self, state: GameState, request: InputRequest) -> Any:
        rt = request.request_type.value
        opts = list(request.options)

        if rt == "UPGRADE_PHASE":
            return self._choose_upgrade(request)

        if not opts:
            return "SKIP" if request.can_skip else None

        if rt == "CHOOSE_ACTION":
            best = max(opts, key=self._action_priority)
            return option_selection_value(best)

        if rt in ("SELECT_UNIT", "SELECT_ENEMY", "SELECT_UNIT_OR_TOKEN"):
            hero_team = self._acting_team(state, request)
            best = max(opts, key=lambda o: self._unit_score(state, o, hero_team))
            return option_selection_value(best)

        if rt in ("SELECT_HEX", "MOVEMENT_HEX", "FAST_TRAVEL_DESTINATION", "CHOOSE_RESPAWN_HEX"):
            hero_team = self._acting_team(state, request)
            best = max(opts, key=lambda o: self._hex_score(state, o, hero_team))
            return option_selection_value(best)

        if rt == "SELECT_NUMBER":
            # More (push/move/repeat) is usually better.
            return max((option_selection_value(o) for o in opts), key=lambda v: _as_int(v))

        if rt in ("DEFENSE_CARD", "SELECT_CARD_OR_PASS"):
            # Prefer to defend (survive) rather than skip into defeat; pick the
            # option advertising the highest defense value if present.
            best = max(opts, key=lambda o: _as_int(o.metadata.get("defense", 0)))
            return option_selection_value(best)

        # Default: first concrete option.
        return option_selection_value(opts[0])

    # --- scoring -----------------------------------------------------------
    def _action_priority(self, option: Any) -> int:
        return _ACTION_PRIORITY.get(option.metadata.get("type"), 0)

    def _acting_team(self, state: GameState, request: InputRequest) -> TeamColor:
        for uid in (request.player_id, state.current_actor_id):
            if not uid:
                continue
            hero = state.get_hero(HeroID(str(uid)))
            if hero is not None and hero.team is not None:
                return hero.team
        return TeamColor.RED

    def _unit_score(self, state: GameState, option: Any, team: TeamColor) -> float:
        uid = option.id
        ut = self._unit_team(state, uid)
        if ut is None:
            return 0.0
        enemy = ut != team
        if not enemy:
            return -5.0
        base = 10.0 if self._is_hero(state, uid) else 5.0
        loc = state.unit_locations.get(uid)
        in_battle = loc is not None and any(
            loc in state.board.zones[z].hexes for z in state.battle_zones.values()
        )
        return base + (2.0 if in_battle else 0.0)

    def _hex_score(self, state: GameState, option: Any, team: TeamColor) -> float:
        hexd = option.metadata.get("hex")
        if hexd is None:
            return 0.0
        zid = self._zone_of(state, _HexLike(hexd))
        if zid is None:
            return 0.0
        lane_id = next(iter(state.battle_zones), None)
        toward_enemy = zones_between(state, team, lane_id, zid) if lane_id else 0
        return float(toward_enemy)

    def _choose_upgrade(self, request: InputRequest) -> Any:
        players = request.context.get("players", {})
        for hid, info in players.items():
            if info.get("remaining", 0) > 0 and info.get("options"):
                # Prefer a group containing an attack card; else first group.
                groups = info["options"]
                group = next(
                    (
                        g
                        for g in groups
                        if any(
                            d.get("primary_action") == ActionType.ATTACK
                            for d in g.get("card_details", [])
                        )
                    ),
                    groups[0],
                )
                pair = group.get("pair") or [d["id"] for d in group.get("card_details", [])]
                return {"hero_id": hid, "card_id": pair[0]}
        return None


class _HexLike:
    """Wrap a {q,r,s} dict so `x in zone.hexes` works (Hex equality by coords)."""

    __slots__ = ("q", "r", "s")

    def __init__(self, d: dict[str, Any]) -> None:
        self.q = d.get("q", 0)
        self.r = d.get("r", 0)
        self.s = d.get("s", d.get("q", 0) * -1 - d.get("r", 0))

    def __eq__(self, other: object) -> bool:
        return (
            getattr(other, "q", None) == self.q
            and getattr(other, "r", None) == self.r
            and getattr(other, "s", None) == self.s
        )

    def __hash__(self) -> int:
        return hash((self.q, self.r, self.s))


def _as_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0

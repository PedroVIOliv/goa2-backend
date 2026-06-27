"""MINION_BATTLE_EXCLUSION: Wuk's Claim/Assert Dominance (no targeting)."""

from __future__ import annotations

from goa2.domain.board import Board, Zone
from goa2.domain.hex import Hex
from goa2.domain.models import Hero, Minion, MinionType, Team, TeamColor
from goa2.domain.models.effect import (
    ActiveEffect,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.state import GameState
from goa2.domain.types import HeroID
from goa2.engine.steps.combat import MinionBattleStep

CENTER = Hex(q=0, r=0, s=0)
# The six neighbors of CENTER.
NEIGHBORS = [
    Hex(q=1, r=-1, s=0),
    Hex(q=1, r=0, s=-1),
    Hex(q=0, r=1, s=-1),
    Hex(q=-1, r=1, s=0),
    Hex(q=-1, r=0, s=1),
    Hex(q=0, r=-1, s=1),
]
FAR = [Hex(q=3, r=0, s=-3), Hex(q=4, r=0, s=-4)]


def _build(
    *,
    red_minions: int,
    blue_adjacent: int,
    blue_heavy_adjacent: int = 0,
    caps: list[int],
) -> GameState:
    """Wuk (RED) at CENTER; `blue_adjacent` BLUE minions on neighbor hexes;
    `red_minions` RED minions on far hexes. One exclusion effect per cap."""
    zone_hexes = {CENTER, *NEIGHBORS, *FAR}
    board = Board()
    board.zones = {"Z": Zone(id="Z", label="Z", hexes=zone_hexes)}
    board.populate_tiles_from_zones()

    wuk = Hero(id=HeroID("hero_wuk"), name="Wuk", team=TeamColor.RED, deck=[])
    reds = [
        Minion(id=f"r{i}", name=f"R{i}", type=MinionType.MELEE, team=TeamColor.RED)
        for i in range(red_minions)
    ]
    blues: list[Minion] = []
    for i in range(blue_adjacent):
        heavy = i < blue_heavy_adjacent
        blues.append(
            Minion(
                id=f"b{i}",
                name=f"B{i}",
                type=MinionType.HEAVY if heavy else MinionType.MELEE,
                team=TeamColor.BLUE,
            )
        )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[wuk], minions=reds),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=blues),
        },
        current_actor_id="hero_wuk",
    )
    state.active_zone_id = "Z"
    state.place_entity("hero_wuk", CENTER)
    for i, m in enumerate(reds):
        state.place_entity(m.id, FAR[i % len(FAR)])
    for i, m in enumerate(blues):
        state.place_entity(m.id, NEIGHBORS[i])

    for idx, cap in enumerate(caps):
        state.active_effects.append(
            ActiveEffect(
                id=f"excl_{idx}",
                source_id="hero_wuk",
                effect_type=EffectType.MINION_BATTLE_EXCLUSION,
                scope=EffectScope(shape=Shape.POINT, origin_id="hero_wuk"),
                max_value=cap,
                duration=DurationType.THIS_ROUND,
                created_at_turn=0,
                created_at_round=0,
                is_active=True,
            )
        )
    return state


def _battle(state: GameState) -> tuple[str | None, int]:
    steps = MinionBattleStep()._resolve_minion_battle(state)
    if not steps:
        return (None, 0)
    s = steps[0]
    return (s.losing_team, s.remaining_to_remove)


def test_single_effect_reduces_enemy_count() -> None:
    # red=2, blue=3 adjacent; Assert cap 2 -> blue effective 1 -> BLUE loses 1.
    loser, diff = _battle(_build(red_minions=2, blue_adjacent=3, caps=[2]))
    assert (loser, diff) == ("BLUE", 1)


def test_stacked_caps_sum_but_minions_dedup() -> None:
    # red=1, blue=2 adjacent; Claim(1)+Assert(2)=3 capped by 2 distinct -> blue 0.
    loser, diff = _battle(_build(red_minions=1, blue_adjacent=2, caps=[1, 2]))
    assert (loser, diff) == ("BLUE", 1)


def test_summed_caps_not_max() -> None:
    # red=2, blue=5 adjacent; Claim(1)+Assert(2)=3 -> blue 2 -> tie (no removal).
    # 'max' would give 2 -> blue 3 -> RED loses; this distinguishes sum from max.
    loser, diff = _battle(_build(red_minions=2, blue_adjacent=5, caps=[1, 2]))
    assert (loser, diff) == (None, 0)


def test_immune_heavy_minion_still_excluded() -> None:
    # red=1, blue=1 adjacent heavy; cap 1 -> blue 0 -> BLUE loses 1.
    loser, diff = _battle(_build(red_minions=1, blue_adjacent=1, blue_heavy_adjacent=1, caps=[1]))
    assert (loser, diff) == ("BLUE", 1)

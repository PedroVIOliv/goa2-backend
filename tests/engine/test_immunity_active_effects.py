"""Regression tests for active effects respecting unit immunity."""

from __future__ import annotations

from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import ActionType, Card, CardColor, CardTier, Hero, Team, TeamColor
from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import DisplacementType, StatType
from goa2.domain.state import GameState
from goa2.domain.tile import Tile
from goa2.domain.types import UnitID
from goa2.engine.effect_manager import EffectManager
from goa2.engine.filters import RangeFilter
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.stats import get_computed_stat
from goa2.engine.steps import ResolvePreActionDiscardStep

HERO_TEAMS = {
    "hero_source": TeamColor.RED,
    "hero_actor": TeamColor.RED,
    "hero_target": TeamColor.RED,
    "hero_enemy": TeamColor.BLUE,
    "hero_enemy_2": TeamColor.BLUE,
}


def _hex(coords: tuple[int, int, int]) -> Hex:
    return Hex(q=coords[0], r=coords[1], s=coords[2])


def _state(
    positions: dict[str, tuple[int, int, int]],
    *,
    current_actor: str = "hero_source",
) -> GameState:
    board = Board()
    for q in range(-4, 5):
        for r in range(-4, 5):
            s = -q - r
            if abs(s) <= 4:
                h = Hex(q=q, r=r, s=s)
                board.tiles[h] = Tile(hex=h)

    heroes_by_team = {TeamColor.RED: [], TeamColor.BLUE: []}
    for hero_id, team in HERO_TEAMS.items():
        heroes_by_team[team].append(Hero(id=hero_id, name=hero_id, team=team, deck=[]))

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=heroes_by_team[TeamColor.RED]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=heroes_by_team[TeamColor.BLUE]),
        },
        turn=1,
        round=1,
        current_actor_id=current_actor,
    )
    for hero_id, coords in positions.items():
        state.place_entity(hero_id, _hex(coords))
    return state


def _create_effect(
    state: GameState,
    *,
    source_id: str = "hero_source",
    effect_type: EffectType,
    scope: EffectScope | None = None,
    **kwargs,
):
    duration = kwargs.pop("duration", DurationType.THIS_TURN)
    is_active = kwargs.pop("is_active", True)
    return EffectManager.create_effect(
        state=state,
        source_id=source_id,
        effect_type=effect_type,
        scope=scope
        or EffectScope(
            shape=Shape.RADIUS,
            range=3,
            origin_id=source_id,
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        duration=duration,
        is_active=is_active,
        **kwargs,
    )


def _add_full_immunity(state: GameState, hero_id: str) -> None:
    _create_effect(
        state,
        source_id=hero_id,
        effect_type=EffectType.IMMUNITY_ENEMY_ACTIONS,
        scope=EffectScope(shape=Shape.POINT, origin_id=hero_id, affects=AffectsFilter.SELF),
        duration=DurationType.THIS_ROUND,
    )


def _discard_card() -> Card:
    return Card(
        id="discard_me",
        name="Discard Me",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=1,
        primary_action=ActionType.ATTACK,
        secondary_actions={},
        is_ranged=False,
        range_value=0,
        primary_action_value=1,
        effect_id="filler",
        effect_text="",
    )


def test_target_prevention_ignores_immune_actor() -> None:
    state = _state({"hero_source": (0, 0, 0), "hero_enemy": (1, 0, -1)})
    _create_effect(
        state,
        effect_type=EffectType.TARGET_PREVENTION,
        restrictions=[ActionType.SKILL],
    )

    blocked = state.validator.can_perform_action(state, "hero_enemy", ActionType.SKILL)
    assert blocked.allowed is False

    _add_full_immunity(state, "hero_enemy")

    allowed = state.validator.can_perform_action(state, "hero_enemy", ActionType.SKILL)
    assert allowed.allowed is True


def test_movement_zone_ignores_immune_unit_for_cap() -> None:
    state = _state({"hero_source": (0, 0, 0), "hero_enemy": (1, 0, -1)})
    _create_effect(state, effect_type=EffectType.MOVEMENT_ZONE, max_value=1)

    blocked = state.validator.can_move(state, "hero_enemy", distance=2, is_movement_action=True)
    assert blocked.allowed is False

    _add_full_immunity(state, "hero_enemy")

    allowed = state.validator.can_move(state, "hero_enemy", distance=2, is_movement_action=True)
    assert allowed.allowed is True


def test_area_stat_modifier_ignores_immune_units_but_not_self() -> None:
    state = _state({"hero_source": (0, 0, 0), "hero_enemy": (1, 0, -1)})
    _create_effect(
        state,
        effect_type=EffectType.AREA_STAT_MODIFIER,
        stat_type=StatType.ATTACK,
        stat_value=-2,
    )
    assert get_computed_stat(state, UnitID("hero_enemy"), StatType.ATTACK, 5) == 3

    _add_full_immunity(state, "hero_enemy")
    assert get_computed_stat(state, UnitID("hero_enemy"), StatType.ATTACK, 5) == 5

    self_state = _state({"hero_source": (0, 0, 0)})
    _add_full_immunity(self_state, "hero_source")
    _create_effect(
        self_state,
        effect_type=EffectType.AREA_STAT_MODIFIER,
        scope=EffectScope(shape=Shape.POINT, origin_id="hero_source", affects=AffectsFilter.SELF),
        stat_type=StatType.ATTACK,
        stat_value=2,
    )
    assert get_computed_stat(self_state, UnitID("hero_source"), StatType.ATTACK, 5) == 7


def test_repeat_prevention_ignores_immune_actor() -> None:
    state = _state({"hero_source": (0, 0, 0), "hero_enemy": (1, 0, -1)})
    _create_effect(state, effect_type=EffectType.REPEAT_PREVENTION)

    blocked = state.validator.can_repeat_action(state, "hero_enemy")
    assert blocked.allowed is False

    _add_full_immunity(state, "hero_enemy")

    allowed = state.validator.can_repeat_action(state, "hero_enemy")
    assert allowed.allowed is True


def test_placement_prevention_ignores_immune_displaced_unit() -> None:
    state = _state({"hero_source": (0, 0, 0), "hero_enemy": (1, 0, -1)})
    _create_effect(
        state,
        effect_type=EffectType.PLACEMENT_PREVENTION,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=3,
            origin_id="hero_source",
            affects=AffectsFilter.ENEMY_UNITS,
        ),
        displacement_blocks=[DisplacementType.PLACE],
    )

    blocked = state.validator.can_be_placed(state, "hero_enemy", "hero_enemy")
    assert blocked.allowed is False

    _add_full_immunity(state, "hero_enemy")

    allowed = state.validator.can_be_placed(state, "hero_enemy", "hero_enemy")
    assert allowed.allowed is True


def test_los_blocker_ignores_immune_actor() -> None:
    state = _state(
        {
            "hero_source": (0, 1, -1),
            "hero_enemy": (0, 0, 0),
            "hero_target": (2, -2, 0),
        },
        current_actor="hero_enemy",
    )
    _create_effect(
        state,
        effect_type=EffectType.LOS_BLOCKER,
        scope=EffectScope(shape=Shape.POINT, origin_hex=Hex(q=1, r=-1, s=0)),
    )

    blocked = state.validator.can_be_targeted(state, "hero_enemy", "hero_target")
    assert blocked.allowed is False

    _add_full_immunity(state, "hero_enemy")

    allowed = state.validator.can_be_targeted(state, "hero_enemy", "hero_target")
    assert allowed.allowed is True


def test_static_barrier_ignores_immune_actor() -> None:
    state = _state({"hero_source": (0, 0, 0), "hero_enemy": (2, 0, -2)})
    _create_effect(
        state,
        effect_type=EffectType.STATIC_BARRIER,
        scope=EffectScope(shape=Shape.GLOBAL, origin_id="hero_source"),
        barrier_radius=1,
        barrier_origin_id="hero_source",
    )
    inside_hex = Hex(q=1, r=0, s=-1)

    assert state.validator.is_obstacle_for_actor(state, inside_hex, "hero_enemy") is True

    _add_full_immunity(state, "hero_enemy")

    assert state.validator.is_obstacle_for_actor(state, inside_hex, "hero_enemy") is False


def test_petrify_ignores_immune_unit_for_terrain_and_action_prevention() -> None:
    state = _state(
        {"hero_source": (0, 0, 0), "hero_enemy": (1, 0, -1)},
        current_actor="hero_enemy",
    )
    enemy_hex = Hex(q=1, r=0, s=-1)
    _create_effect(
        state,
        effect_type=EffectType.PETRIFY,
        restrictions=[ActionType.MOVEMENT, ActionType.FAST_TRAVEL],
    )

    assert state.validator.is_terrain_hex(state, enemy_hex) is True
    assert (
        state.validator.can_perform_action(state, "hero_enemy", ActionType.MOVEMENT).allowed
        is False
    )

    _add_full_immunity(state, "hero_enemy")

    assert state.validator.is_terrain_hex(state, enemy_hex) is False
    assert (
        state.validator.can_perform_action(state, "hero_enemy", ActionType.MOVEMENT).allowed is True
    )


def test_pre_action_discard_ignores_immune_hero() -> None:
    state = _state(
        {"hero_source": (0, 0, 0), "hero_enemy": (1, 0, -1)},
        current_actor="hero_enemy",
    )
    enemy = state.get_hero(UnitID("hero_enemy"))
    assert enemy is not None
    enemy.hand = [_discard_card()]
    _create_effect(state, effect_type=EffectType.PRE_ACTION_DISCARD)
    _add_full_immunity(state, "hero_enemy")

    push_steps(state, [ResolvePreActionDiscardStep(hero_id="hero_enemy")])
    result = process_stack(state)

    assert result.input_request is None
    assert enemy.hand


def test_topology_split_ignored_for_immune_unit_in_range_filter() -> None:
    state = _state(
        {
            "hero_source": (0, 0, 0),
            "hero_actor": (1, 0, -1),
            "hero_enemy": (-1, 0, 1),
        },
        current_actor="hero_actor",
    )
    _create_effect(
        state,
        effect_type=EffectType.TOPOLOGY_SPLIT,
        scope=EffectScope(shape=Shape.GLOBAL, origin_id="hero_source"),
        split_axis="q",
        split_value=0,
    )

    range_filter = RangeFilter(max_range=2)
    assert range_filter.apply("hero_enemy", state, {}) is False

    _add_full_immunity(state, "hero_enemy")

    assert range_filter.apply("hero_enemy", state, {}) is True

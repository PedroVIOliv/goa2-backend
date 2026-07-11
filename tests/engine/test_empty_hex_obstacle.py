"""P4: EMPTY_HEX_OBSTACLE — empty hexes near the source deny enemy units."""

from goa2.domain.hex import Hex
from goa2.domain.models.effect import (
    ActiveEffect,
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.state import GameState
from tests.engine.effects.builders import EffectScenarioBuilder


def _denial_state(radius: int = 1) -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes(
            [
                (q, r, -q - r)
                for q in range(-3, 5)
                for r in range(-2, 3)
                if -3 <= -q - r <= 4  # a comfortable slab around the origin
            ]
        )
        .red_hero("hero_takahide", at=(0, 0, 0))
        .red_hero("hero_ally_1", at=(0, 2, -2))
        .blue_hero("hero_enemy_1", at=(3, 0, -3))
        .blue_minion("minion_e1", at=(3, -1, -2))
        .with_actor("hero_enemy_1")
        .build()
    )
    state.active_effects.append(
        ActiveEffect(
            id="fx_denial",
            source_id="hero_takahide",
            source_card_id="spinning_blade",
            effect_type=EffectType.EMPTY_HEX_OBSTACLE,
            scope=EffectScope(
                shape=Shape.RADIUS,
                range=radius,
                origin_id="hero_takahide",
                affects=AffectsFilter.ENEMY_UNITS,
            ),
            duration=DurationType.THIS_TURN,
            created_at_turn=state.turn,
            created_at_round=state.round,
            is_active=True,
        )
    )
    return state


ADJACENT = Hex(q=1, r=0, s=-1)


def test_empty_adjacent_hex_is_obstacle_for_enemy_hero():
    state = _denial_state()
    assert state.validator.is_obstacle_for_actor(state, ADJACENT, "hero_enemy_1")


def test_denied_hex_is_not_obstacle_for_friendly_unit():
    state = _denial_state()
    assert not state.validator.is_obstacle_for_actor(state, ADJACENT, "hero_ally_1")


def test_denied_hex_is_not_obstacle_for_the_source():
    state = _denial_state()
    assert not state.validator.is_obstacle_for_actor(state, ADJACENT, "hero_takahide")


def test_enemy_minion_actor_is_blocked_too():
    state = _denial_state()
    assert state.validator.is_obstacle_for_actor(state, ADJACENT, "minion_e1")


def test_hex_outside_radius_is_free():
    state = _denial_state()
    assert not state.validator.is_obstacle_for_actor(state, Hex(q=2, r=0, s=-2), "hero_enemy_1")


def test_radius_two_denies_distance_two_hexes():
    state = _denial_state(radius=2)
    assert state.validator.is_obstacle_for_actor(state, Hex(q=2, r=0, s=-2), "hero_enemy_1")


def test_inactive_effect_does_nothing():
    state = _denial_state()
    state.active_effects[-1].is_active = False
    assert not state.validator.is_obstacle_for_actor(state, ADJACENT, "hero_enemy_1")


def test_occupied_hex_is_unaffected_by_the_effect():
    """An occupied hex is already an obstacle; nothing changes for allies either."""
    state = _denial_state(radius=3)
    ally_hex = state.get_position("hero_ally_1")
    assert ally_hex is not None
    assert state.validator.is_obstacle_for_actor(state, ally_hex, "hero_enemy_1")
    assert state.validator.is_obstacle_for_actor(state, ally_hex, "hero_takahide")


def test_dynamic_origin_follows_source_position():
    state = _denial_state()
    state.place_entity("hero_takahide", Hex(q=-2, r=0, s=2))
    assert not state.validator.is_obstacle_for_actor(state, ADJACENT, "hero_enemy_1")
    assert state.validator.is_obstacle_for_actor(state, Hex(q=-1, r=0, s=1), "hero_enemy_1")

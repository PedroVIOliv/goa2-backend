"""Fix 5 guards: persistent positional effects created by a multi-piece hero
anchor to the acting piece, not the owner hero ID (which has no position)."""

from goa2.domain.hex import Hex
from goa2.domain.models.effect import (
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import StatType
from goa2.domain.state import GameState
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.stats import is_unit_in_effect_scope
from goa2.engine.steps.effects import CreateEffectStep
from tests.engine.effects.builders import EffectScenarioBuilder


def _state() -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(5)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(3, 0, -3))
        .with_actor("hero_razzle")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=2, r=0, s=-2))
    return state


def test_persistent_effect_from_razzle_anchors_to_acting_piece():
    state = _state()
    state.acting_piece_id = piece_id("hero_razzle", 2)

    push_steps(
        state,
        [
            CreateEffectStep(
                effect_type=EffectType.AREA_STAT_MODIFIER,
                scope=EffectScope(shape=Shape.RADIUS, range=1, affects=AffectsFilter.ENEMY_HEROES),
                stat_type=StatType.DEFENSE,
                stat_value=-1,
                duration=DurationType.THIS_ROUND,
                use_context_card=False,
            )
        ],
    )
    process_stack(state)

    effect = state.active_effects[-1]
    assert effect.scope.origin_id == piece_id("hero_razzle", 2)

    # Razzle's turn ends: binding cleared, another hero acts. The effect must
    # stay anchored at the piece that created it.
    state.acting_piece_id = None
    state.current_actor_id = "hero_knight"
    # knight at (3,0,-3) is adjacent to piece_2 at (2,0,-2) → in scope
    assert is_unit_in_effect_scope(effect, "hero_knight", state) is True

    # Even after Razzle later acts with the other piece, the anchor is stable.
    state.acting_piece_id = piece_id("hero_razzle", 1)
    state.current_actor_id = "hero_razzle"
    assert is_unit_in_effect_scope(effect, "hero_knight", state) is True


def test_static_barrier_from_razzle_binds_piece_origin():
    state = _state()
    state.acting_piece_id = piece_id("hero_razzle", 1)

    push_steps(
        state,
        [
            CreateEffectStep(
                effect_type=EffectType.STATIC_BARRIER,
                scope=EffectScope(shape=Shape.GLOBAL),
                barrier_radius=1,
                duration=DurationType.THIS_ROUND,
                use_context_card=False,
            )
        ],
    )
    process_stack(state)

    effect = state.active_effects[-1]
    assert effect.barrier_origin_id == piece_id("hero_razzle", 1)

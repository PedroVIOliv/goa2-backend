"""Pieces behave as independent enemy hero units for targeting and stats."""

from goa2.domain.hex import Hex
from goa2.domain.models import StatType
from goa2.domain.models.effect import (
    ActiveEffect,
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.models.enums import TargetType
from goa2.domain.state import GameState
from goa2.engine.filters_hex import RangeFilter
from goa2.engine.filters_units import TeamFilter
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.stats import get_computed_stat, is_unit_in_effect_scope
from goa2.engine.steps.selection import SelectStep
from tests.engine.effects.builders import EffectScenarioBuilder


def _state(actor: str = "hero_knight") -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(0, 0, 0), (1, 0, -1), (2, 0, -2), (3, 0, -3), (0, 1, -1)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(2, 0, -2))
        .with_actor(actor)
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=1, r=0, s=-1))
    return state


def test_enemy_select_step_offers_pieces():
    state = _state()
    push_steps(
        state,
        [
            SelectStep(
                target_type=TargetType.UNIT,
                prompt="Select Attack Target",
                output_key="victim_id",
                filters=[RangeFilter(max_range=1), TeamFilter(relation="ENEMY")],
            )
        ],
    )
    result = process_stack(state)
    assert result.input_request is not None
    option_ids = {o.id for o in result.input_request.options}
    # knight at (2,0,-2): piece_2 at (1,0,-1) is adjacent, piece_1 is not
    assert piece_id("hero_razzle", 2) in option_ids
    assert piece_id("hero_razzle", 1) not in option_ids
    assert "hero_razzle" not in option_ids


def test_range_filter_origin_resolves_acting_piece():
    state = _state(actor="hero_razzle")
    state.acting_piece_id = piece_id("hero_razzle", 2)
    # knight at (2,0,-2) is adjacent to piece_2 at (1,0,-1)
    f = RangeFilter(max_range=1)
    assert f.apply("hero_knight", state, {}) is True
    state.acting_piece_id = piece_id("hero_razzle", 1)
    assert f.apply("hero_knight", state, {}) is False


def test_computed_stat_applies_owner_items_to_piece():
    state = _state()
    razzle = state.get_hero("hero_razzle")
    razzle.items[StatType.DEFENSE] = 2
    total = get_computed_stat(state, piece_id("hero_razzle", 2), StatType.DEFENSE, 1)
    assert total == 3


def test_area_modifier_hits_piece_in_scope_only():
    state = _state()
    effect = ActiveEffect(
        id="area_test",
        source_id="hero_knight",
        effect_type=EffectType.AREA_STAT_MODIFIER,
        scope=EffectScope(shape=Shape.RADIUS, range=1, affects=AffectsFilter.ENEMY_HEROES),
        stat_type=StatType.DEFENSE,
        stat_value=-1,
        duration=DurationType.THIS_ROUND,
        created_at_round=state.round,
        created_at_turn=state.turn,
        is_active=True,
    )
    state.add_effect(effect)
    # piece_2 adjacent to knight → in scope; piece_1 two away → out of scope
    assert is_unit_in_effect_scope(effect, piece_id("hero_razzle", 2), state) is True
    assert is_unit_in_effect_scope(effect, piece_id("hero_razzle", 1), state) is False
    assert get_computed_stat(state, piece_id("hero_razzle", 2), StatType.DEFENSE, 1) == 0
    assert get_computed_stat(state, piece_id("hero_razzle", 1), StatType.DEFENSE, 1) == 1

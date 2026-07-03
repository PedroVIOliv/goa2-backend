"""Fix 1 guards: board-level hero checks treat HeroPiece as a hero unit."""

from goa2.data.heroes.brynn import create_brynn
from goa2.domain.hex import Hex
from goa2.domain.models import TeamColor
from goa2.domain.models.effect import (
    ActiveEffect,
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.state import GameState
from goa2.engine.filters_hex import AdjacentToObstaclesFilter
from goa2.engine.filters_units import AdjacencyFilter, TeamFilter
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
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


def test_validator_affects_enemy_heroes_matches_piece():
    state = _state()
    effect = ActiveEffect(
        id="affects_test",
        source_id="hero_knight",
        effect_type=EffectType.AREA_STAT_MODIFIER,
        scope=EffectScope(shape=Shape.GLOBAL, affects=AffectsFilter.ENEMY_HEROES),
        duration=DurationType.THIS_ROUND,
        created_at_round=state.round,
        created_at_turn=state.turn,
        is_active=True,
    )
    validator = state.validator
    assert validator._matches_affects_filter(effect, piece_id("hero_razzle", 2), state) is True
    # ALL_HEROES must also see the piece
    effect.scope.affects = AffectsFilter.ALL_HEROES
    assert validator._matches_affects_filter(effect, piece_id("hero_razzle", 2), state) is True


def test_static_barrier_applies_to_acting_piece():
    state = _state()
    effect = ActiveEffect(
        id="barrier_test",
        source_id="hero_knight",
        effect_type=EffectType.STATIC_BARRIER,
        scope=EffectScope(shape=Shape.GLOBAL),
        barrier_radius=1,
        duration=DurationType.THIS_ROUND,
        created_at_round=state.round,
        created_at_turn=state.turn,
        is_active=True,
    )
    state.add_effect(effect)
    # Acting piece_1 at (0,0,0) is outside radius 1 of the knight, so the hex
    # (3,0,-3) inside the barrier must be an obstacle for it.
    assert (
        state.validator.is_obstacle_for_actor(
            state, Hex(q=3, r=0, s=-3), piece_id("hero_razzle", 1)
        )
        is True
    )


def test_adjacency_filter_hero_tag_counts_pieces():
    state = _state()
    # hex (0,1,-1) has only the two Razzle pieces as occupied neighbours
    assert AdjacencyFilter(target_tags=["HERO"]).apply(Hex(q=0, r=1, s=-1), state, {}) is True
    assert (
        AdjacencyFilter(target_tags=["ENEMY", "HERO"]).apply(Hex(q=0, r=1, s=-1), state, {}) is True
    )


def test_over_the_top_treats_enemy_piece_as_hero():
    state = _state()
    brynn = create_brynn()
    brynn.level = 8
    brynn.team = TeamColor.BLUE
    state.teams[TeamColor.BLUE].heroes.append(brynn)
    state.place_entity("hero_brynn", Hex(q=3, r=0, s=-3))
    state.current_actor_id = "hero_brynn"
    f = AdjacentToObstaclesFilter(min_count=3)
    assert f._over_the_top_applies(piece_id("hero_razzle", 2), state) is True


def test_friendly_filter_offers_other_piece_not_acting_piece():
    state = _state(actor="hero_razzle")
    state.acting_piece_id = piece_id("hero_razzle", 1)
    f = TeamFilter(relation="FRIENDLY")
    # During resolution the pieces are different heroes: "another friendly
    # hero" can select her own other piece...
    assert f.apply(piece_id("hero_razzle", 2), state, {}) is True
    # ...but never the acting piece itself (that is "you").
    assert f.apply(piece_id("hero_razzle", 1), state, {}) is False

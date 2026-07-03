"""Effect identity is player-level: SELF-scoped effects from a multi-piece
hero apply to her pieces, and "other friendly heroes" scopes exclude them."""

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
from goa2.domain.state import GameState
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.stats import get_computed_stat
from tests.engine.effects.builders import EffectScenarioBuilder


def _state() -> GameState:
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(6)])
        .red_hero("hero_razzle", at=(0, 0, 0))
        .red_hero("hero_ally", at=(5, 0, -5))
        .blue_hero("hero_knight", at=(4, 0, -4))
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


def _global_effect(affects: AffectsFilter, stat: StatType, value: int, state: GameState):
    return ActiveEffect(
        id=f"eff_{affects.value}",
        source_id="hero_razzle",
        effect_type=EffectType.AREA_STAT_MODIFIER,
        scope=EffectScope(shape=Shape.GLOBAL, affects=affects),
        stat_type=stat,
        stat_value=value,
        duration=DurationType.THIS_ROUND,
        created_at_round=state.round,
        created_at_turn=state.turn,
        is_active=True,
    )


def test_self_scoped_effect_from_razzle_applies_to_her_pieces():
    state = _state()
    state.add_effect(_global_effect(AffectsFilter.SELF, StatType.ATTACK, 2, state))

    assert get_computed_stat(state, piece_id("hero_razzle", 1), StatType.ATTACK, 1) == 3
    assert get_computed_stat(state, piece_id("hero_razzle", 2), StatType.ATTACK, 1) == 3
    # Nobody else is "self".
    assert get_computed_stat(state, "hero_ally", StatType.ATTACK, 1) == 1
    assert get_computed_stat(state, "hero_knight", StatType.ATTACK, 1) == 1


def test_friendly_heroes_scope_excludes_own_pieces():
    state = _state()
    state.add_effect(_global_effect(AffectsFilter.FRIENDLY_HEROES, StatType.DEFENSE, 1, state))

    # "Other friendly heroes" reaches the ally...
    assert get_computed_stat(state, "hero_ally", StatType.DEFENSE, 1) == 2
    # ...but Razzle's own pieces are "you", not other heroes.
    assert get_computed_stat(state, piece_id("hero_razzle", 1), StatType.DEFENSE, 1) == 1
    assert get_computed_stat(state, piece_id("hero_razzle", 2), StatType.DEFENSE, 1) == 1


def test_validator_self_scope_matches_piece():
    state = _state()
    effect = _global_effect(AffectsFilter.SELF, StatType.ATTACK, 2, state)
    assert (
        state.validator._matches_affects_filter(effect, piece_id("hero_razzle", 2), state) is True
    )
    assert state.validator._matches_affects_filter(effect, "hero_ally", state) is False


def test_blocks_self_restriction_blocks_own_piece_actor():
    state = _state()
    effect = ActiveEffect(
        id="restrict_self",
        source_id="hero_razzle",
        effect_type=EffectType.TARGET_PREVENTION,
        scope=EffectScope(shape=Shape.GLOBAL),
        duration=DurationType.THIS_ROUND,
        created_at_round=state.round,
        created_at_turn=state.turn,
        is_active=True,
        blocks_self=True,
        blocks_enemy_actors=False,
    )
    piece = state.get_unit(piece_id("hero_razzle", 1))
    knight = state.get_unit("hero_knight")
    assert state.validator._actor_blocked_by_effect(effect, piece, None, state) is True
    assert state.validator._actor_blocked_by_effect(effect, knight, None, state) is False

"""Fix 3 guards: acting-piece stats are authoritative; initiative aggregates
across all pieces, counting each distinct positional effect once."""

from goa2.domain.hex import Hex
from goa2.domain.models import ActionType, Card, CardColor, CardTier, StatType
from goa2.domain.models.effect import (
    ActiveEffect,
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.state import GameState
from goa2.engine.effects import CardEffect
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.stats import get_computed_stat
from tests.engine.effects.builders import EffectScenarioBuilder


def _state(actor: str = "hero_razzle") -> GameState:
    """Line board; pieces at (0,0,0) and (2,0,-2), knight at (4,0,-4)."""
    hexes = [(q, 0, -q) for q in range(5)] + [(0, 1, -1), (1, 1, -2)]
    state = (
        EffectScenarioBuilder()
        .with_hexes(hexes)
        .red_hero("hero_razzle", at=(0, 0, 0))
        .blue_hero("hero_knight", at=(4, 0, -4))
        .with_actor(actor)
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=2, r=0, s=-2))
    return state


def _area_effect(
    effect_id: str,
    origin: tuple[int, int, int],
    stat_type: StatType,
    value: int,
    state: GameState,
) -> ActiveEffect:
    q, r, s = origin
    return ActiveEffect(
        id=effect_id,
        source_id="hero_knight",
        effect_type=EffectType.AREA_STAT_MODIFIER,
        scope=EffectScope(
            shape=Shape.RADIUS,
            range=1,
            origin_hex=Hex(q=q, r=r, s=s),
            affects=AffectsFilter.ENEMY_HEROES,
        ),
        stat_type=stat_type,
        stat_value=value,
        duration=DurationType.THIS_ROUND,
        created_at_round=state.round,
        created_at_turn=state.turn,
        is_active=True,
    )


def test_acting_piece_stats_are_authoritative():
    state = _state()
    # Debuff zone touches only piece_2 at (2,0,-2)
    state.add_effect(_area_effect("near_p2", (2, 0, -2), StatType.ATTACK, -1, state))

    state.acting_piece_id = piece_id("hero_razzle", 1)
    assert get_computed_stat(state, "hero_razzle", StatType.ATTACK, 3) == 3

    state.acting_piece_id = piece_id("hero_razzle", 2)
    assert get_computed_stat(state, "hero_razzle", StatType.ATTACK, 3) == 2


def test_initiative_counts_single_effect_once_when_touching_two_pieces():
    state = _state()
    # Pieces moved adjacent so one radius-1 zone at (1,0,-1) covers both.
    state.move_unit(piece_id("hero_razzle", 2), Hex(q=1, r=0, s=-1))
    state.add_effect(_area_effect("shared", (1, 0, -1), StatType.INITIATIVE, -1, state))

    assert get_computed_stat(state, "hero_razzle", StatType.INITIATIVE, 5) == 4


def test_initiative_sums_distinct_effects_on_different_pieces():
    state = _state()
    state.add_effect(_area_effect("near_p1", (0, 0, 0), StatType.INITIATIVE, -1, state))
    state.add_effect(_area_effect("near_p2", (2, 0, -2), StatType.INITIATIVE, -1, state))

    assert get_computed_stat(state, "hero_razzle", StatType.INITIATIVE, 5) == 3


def test_initiative_aggregates_even_with_acting_piece_bound():
    state = _state()
    state.add_effect(_area_effect("near_p2", (2, 0, -2), StatType.INITIATIVE, -1, state))
    state.acting_piece_id = piece_id("hero_razzle", 1)

    assert get_computed_stat(state, "hero_razzle", StatType.INITIATIVE, 5) == 4


class _CaptureDefense(CardEffect):
    def __init__(self) -> None:
        self.captured = []

    def build_defense_steps(self, state, hero, card, stats, context):
        self.captured.append(stats)
        return []


def _defense_card() -> Card:
    return Card(
        id="test_defense",
        name="Test Defense",
        tier=CardTier.I,
        color=CardColor.BLUE,
        initiative=9,
        primary_action=ActionType.DEFENSE,
        primary_action_value=2,
        secondary_actions={},
        is_ranged=False,
        effect_id="test_defense",
        effect_text="",
        is_facedown=False,
    )


def test_defense_stats_use_attacked_piece_from_context():
    state = _state(actor="hero_knight")
    razzle = state.get_hero("hero_razzle")
    # Defense buff zone touches only piece_2
    state.add_effect(_area_effect("near_p2", (2, 0, -2), StatType.DEFENSE, 1, state))

    effect = _CaptureDefense()
    effect.get_defense_steps(
        state, razzle, _defense_card(), {"defender_id": piece_id("hero_razzle", 2)}
    )
    effect.get_defense_steps(
        state, razzle, _defense_card(), {"defender_id": piece_id("hero_razzle", 1)}
    )

    assert effect.captured[0].primary_value == 3  # buffed: attacked piece in zone
    assert effect.captured[1].primary_value == 2  # unbuffed: attacked piece outside

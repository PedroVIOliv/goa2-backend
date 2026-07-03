"""Fix 3 guards: acting-piece stats are authoritative; initiative aggregates
across all pieces, counting each distinct positional effect once."""

from goa2.domain.hex import Hex
from goa2.domain.input import InputRequestType
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardTier,
    Minion,
    MinionType,
    StatType,
    TeamColor,
)
from goa2.domain.models.effect import (
    ActiveEffect,
    AffectsFilter,
    DurationType,
    EffectScope,
    EffectType,
    Shape,
)
from goa2.domain.state import GameState
from goa2.engine.effects import CardEffect, CardEffectRegistry, StatAura
from goa2.engine.filters_hex import RangeFilter
from goa2.engine.filters_units import TeamFilter
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.hero_pieces import create_hero_pieces, piece_id
from goa2.engine.stats import get_computed_stat
from goa2.engine.steps.cards import ResolveCardStep
from tests.engine.effects.builders import EffectScenarioBuilder, skill_card


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


def _card_with_secondary_movement() -> Card:
    return Card(
        id="test_secondary_move",
        name="Test Secondary Move",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=1,
        secondary_actions={ActionType.MOVEMENT: 3},
        is_ranged=False,
        range_value=1,
        effect_id="test_secondary_move",
        effect_text="",
        is_facedown=False,
    )


def _card_with_secondary_attack() -> Card:
    return Card(
        id="test_secondary_attack",
        name="Test Secondary Attack",
        tier=CardTier.I,
        color=CardColor.GREEN,
        initiative=5,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=1,
        secondary_actions={ActionType.ATTACK: 3},
        is_ranged=False,
        effect_id="test_secondary_attack",
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


def test_secondary_movement_recomputes_after_acting_piece_choice():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(8)])
        .red_hero("hero_razzle", at=(0, 0, 0), current_card=_card_with_secondary_movement())
        .blue_hero("hero_knight", at=(7, 0, -7))
        .with_actor("hero_razzle")
        .build()
    )
    razzle = state.get_hero("hero_razzle")
    razzle.piece_supply = 4
    state.remove_entity("hero_razzle")
    create_hero_pieces(state, razzle)
    state.place_entity(piece_id("hero_razzle", 1), Hex(q=0, r=0, s=0))
    state.place_entity(piece_id("hero_razzle", 2), Hex(q=2, r=0, s=-2))
    state.add_effect(_area_effect("near_p1", (0, 0, 0), StatType.MOVEMENT, 2, state))

    push_steps(state, [ResolveCardStep(hero_id="hero_razzle")])
    result = process_stack(state)
    assert result.input_request.request_type == InputRequestType.CHOOSE_ACTION
    state.execution_stack[-1].pending_input = {"selection": "MOVEMENT"}

    result = process_stack(state)
    assert result.input_request.request_type == InputRequestType.SELECT_UNIT
    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 2)}

    result = process_stack(state)
    assert result.input_request.request_type == InputRequestType.SELECT_HEX
    offered = {option.metadata["raw"] for option in result.input_request.options}
    assert Hex(q=5, r=0, s=-5) in offered
    assert Hex(q=6, r=0, s=-6) not in offered


def test_secondary_attack_damage_recomputes_after_acting_piece_choice():
    state = (
        EffectScenarioBuilder()
        .with_hexes([(q, 0, -q) for q in range(5)])
        .red_hero("hero_razzle", at=(0, 0, 0), current_card=_card_with_secondary_attack())
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
    state.add_effect(_area_effect("near_p1", (0, 0, 0), StatType.ATTACK, 2, state))

    push_steps(state, [ResolveCardStep(hero_id="hero_razzle")])
    result = process_stack(state)
    assert result.input_request.request_type == InputRequestType.CHOOSE_ACTION
    state.execution_stack[-1].pending_input = {"selection": "ATTACK"}

    result = process_stack(state)
    assert result.input_request.request_type == InputRequestType.SELECT_UNIT
    state.execution_stack[-1].pending_input = {"selection": piece_id("hero_razzle", 2)}

    result = process_stack(state)
    assert result.input_request.request_type == InputRequestType.SELECT_UNIT
    assert state.execution_context["attack_damage"] == 3


class _CountInitiativeAura(CardEffect):
    def get_stat_auras(self):
        return [
            StatAura(
                stat_type=StatType.INITIATIVE,
                count_filters=[TeamFilter(relation="ENEMY"), RangeFilter(max_range=1)],
                multiplier=1,
            )
        ]


def test_count_based_initiative_aura_counts_from_multipiece_owner():
    state = _state()
    razzle = state.get_hero("hero_razzle")
    razzle.level = 8
    razzle.ultimate_card = skill_card(
        "test_count_aura", effect_id="test_multipiece_count_initiative"
    )
    CardEffectRegistry.register("test_multipiece_count_initiative", _CountInitiativeAura())
    shared_enemy = Minion(
        id="shared_enemy", name="Shared Enemy", team=TeamColor.BLUE, type=MinionType.MELEE
    )
    p2_enemy = Minion(id="p2_enemy", name="P2 Enemy", team=TeamColor.BLUE, type=MinionType.MELEE)
    state.teams[TeamColor.BLUE].minions.extend([shared_enemy, p2_enemy])
    state.place_entity("shared_enemy", Hex(q=1, r=0, s=-1))
    state.place_entity("p2_enemy", Hex(q=3, r=0, s=-3))

    assert get_computed_stat(state, "hero_razzle", StatType.INITIATIVE, 0) == 2

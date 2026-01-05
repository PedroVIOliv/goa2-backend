"""Tests for ActiveEffect model and related enums."""
import pytest
from goa2.domain.models.effect import (
    EffectType,
    AffectsFilter,
    Shape,
    EffectScope,
    ActiveEffect,
)
from goa2.domain.models.modifier import DurationType
from goa2.domain.hex import Hex


class TestEffectType:
    """Tests for EffectType enum."""

    def test_effect_type_placement_prevention(self):
        assert EffectType.PLACEMENT_PREVENTION == "placement_prevention"

    def test_effect_type_movement_zone(self):
        assert EffectType.MOVEMENT_ZONE == "movement_zone"

    def test_effect_type_target_prevention(self):
        assert EffectType.TARGET_PREVENTION == "target_prevention"

    def test_effect_type_area_stat_modifier(self):
        assert EffectType.AREA_STAT_MODIFIER == "area_stat_modifier"


class TestAffectsFilter:
    """Tests for AffectsFilter enum."""

    def test_affects_filter_self(self):
        assert AffectsFilter.SELF == "self"

    def test_affects_filter_enemy_units(self):
        assert AffectsFilter.ENEMY_UNITS == "enemy_units"

    def test_affects_filter_friendly_units(self):
        assert AffectsFilter.FRIENDLY_UNITS == "friendly_units"

    def test_affects_filter_all_units(self):
        assert AffectsFilter.ALL_UNITS == "all_units"

    def test_affects_filter_enemy_heroes(self):
        assert AffectsFilter.ENEMY_HEROES == "enemy_heroes"


class TestShape:
    """Tests for Shape enum."""

    def test_shape_point(self):
        assert Shape.POINT == "point"

    def test_shape_radius(self):
        assert Shape.RADIUS == "radius"

    def test_shape_adjacent(self):
        assert Shape.ADJACENT == "adjacent"

    def test_shape_zone(self):
        assert Shape.ZONE == "zone"

    def test_shape_global(self):
        assert Shape.GLOBAL == "global"


class TestEffectScope:
    """Tests for EffectScope model."""

    def test_effect_scope_basic(self):
        """EffectScope can be created with minimal fields."""
        scope = EffectScope(shape=Shape.RADIUS)
        assert scope.shape == Shape.RADIUS
        assert scope.range == 0
        assert scope.affects == AffectsFilter.ALL_UNITS

    def test_effect_scope_with_range(self):
        """EffectScope can specify a range."""
        scope = EffectScope(
            shape=Shape.RADIUS,
            range=3,
            origin_id="hero_1",
            affects=AffectsFilter.ENEMY_UNITS
        )
        assert scope.shape == Shape.RADIUS
        assert scope.range == 3
        assert scope.origin_id == "hero_1"
        assert scope.affects == AffectsFilter.ENEMY_UNITS

    def test_effect_scope_with_fixed_origin(self):
        """EffectScope can use a fixed hex as origin."""
        origin = Hex(q=1, r=2, s=-3)
        scope = EffectScope(
            shape=Shape.RADIUS,
            range=2,
            origin_hex=origin
        )
        assert scope.origin_hex == origin
        assert scope.origin_id is None


class TestActiveEffect:
    """Tests for ActiveEffect model."""

    def test_active_effect_basic_creation(self):
        """ActiveEffect can be created with required fields."""
        effect = ActiveEffect(
            id="eff_1",
            source_id="hero_1",
            effect_type=EffectType.PLACEMENT_PREVENTION,
            scope=EffectScope(shape=Shape.RADIUS, range=3),
            duration=DurationType.THIS_TURN,
            created_at_turn=1,
            created_at_round=1
        )
        assert effect.id == "eff_1"
        assert effect.source_id == "hero_1"
        assert effect.effect_type == EffectType.PLACEMENT_PREVENTION
        assert effect.scope.shape == Shape.RADIUS
        assert effect.duration == DurationType.THIS_TURN

    def test_active_effect_with_source_card(self):
        """ActiveEffect can track which card created it."""
        effect = ActiveEffect(
            id="eff_1",
            source_id="hero_1",
            source_card_id="magnetic_dagger_1",
            effect_type=EffectType.PLACEMENT_PREVENTION,
            scope=EffectScope(shape=Shape.RADIUS, range=3),
            duration=DurationType.THIS_TURN,
            created_at_turn=1,
            created_at_round=1
        )
        assert effect.source_card_id == "magnetic_dagger_1"

    def test_active_effect_blocks_enemy_actors_default(self):
        """By default, effects block enemy actors."""
        effect = ActiveEffect(
            id="eff_1",
            source_id="hero_1",
            effect_type=EffectType.PLACEMENT_PREVENTION,
            scope=EffectScope(shape=Shape.GLOBAL),
            duration=DurationType.THIS_TURN,
            created_at_turn=1,
            created_at_round=1
        )
        assert effect.blocks_enemy_actors is True
        assert effect.blocks_friendly_actors is False
        assert effect.blocks_self is False

    def test_active_effect_movement_zone_with_max_value(self):
        """Movement zone effects can specify max movement value."""
        effect = ActiveEffect(
            id="eff_1",
            source_id="hero_1",
            effect_type=EffectType.MOVEMENT_ZONE,
            scope=EffectScope(shape=Shape.ADJACENT, affects=AffectsFilter.ENEMY_UNITS),
            duration=DurationType.THIS_TURN,
            created_at_turn=1,
            created_at_round=1,
            max_value=1  # Can only move 1 space
        )
        assert effect.max_value == 1

    def test_active_effect_source_card_id_optional(self):
        """source_card_id defaults to None."""
        effect = ActiveEffect(
            id="eff_1",
            source_id="hero_1",
            effect_type=EffectType.AREA_STAT_MODIFIER,
            scope=EffectScope(shape=Shape.ADJACENT),
            duration=DurationType.PASSIVE,
            created_at_turn=1,
            created_at_round=1
        )
        assert effect.source_card_id is None

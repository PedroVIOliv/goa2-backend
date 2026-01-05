"""Tests for Modifier and DurationType models."""
import pytest
from goa2.domain.models.modifier import DurationType, Modifier


class TestDurationType:
    """Tests for DurationType enum."""

    def test_duration_type_has_this_turn(self):
        assert DurationType.THIS_TURN == "THIS_TURN"

    def test_duration_type_has_this_round(self):
        assert DurationType.THIS_ROUND == "THIS_ROUND"

    def test_duration_type_has_passive(self):
        assert DurationType.PASSIVE == "PASSIVE"

    def test_duration_type_has_next_turn(self):
        """NEXT_TURN duration for effects that activate on the following turn."""
        assert DurationType.NEXT_TURN == "NEXT_TURN"


class TestModifier:
    """Tests for Modifier model."""

    def test_modifier_basic_creation(self):
        """Modifier can be created with required fields."""
        mod = Modifier(
            id="mod_1",
            source_id="hero_1",
            target_id="hero_2",
            status_tag="PREVENT_MOVEMENT",
            duration=DurationType.THIS_TURN,
            created_at_turn=1,
            created_at_round=1
        )
        assert mod.id == "mod_1"
        assert mod.source_id == "hero_1"
        assert mod.target_id == "hero_2"
        assert mod.status_tag == "PREVENT_MOVEMENT"

    def test_modifier_has_source_card_id(self):
        """Modifier can track which card created it."""
        mod = Modifier(
            id="mod_1",
            source_id="hero_1",
            source_card_id="card_123",
            target_id="hero_2",
            status_tag="PREVENT_MOVEMENT",
            duration=DurationType.THIS_TURN,
            created_at_turn=1,
            created_at_round=1
        )
        assert mod.source_card_id == "card_123"

    def test_modifier_source_card_id_optional(self):
        """source_card_id defaults to None for non-card effects."""
        mod = Modifier(
            id="mod_1",
            source_id="hero_1",
            target_id="hero_2",
            status_tag="BONUS",
            duration=DurationType.PASSIVE,
            created_at_turn=1,
            created_at_round=1
        )
        assert mod.source_card_id is None

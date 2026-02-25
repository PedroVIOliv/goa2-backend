"""Tests for Marker model and GameState marker integration."""

import pytest
from goa2.domain.models.marker import (
    Marker,
    MarkerType,
    MARKER_EFFECTS,
)
from goa2.domain.models.enums import StatType


class TestMarkerType:
    """Tests for MarkerType enum."""

    def test_marker_type_has_venom(self):
        assert MarkerType.VENOM == "venom"


class TestMarkerStatEffect:
    """Tests for MarkerStatEffect configuration."""

    def test_venom_marker_effects_defined(self):
        """VENOM marker should have effects for Attack, Defense, Initiative."""
        effects = MARKER_EFFECTS[MarkerType.VENOM]
        stat_types = [e.stat_type for e in effects]
        assert StatType.ATTACK in stat_types
        assert StatType.DEFENSE in stat_types
        assert StatType.INITIATIVE in stat_types

    def test_venom_effects_use_marker_value(self):
        """VENOM effects should use the marker's value field."""
        effects = MARKER_EFFECTS[MarkerType.VENOM]
        for effect in effects:
            assert effect.use_marker_value is True


class TestMarker:
    """Tests for Marker model."""

    def test_marker_creation(self):
        """Marker can be created with a type."""
        marker = Marker(type=MarkerType.VENOM)
        assert marker.type == MarkerType.VENOM
        assert marker.target_id is None
        assert marker.value == 0
        assert marker.source_id is None

    def test_marker_is_placed_false_when_no_target(self):
        """is_placed returns False when marker is in supply."""
        marker = Marker(type=MarkerType.VENOM)
        assert marker.is_placed is False

    def test_marker_is_placed_true_when_has_target(self):
        """is_placed returns True when marker is on a hero."""
        marker = Marker(type=MarkerType.VENOM, target_id="hero_1")
        assert marker.is_placed is True

    def test_marker_place(self):
        """place() sets target, value, and source."""
        marker = Marker(type=MarkerType.VENOM)
        marker.place(target_id="hero_2", value=-1, source_id="hero_1")

        assert marker.target_id == "hero_2"
        assert marker.value == -1
        assert marker.source_id == "hero_1"
        assert marker.is_placed is True

    def test_marker_remove(self):
        """remove() clears target, value, and source."""
        marker = Marker(type=MarkerType.VENOM)
        marker.place(target_id="hero_2", value=-1, source_id="hero_1")
        marker.remove()

        assert marker.target_id is None
        assert marker.value == 0
        assert marker.source_id is None
        assert marker.is_placed is False

    def test_marker_get_stat_effects_venom(self):
        """get_stat_effects returns correct effects for VENOM marker."""
        marker = Marker(type=MarkerType.VENOM)
        marker.place(target_id="hero_2", value=-2, source_id="hero_1")

        effects = marker.get_stat_effects()

        # Should have 3 effects, all with value -2
        assert len(effects) == 3
        effect_dict = {stat: val for stat, val in effects}
        assert effect_dict[StatType.ATTACK] == -2
        assert effect_dict[StatType.DEFENSE] == -2
        assert effect_dict[StatType.INITIATIVE] == -2

    def test_marker_get_stat_effects_unplaced(self):
        """get_stat_effects returns 0 values when marker is not placed."""
        marker = Marker(type=MarkerType.VENOM)

        effects = marker.get_stat_effects()

        # Should still return effects, but with value 0
        assert len(effects) == 3
        for stat, val in effects:
            assert val == 0


class TestGameStateMarkers:
    """Tests for GameState marker integration."""

    @pytest.fixture
    def game_state(self):
        """Create a minimal GameState for testing."""
        from goa2.domain.state import GameState
        from goa2.domain.board import Board
        from goa2.domain.models import TeamColor, Team

        board = Board(zones={}, tiles={})
        teams = {
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[], minions=[]),
        }
        return GameState(board=board, teams=teams)

    def test_get_marker_creates_if_not_exists(self, game_state):
        """get_marker creates a new marker if it doesn't exist."""
        assert MarkerType.VENOM not in game_state.markers

        marker = game_state.get_marker(MarkerType.VENOM)

        assert marker.type == MarkerType.VENOM
        assert MarkerType.VENOM in game_state.markers

    def test_get_marker_returns_existing(self, game_state):
        """get_marker returns the same marker instance."""
        marker1 = game_state.get_marker(MarkerType.VENOM)
        marker2 = game_state.get_marker(MarkerType.VENOM)

        assert marker1 is marker2

    def test_place_marker(self, game_state):
        """place_marker places a marker on a target."""
        marker = game_state.place_marker(
            marker_type=MarkerType.VENOM,
            target_id="hero_2",
            value=-1,
            source_id="hero_1",
        )

        assert marker.target_id == "hero_2"
        assert marker.value == -1
        assert marker.source_id == "hero_1"

    def test_place_marker_singleton_behavior(self, game_state):
        """Placing marker on new target removes it from old target."""
        game_state.place_marker(MarkerType.VENOM, "hero_1", -1, "hero_rogue")
        game_state.place_marker(MarkerType.VENOM, "hero_2", -2, "hero_rogue")

        marker = game_state.get_marker(MarkerType.VENOM)
        assert marker.target_id == "hero_2"
        assert marker.value == -2

    def test_remove_marker(self, game_state):
        """remove_marker returns marker to supply."""
        game_state.place_marker(MarkerType.VENOM, "hero_1", -1, "hero_rogue")

        marker = game_state.remove_marker(MarkerType.VENOM)

        assert marker is not None
        assert marker.target_id is None
        assert marker.is_placed is False

    def test_remove_marker_nonexistent(self, game_state):
        """remove_marker returns None if marker doesn't exist."""
        result = game_state.remove_marker(MarkerType.VENOM)
        assert result is None

    def test_get_markers_on_hero(self, game_state):
        """get_markers_on_hero returns all markers on a specific hero."""
        game_state.place_marker(MarkerType.VENOM, "hero_1", -1, "hero_rogue")

        markers = game_state.get_markers_on_hero("hero_1")

        assert len(markers) == 1
        assert markers[0].type == MarkerType.VENOM

    def test_get_markers_on_hero_empty(self, game_state):
        """get_markers_on_hero returns empty list if no markers on hero."""
        game_state.place_marker(MarkerType.VENOM, "hero_1", -1, "hero_rogue")

        markers = game_state.get_markers_on_hero("hero_2")

        assert len(markers) == 0

    def test_return_all_markers(self, game_state):
        """return_all_markers returns all markers to supply."""
        game_state.place_marker(MarkerType.VENOM, "hero_1", -1, "hero_rogue")

        game_state.return_all_markers()

        marker = game_state.get_marker(MarkerType.VENOM)
        assert marker.is_placed is False

    def test_return_markers_from_hero(self, game_state):
        """return_markers_from_hero removes markers from a specific hero."""
        game_state.place_marker(MarkerType.VENOM, "hero_1", -1, "hero_rogue")

        removed = game_state.return_markers_from_hero("hero_1")

        assert len(removed) == 1
        assert removed[0].type == MarkerType.VENOM
        assert removed[0].is_placed is False

    def test_return_markers_from_hero_only_affects_target(self, game_state):
        """return_markers_from_hero doesn't affect markers on other heroes."""
        game_state.place_marker(MarkerType.VENOM, "hero_2", -1, "hero_rogue")

        removed = game_state.return_markers_from_hero("hero_1")

        assert len(removed) == 0
        marker = game_state.get_marker(MarkerType.VENOM)
        assert marker.target_id == "hero_2"

    def test_return_markers_by_source(self, game_state):
        """return_markers_by_source removes markers placed by a source."""
        game_state.place_marker(MarkerType.VENOM, "hero_1", -1, "hero_rogue")

        removed = game_state.return_markers_by_source("hero_rogue")

        assert len(removed) == 1
        assert removed[0].is_placed is False

    def test_return_markers_by_source_only_affects_source(self, game_state):
        """return_markers_by_source doesn't affect markers from other sources."""
        game_state.place_marker(MarkerType.VENOM, "hero_1", -1, "hero_rogue")

        removed = game_state.return_markers_by_source("hero_other")

        assert len(removed) == 0
        marker = game_state.get_marker(MarkerType.VENOM)
        assert marker.is_placed is True

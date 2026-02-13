"""
Tests for player-scoped views (Phase 4 of Client-Readiness Roadmap).

Tests verify that:
1. Requesting hero sees all their cards (including facedown)
2. Other heroes see only faceup cards
3. Public info (board, units, effects, discard piles) is visible to all
4. Spectator view (for_hero_id=None) shows only public info
"""

import pytest

from goa2.domain.state import GameState
from goa2.domain.hex import Hex
from goa2.domain.models import (
    TeamColor,
    Hero,
    Card,
    CardTier,
    CardColor,
    CardState,
    ActionType,
    MinionType,
    StatType,
    GamePhase,
)
from goa2.domain.types import HeroID
from goa2.domain.views import build_view
from goa2.domain.board import Board, Zone
from goa2.domain.models.team import Team


@pytest.fixture
def sample_state():
    """Create a minimal game state with two heroes."""
    # Create heroes
    hero_a = Hero(
        id=HeroID("hero_a"),
        name="Hero A",
        team=TeamColor.RED,
        level=1,
        gold=0,
        deck=[],
        hand=[],
        played_cards=[],
        discard_pile=[],
    )

    hero_b = Hero(
        id=HeroID("hero_b"),
        name="Hero B",
        team=TeamColor.BLUE,
        level=1,
        gold=0,
        deck=[],
        hand=[],
        played_cards=[],
        discard_pile=[],
    )

    # Add cards to heroes
    # Hero A's hand: 2 facedown cards, 1 faceup card
    hero_a.hand = [
        Card(
            id="a1",
            name="Card A1",
            tier=CardTier.I,
            color=CardColor.RED,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            effect_id="test_effect",
            effect_text="Test effect",
            initiative=5,
            state=CardState.HAND,
            is_facedown=True,
        ),
        Card(
            id="a2",
            name="Card A2",
            tier=CardTier.II,
            color=CardColor.RED,
            primary_action=ActionType.MOVEMENT,
            primary_action_value=2,
            effect_id="test_effect",
            effect_text="Test effect",
            initiative=4,
            state=CardState.HAND,
            is_facedown=True,
        ),
        Card(
            id="a3",
            name="Card A3",
            tier=CardTier.I,
            color=CardColor.RED,
            primary_action=ActionType.ATTACK,
            primary_action_value=4,
            effect_id="test_effect",
            effect_text="Test effect",
            initiative=6,
            state=CardState.HAND,
            is_facedown=False,  # Faceup
        ),
    ]

    hero_a.deck = [
        Card(
            id="a_deck1",
            name="Deck A1",
            tier=CardTier.I,
            color=CardColor.RED,
            primary_action=ActionType.ATTACK,
            primary_action_value=2,
            effect_id="test_effect",
            effect_text="Test effect",
            initiative=3,
            state=CardState.DECK,
            is_facedown=True,
        ),
    ]

    # Hero B's hand: 1 facedown card, 1 faceup card
    hero_b.hand = [
        Card(
            id="b1",
            name="Card B1",
            tier=CardTier.I,
            color=CardColor.BLUE,
            primary_action=ActionType.DEFENSE,
            primary_action_value=2,
            effect_id="test_effect",
            effect_text="Test effect",
            initiative=5,
            state=CardState.HAND,
            is_facedown=True,
        ),
        Card(
            id="b2",
            name="Card B2",
            tier=CardTier.I,
            color=CardColor.BLUE,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            effect_id="test_effect",
            effect_text="Test effect",
            initiative=4,
            state=CardState.HAND,
            is_facedown=False,  # Faceup
        ),
    ]

    hero_b.deck = [
        Card(
            id="b_deck1",
            name="Deck B1",
            tier=CardTier.I,
            color=CardColor.BLUE,
            primary_action=ActionType.ATTACK,
            primary_action_value=2,
            effect_id="test_effect",
            effect_text="Test effect",
            initiative=3,
            state=CardState.DECK,
            is_facedown=True,
        ),
    ]

    # Add discard pile (public info)
    hero_a.discard_pile = [
        Card(
            id="a_discard",
            name="Discarded A",
            tier=CardTier.I,
            color=CardColor.RED,
            primary_action=ActionType.ATTACK,
            primary_action_value=1,
            effect_id="test_effect",
            effect_text="Test effect",
            initiative=2,
            state=CardState.DISCARD,
            is_facedown=False,
        ),
    ]

    # Add teams
    team_a = Team(color=TeamColor.RED, heroes=[hero_a], life_counters=5)
    team_b = Team(color=TeamColor.BLUE, heroes=[hero_b], life_counters=5)

    # Create a simple board
    from goa2.domain.models.spawn import SpawnPoint, SpawnType

    zone = Zone(
        id="test_zone",
        hexes=set(),
        neighbors=[],
        spawn_points=[
            SpawnPoint(
                location=Hex(q=0, r=0, s=0),
                team=TeamColor.RED,
                type=SpawnType.HERO,
            ),
            SpawnPoint(
                location=Hex(q=5, r=-5, s=0),
                team=TeamColor.BLUE,
                type=SpawnType.HERO,
            ),
        ],
    )

    board = Board(zones={zone.id: zone}, tiles={}, lane=["test_zone"])

    # Create state with required fields
    state = GameState(
        board=board,
        teams={TeamColor.RED: team_a, TeamColor.BLUE: team_b},
        entity_locations={},
        active_effects=[],
        markers={},
        round=1,
        turn=1,
        phase=GamePhase.PLANNING,
        active_zone_id="test_zone",
    )

    return state


class TestHeroScopedView:
    """Tests for hero-scoped views (for_hero_id specified)."""

    def test_own_hero_sees_facedown_hand_cards(self, sample_state):
        """Hero A sees their facedown hand cards with full details."""
        view = build_view(sample_state, for_hero_id=HeroID("hero_a"))

        hero_a_view = view["teams"]["RED"]["heroes"][0]
        hand_cards = hero_a_view["hand"]

        # Should see all 3 cards
        assert len(hand_cards) == 3

        # Facedown cards show full details
        facedown_cards = [c for c in hand_cards if c["is_facedown"]]
        assert len(facedown_cards) == 2

        for card in facedown_cards:
            assert card["name"] is not None
            assert card["effect_id"] is not None
            assert card["effect_text"] != ""
            assert card["primary_action"] is not None

    def test_other_hero_does_not_see_facedown_hand_cards(self, sample_state):
        """Hero A looking at Hero B's hand sees only faceup cards."""
        view = build_view(sample_state, for_hero_id=HeroID("hero_a"))

        hero_b_view = view["teams"]["BLUE"]["heroes"][0]
        hand_cards = hero_b_view["hand"]

        # Should see both cards
        assert len(hand_cards) == 2

        # Facedown card uses current_* pattern (hides details)
        facedown = [c for c in hand_cards if c["is_facedown"]][0]
        assert facedown["effect_id"] is None
        assert facedown["effect_text"] == ""
        assert facedown["primary_action"] is None

        # Faceup card shows details
        faceup = [c for c in hand_cards if not c["is_facedown"]][0]
        assert faceup["effect_id"] is not None
        assert faceup["effect_text"] != ""
        assert faceup["primary_action"] is not None

    def test_own_hero_sees_deck_details(self, sample_state):
        """Hero sees their full deck."""
        view = build_view(sample_state, for_hero_id=HeroID("hero_a"))

        hero_a_view = view["teams"]["RED"]["heroes"][0]
        deck = hero_a_view["deck"]

        # Should see full deck list
        assert isinstance(deck, list)
        assert len(deck) == 1
        assert deck[0]["id"] == "a_deck1"
        assert deck[0]["name"] == "Deck A1"

    def test_other_hero_sees_only_deck_count(self, sample_state):
        """Other heroes see only deck count, not card details."""
        view = build_view(sample_state, for_hero_id=HeroID("hero_a"))

        hero_b_view = view["teams"]["BLUE"]["heroes"][0]
        deck = hero_b_view["deck"]

        # Should see count only
        assert isinstance(deck, dict)
        assert deck["count"] == 1
        assert "name" not in deck

    def test_discard_pile_always_visible(self, sample_state):
        """Discard pile is visible to everyone."""
        view_a = build_view(sample_state, for_hero_id=HeroID("hero_a"))
        view_b = build_view(sample_state, for_hero_id=HeroID("hero_b"))

        # Both should see Hero A's discard pile
        discard_a = view_a["teams"]["RED"]["heroes"][0]["discard_pile"]
        discard_b = view_b["teams"]["RED"]["heroes"][0]["discard_pile"]

        assert len(discard_a) == 1
        assert len(discard_b) == 1
        assert discard_a[0]["name"] == "Discarded A"
        assert discard_b[0]["name"] == "Discarded A"

    def test_public_board_info_visible_to_all(self, sample_state):
        """Board info is visible to everyone."""
        view_a = build_view(sample_state, for_hero_id=HeroID("hero_a"))
        view_b = build_view(sample_state, for_hero_id=HeroID("hero_b"))

        # Both should see board state
        assert "board" in view_a
        assert "board" in view_b
        assert view_a["board"]["zones"]["test_zone"]["id"] == "test_zone"
        assert view_b["board"]["zones"]["test_zone"]["id"] == "test_zone"

    def test_public_team_info_visible_to_all(self, sample_state):
        """Team info (life counters) is visible to everyone."""
        view_a = build_view(sample_state, for_hero_id=HeroID("hero_a"))
        view_b = build_view(sample_state, for_hero_id=HeroID("hero_b"))

        # Both should see life counters
        assert view_a["teams"]["RED"]["life_counters"] == 5
        assert view_b["teams"]["RED"]["life_counters"] == 5
        assert view_a["teams"]["BLUE"]["life_counters"] == 5
        assert view_b["teams"]["BLUE"]["life_counters"] == 5


class TestSpectatorView:
    """Tests for public/spectator view (for_hero_id=None)."""

    def test_spectator_sees_only_faceup_cards(self, sample_state):
        """Spectator sees only faceup cards from everyone."""
        view = build_view(sample_state, for_hero_id=None)

        hero_a_hand = view["teams"]["RED"]["heroes"][0]["hand"]
        hero_b_hand = view["teams"]["BLUE"]["heroes"][0]["hand"]

        # All facedown cards should hide details
        facedown_a = [c for c in hero_a_hand if c["is_facedown"]]
        facedown_b = [c for c in hero_b_hand if c["is_facedown"]]

        for card in facedown_a + facedown_b:
            assert card["effect_id"] is None
            assert card["effect_text"] == ""

        # Faceup cards show details
        faceup_a = [c for c in hero_a_hand if not c["is_facedown"]]
        faceup_b = [c for c in hero_b_hand if not c["is_facedown"]]

        for card in faceup_a + faceup_b:
            assert card["effect_id"] is not None

    def test_spectator_sees_only_deck_counts(self, sample_state):
        """Spectator sees only deck counts."""
        view = build_view(sample_state, for_hero_id=None)

        hero_a_deck = view["teams"]["RED"]["heroes"][0]["deck"]
        hero_b_deck = view["teams"]["BLUE"]["heroes"][0]["deck"]

        assert isinstance(hero_a_deck, dict)
        assert hero_a_deck["count"] == 1
        assert isinstance(hero_b_deck, dict)
        assert hero_b_deck["count"] == 1

    def test_spectator_sees_discard_piles(self, sample_state):
        """Spectator sees discard piles (public info)."""
        view = build_view(sample_state, for_hero_id=None)

        discard_a = view["teams"]["RED"]["heroes"][0]["discard_pile"]

        assert len(discard_a) == 1
        assert discard_a[0]["name"] == "Discarded A"


class TestCardViewHelper:
    """Tests for _build_card_view helper function."""

    def test_facedown_card_shows_full_details_when_show_facedown_true(self):
        """When show_facedown=True, facedown cards show full details."""
        from goa2.domain.views import _build_card_view

        card = Card(
            id="test_card",
            name="Test Card",
            tier=CardTier.I,
            color=CardColor.RED,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            effect_id="test_effect",
            effect_text="Test effect",
            initiative=5,
            state=CardState.HAND,
            is_facedown=True,
        )

        view = _build_card_view(card, show_facedown=True)

        assert view["id"] == "test_card"
        assert view["name"] == "Test Card"
        assert view["effect_id"] == "test_effect"
        assert view["effect_text"] == "Test effect"
        assert view["primary_action"] == "ATTACK"
        assert view["is_facedown"] is True

    def test_facedown_card_hides_details_when_show_facedown_false(self):
        """When show_facedown=False, facedown cards hide details."""
        from goa2.domain.views import _build_card_view

        card = Card(
            id="test_card",
            name="Test Card",
            tier=CardTier.I,
            color=CardColor.RED,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            effect_id="test_effect",
            effect_text="Test effect",
            initiative=5,
            state=CardState.HAND,
            is_facedown=True,
        )

        view = _build_card_view(card, show_facedown=False)

        assert view["id"] == "test_card"
        assert view["name"] == "Test Card"  # Name is still visible (id-based)
        assert view["effect_id"] is None  # Hidden
        assert view["effect_text"] == ""  # Hidden
        assert view["primary_action"] is None  # Hidden
        assert view["primary_action_value"] is None  # Hidden
        assert view["is_facedown"] is True

    def test_faceup_card_shows_details_regardless_of_show_facedown(self):
        """Faceup cards always show details."""
        from goa2.domain.views import _build_card_view

        card = Card(
            id="test_card",
            name="Test Card",
            tier=CardTier.I,
            color=CardColor.RED,
            primary_action=ActionType.ATTACK,
            primary_action_value=3,
            effect_id="test_effect",
            effect_text="Test effect",
            initiative=5,
            state=CardState.HAND,
            is_facedown=False,
        )

        view_true = _build_card_view(card, show_facedown=True)
        view_false = _build_card_view(card, show_facedown=False)

        # Both should show details
        for view in [view_true, view_false]:
            assert view["effect_id"] == "test_effect"
            assert view["effect_text"] == "Test effect"
            assert view["primary_action"] == "ATTACK"

    def test_none_card_returns_none(self):
        """None card returns None."""
        from goa2.domain.views import _build_card_view

        view = _build_card_view(None, show_facedown=True)
        assert view is None


class TestViewStructure:
    """Tests for overall view structure."""

    def test_view_has_all_top_level_fields(self, sample_state):
        """View contains all expected top-level fields."""
        view = build_view(sample_state, for_hero_id=HeroID("hero_a"))

        assert "phase" in view
        assert "round" in view
        assert "turn" in view
        assert "teams" in view
        assert "board" in view
        assert "effects" in view
        assert "markers" in view

    def test_teams_structure(self, sample_state):
        """Teams section has correct structure."""
        view = build_view(sample_state, for_hero_id=HeroID("hero_a"))

        assert "RED" in view["teams"]
        assert "BLUE" in view["teams"]

        red_team = view["teams"]["RED"]
        assert "color" in red_team
        assert "life_counters" in red_team
        assert "heroes" in red_team
        assert "minions" in red_team

    def test_hero_structure(self, sample_state):
        """Hero view has correct structure."""
        view = build_view(sample_state, for_hero_id=HeroID("hero_a"))

        hero = view["teams"]["RED"]["heroes"][0]
        expected_fields = [
            "id",
            "name",
            "title",
            "team",
            "level",
            "gold",
            "items",
            "hand",
            "deck",
            "played_cards",
            "current_turn_card",
            "discard_pile",
            "ultimate_card",
        ]

        for field in expected_fields:
            assert field in hero, f"Missing field: {field}"

    def test_card_view_structure(self, sample_state):
        """Card view has expected fields."""
        view = build_view(sample_state, for_hero_id=HeroID("hero_a"))

        # Get a facedown card (hero's own view)
        hand = view["teams"]["RED"]["heroes"][0]["hand"]
        card = [c for c in hand if c["is_facedown"]][0]

        expected_fields = [
            "id",
            "name",
            "tier",
            "color",
            "primary_action",
            "primary_action_value",
            "secondary_actions",
            "effect_id",
            "effect_text",
            "initiative",
            "state",
            "is_facedown",
            "is_ranged",
            "range_value",
            "radius_value",
            "item",
            "is_active",
        ]

        for field in expected_fields:
            assert field in card, f"Missing field: {field}"

    def test_board_structure(self, sample_state):
        """Board view has correct structure."""
        view = build_view(sample_state, for_hero_id=HeroID("hero_a"))

        board = view["board"]
        assert "tiles" in board
        assert "zones" in board
        assert "entity_locations" in board

    def test_effects_structure(self, sample_state):
        """Effects view has correct structure."""
        view = build_view(sample_state, for_hero_id=HeroID("hero_a"))

        effects = view["effects"]
        assert isinstance(effects, list)

    def test_markers_structure(self, sample_state):
        """Markers view has correct structure."""
        view = build_view(sample_state, for_hero_id=HeroID("hero_a"))

        markers = view["markers"]
        assert isinstance(markers, dict)

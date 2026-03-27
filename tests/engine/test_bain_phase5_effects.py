"""Tests for Bain Phase 5: Get Over Here! and A Complicated Profession."""

import pytest
import goa2.scripts.bain_effects  # noqa: F401 — registers effects

from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Minion,
    MinionType,
    Card,
    CardTier,
    CardColor,
    CardState,
    ActionType,
)
from goa2.domain.models.marker import MarkerType
from goa2.domain.hex import Hex
from goa2.domain.types import HeroID
from goa2.engine.steps import PlaceMarkerStep, ResolveCardStep
from goa2.engine.handler import process_resolution_stack, push_steps


# ---------------------------------------------------------------------------
# Card factories
# ---------------------------------------------------------------------------


def _make_skill_card(card_id, name, effect_id, **overrides):
    defaults = dict(
        id=card_id,
        name=name,
        tier=CardTier.UNTIERED,
        color=CardColor.SILVER,
        initiative=13,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        is_ranged=True,
        range_value=4,
        effect_id=effect_id,
        effect_text="",
        is_facedown=False,
    )
    defaults.update(overrides)
    return Card(**defaults)


def _make_filler_card(card_id="filler", color=CardColor.GOLD):
    return Card(
        id=card_id,
        name="Filler",
        tier=CardTier.UNTIERED,
        color=color,
        initiative=1,
        primary_action=ActionType.ATTACK,
        secondary_actions={},
        is_ranged=False,
        range_value=0,
        primary_action_value=1,
        effect_id="filler",
        effect_text="",
        is_facedown=False,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def board():
    b = Board()
    hexes = set()
    for q in range(-5, 6):
        for r in range(-5, 6):
            s = -q - r
            if abs(s) <= 5:
                hexes.add(Hex(q=q, r=r, s=s))
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    b.zones = {"z1": z1}
    b.populate_tiles_from_zones()
    return b


def _build_state(board, bain_card, bain_hex, enemy_hex, extra_units=None):
    """Build state with Bain and an enemy hero at given positions."""
    bain = Hero(id=HeroID("hero_bain"), name="Bain", team=TeamColor.RED, deck=[], hand=[])
    bain.current_turn_card = bain_card

    enemy = Hero(
        id=HeroID("hero_enemy"), name="Enemy", team=TeamColor.BLUE,
        deck=[], hand=[_make_filler_card("enemy_card")],
    )

    red_minions = []
    blue_minions = []
    if extra_units:
        for uid, team, hex_pos in extra_units:
            m = Minion(id=uid, name=uid, team=team, type=MinionType.MELEE)
            if team == TeamColor.RED:
                red_minions.append(m)
            else:
                blue_minions.append(m)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[bain], minions=red_minions),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=blue_minions),
        },
    )
    state.place_entity("hero_bain", bain_hex)
    state.place_entity("hero_enemy", enemy_hex)
    if extra_units:
        for uid, _team, hex_pos in extra_units:
            state.place_entity(uid, hex_pos)
    state.current_actor_id = "hero_bain"
    return state


def _drive_to_skill(state):
    """Drive through ResolveCardStep until SKILL action is chosen."""
    push_steps(state, [ResolveCardStep(hero_id="hero_bain")])
    req = process_resolution_stack(state)
    assert req["type"] == "CHOOSE_ACTION"
    state.execution_stack[-1].pending_input = {"selection": "SKILL"}


# ===========================================================================
# ClearLineOfSightFilter — blocked_by_obstacles mode
# ===========================================================================


class TestClearLineOfSightObstacleMode:
    """blocked_by_obstacles uses is_obstacle_for_actor for intermediate hexes."""

    def test_blocks_when_occupied_hex_in_path(self, board):
        """A unit between origin and candidate blocks the line."""
        from goa2.engine.filters import ClearLineOfSightFilter

        card = _make_skill_card("test", "Test", "get_over_here")
        blocker_hex = Hex(q=2, r=0, s=-2)
        state = _build_state(
            board, card,
            bain_hex=Hex(q=0, r=0, s=0),
            enemy_hex=Hex(q=4, r=0, s=-4),
            extra_units=[("blocker", TeamColor.RED, blocker_hex)],
        )

        f = ClearLineOfSightFilter(
            blocked_by_units=False,
            blocked_by_terrain=False,
            blocked_by_obstacles=True,
        )
        # Enemy is at q=4 — blocker at q=2 blocks the obstacle-aware path
        assert f.apply("hero_enemy", state, {}) is False

    def test_passes_when_path_clear(self, board):
        """No obstacles between origin and candidate passes."""
        from goa2.engine.filters import ClearLineOfSightFilter

        card = _make_skill_card("test", "Test", "get_over_here")
        state = _build_state(
            board, card,
            bain_hex=Hex(q=0, r=0, s=0),
            enemy_hex=Hex(q=3, r=0, s=-3),
        )

        f = ClearLineOfSightFilter(
            blocked_by_units=False,
            blocked_by_terrain=False,
            blocked_by_obstacles=True,
        )
        assert f.apply("hero_enemy", state, {}) is True


# ===========================================================================
# Get Over Here! — full card flow
# ===========================================================================


class TestGetOverHere:
    """Get Over Here!: Target unit in range, straight line, no obstacles.
    Move target to adjacent hex toward Bain."""

    def test_pulls_enemy_to_adjacent(self, board):
        """Enemy at distance 3 is moved to hex adjacent to Bain."""
        card = _make_skill_card("get_over_here", "Get Over Here!", "get_over_here")
        bain_hex = Hex(q=0, r=0, s=0)
        enemy_hex = Hex(q=3, r=0, s=-3)
        state = _build_state(board, card, bain_hex, enemy_hex)

        _drive_to_skill(state)

        # Select enemy unit
        req = process_resolution_stack(state)
        assert req["type"] == "SELECT_UNIT"
        state.execution_stack[-1].pending_input = {"selection": "hero_enemy"}

        # Process remaining steps (ComputeHexStep auto + MoveUnitStep)
        req = process_resolution_stack(state)
        while req is not None:
            req = process_resolution_stack(state)

        final_loc = state.entity_locations.get("hero_enemy")
        assert final_loc == Hex(q=1, r=0, s=-1)

    def test_pulls_at_max_range(self, board):
        """Enemy at range 4 (max) is moved to adjacent."""
        card = _make_skill_card("get_over_here", "Get Over Here!", "get_over_here")
        bain_hex = Hex(q=0, r=0, s=0)
        enemy_hex = Hex(q=4, r=0, s=-4)
        state = _build_state(board, card, bain_hex, enemy_hex)

        _drive_to_skill(state)

        req = process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "hero_enemy"}

        req = process_resolution_stack(state)
        while req is not None:
            req = process_resolution_stack(state)

        final_loc = state.entity_locations.get("hero_enemy")
        assert final_loc == Hex(q=1, r=0, s=-1)

    def test_pulls_along_diagonal(self, board):
        """Works on non-east axis (diagonal straight line)."""
        card = _make_skill_card("get_over_here", "Get Over Here!", "get_over_here")
        bain_hex = Hex(q=0, r=0, s=0)
        enemy_hex = Hex(q=0, r=3, s=-3)  # south-east axis
        state = _build_state(board, card, bain_hex, enemy_hex)

        _drive_to_skill(state)

        req = process_resolution_stack(state)
        state.execution_stack[-1].pending_input = {"selection": "hero_enemy"}

        req = process_resolution_stack(state)
        while req is not None:
            req = process_resolution_stack(state)

        final_loc = state.entity_locations.get("hero_enemy")
        assert final_loc == Hex(q=0, r=1, s=-1)

    def test_blocked_by_obstacle_in_path_not_selectable(self, board):
        """Enemy behind an obstacle cannot be selected (blocker is offered instead)."""
        card = _make_skill_card("get_over_here", "Get Over Here!", "get_over_here")
        bain_hex = Hex(q=0, r=0, s=0)
        enemy_hex = Hex(q=3, r=0, s=-3)
        blocker_hex = Hex(q=1, r=0, s=-1)
        state = _build_state(
            board, card, bain_hex, enemy_hex,
            extra_units=[("blocker", TeamColor.BLUE, blocker_hex)],
        )

        _drive_to_skill(state)

        # The select step should not offer hero_enemy (blocked by obstacle)
        # blocker IS adjacent in straight line with clear path, so it's offered
        req = process_resolution_stack(state)
        assert req is not None
        assert req["type"] == "SELECT_UNIT"
        option_ids = set(req["valid_options"])
        assert "hero_enemy" not in option_ids
        assert "blocker" in option_ids

    def test_no_valid_targets_aborts(self, board):
        """Enemy not in a straight line — no valid targets, effect aborts."""
        card = _make_skill_card("get_over_here", "Get Over Here!", "get_over_here")
        bain_hex = Hex(q=0, r=0, s=0)
        enemy_hex = Hex(q=2, r=1, s=-3)  # not in straight line
        state = _build_state(board, card, bain_hex, enemy_hex)

        _drive_to_skill(state)

        # Mandatory select with no valid targets → aborts, stack empties
        req = process_resolution_stack(state)
        while req is not None:
            req = process_resolution_stack(state)

        # Enemy didn't move
        final_loc = state.entity_locations.get("hero_enemy")
        assert final_loc == enemy_hex


# ===========================================================================
# A Complicated Profession — passive after placing Bounty marker
# ===========================================================================


def _make_ultimate_card():
    """Bain's ultimate card (A Complicated Profession)."""
    c = Card(
        id="a_complicated_profession",
        name="A Complicated Profession",
        tier=CardTier.IV,
        color=CardColor.PURPLE,
        initiative=0,
        primary_action=ActionType.SKILL,
        secondary_actions={},
        effect_id="a_complicated_profession",
        effect_text="After you give a hero the Bounty marker, that hero discards a card, if able.",
        is_facedown=False,
    )
    c.state = CardState.PASSIVE
    return c


def _build_passive_state(board):
    """State with Bain (level 8, ultimate) and enemy with cards in hand."""
    bain = Hero(
        id=HeroID("hero_bain"), name="Bain", team=TeamColor.RED,
        deck=[], hand=[], level=8,
    )
    bain.current_turn_card = _make_filler_card("bain_card")
    bain.ultimate_card = _make_ultimate_card()

    enemy = Hero(
        id=HeroID("hero_enemy"), name="Enemy", team=TeamColor.BLUE,
        deck=[], hand=[
            _make_filler_card("enemy_c1"),
            _make_filler_card("enemy_c2"),
        ],
    )

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[bain], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.place_entity("hero_bain", Hex(q=0, r=0, s=0))
    state.place_entity("hero_enemy", Hex(q=1, r=0, s=-1))
    state.current_actor_id = "hero_bain"
    return state


class TestAComplicatedProfession:
    """A Complicated Profession: After placing Bounty marker, victim discards."""

    def test_placing_bounty_triggers_discard(self, board):
        """Placing Bounty marker on enemy triggers a forced discard."""
        state = _build_passive_state(board)

        push_steps(state, [
            PlaceMarkerStep(
                marker_type=MarkerType.BOUNTY,
                target_id="hero_enemy",
                value=0,
            ),
        ])

        result = process_resolution_stack(state)

        # Passive fires: enemy must choose a card to discard
        assert result is not None
        assert result["type"] == "SELECT_CARD"

        state.execution_stack[-1].pending_input = {"selection": "enemy_c1"}

        result = process_resolution_stack(state)
        while result is not None:
            result = process_resolution_stack(state)

        enemy = state.get_hero(HeroID("hero_enemy"))
        assert len(enemy.hand) == 1
        assert enemy.hand[0].id == "enemy_c2"
        assert any(c.id == "enemy_c1" for c in enemy.discard_pile)

    def test_no_passive_without_ultimate(self, board):
        """Without the ultimate card (level < 8), no discard triggered."""
        state = _build_passive_state(board)
        bain = state.get_hero(HeroID("hero_bain"))
        bain.level = 1  # Too low for ultimate

        push_steps(state, [
            PlaceMarkerStep(
                marker_type=MarkerType.BOUNTY,
                target_id="hero_enemy",
                value=0,
            ),
        ])

        result = process_resolution_stack(state)
        # No passive — stack should be done (maybe CheckPassive runs but finds nothing)
        while result is not None:
            assert result.get("type") != "SELECT_CARD"
            result = process_resolution_stack(state)

        enemy = state.get_hero(HeroID("hero_enemy"))
        assert len(enemy.hand) == 2  # No cards discarded

    def test_victim_with_no_cards_no_discard(self, board):
        """If victim has no cards, passive fires but does nothing."""
        state = _build_passive_state(board)
        enemy = state.get_hero(HeroID("hero_enemy"))
        enemy.hand = []  # No cards

        push_steps(state, [
            PlaceMarkerStep(
                marker_type=MarkerType.BOUNTY,
                target_id="hero_enemy",
                value=0,
            ),
        ])

        result = process_resolution_stack(state)
        while result is not None:
            result = process_resolution_stack(state)

        # No crash, no discard
        assert len(enemy.hand) == 0

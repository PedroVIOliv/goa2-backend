"""Tests for Brogan's Shield Bash / Counterattack and PlayedCardFilter."""

import pytest
import goa2.scripts.brogan_effects  # noqa: F401 — registers effects
from goa2.domain.state import GameState
from goa2.domain.board import Board, Zone
from goa2.domain.models import (
    Team,
    TeamColor,
    Hero,
    Card,
    CardTier,
    CardColor,
    ActionType,
)
from goa2.domain.hex import Hex
from goa2.engine.filters import PlayedCardFilter
from goa2.engine.steps import ResolveCardStep, SelectStep
from goa2.engine.handler import process_resolution_stack, push_steps
from goa2.domain.models.enums import TargetType


def _make_attack_card(card_id="atk_card", is_facedown=False):
    return Card(
        id=card_id,
        name="Attack Card",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        effect_id="",
        effect_text="",
        is_facedown=is_facedown,
    )


def _make_movement_card(card_id="mov_card"):
    return Card(
        id=card_id,
        name="Movement Card",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=3,
        primary_action=ActionType.MOVEMENT,
        primary_action_value=2,
        effect_id="",
        effect_text="",
        is_facedown=False,
    )


def _make_skill_card(card_id="skill_card", color=CardColor.GOLD):
    return Card(
        id=card_id,
        name="Skill Card",
        tier=CardTier.UNTIERED,
        color=color,
        initiative=3,
        primary_action=ActionType.SKILL,
        effect_id="",
        effect_text="",
        is_facedown=False,
    )


def _make_shield_bash_card():
    return Card(
        id="shield_bash_card",
        name="Shield Bash",
        tier=CardTier.II,
        color=CardColor.BLUE,
        initiative=4,
        primary_action=ActionType.ATTACK,
        primary_action_value=2,
        effect_id="shield_bash",
        effect_text="An enemy hero adjacent to you who has played an attack card this turn discards a card, if able.",
        is_facedown=False,
    )


def _make_red_attack_card(card_id="red_atk"):
    return Card(
        id=card_id,
        name="Red Attack",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=5,
        primary_action=ActionType.ATTACK,
        primary_action_value=3,
        effect_id="",
        effect_text="",
        is_facedown=False,
    )


def _make_filler_card(card_id="filler"):
    return Card(
        id=card_id,
        name="Filler",
        tier=CardTier.UNTIERED,
        color=CardColor.GOLD,
        initiative=1,
        primary_action=ActionType.ATTACK,
        primary_action_value=1,
        effect_id="",
        effect_text="",
        is_facedown=False,
    )


def _make_base_state():
    """Setup: Brogan adjacent to enemy, both on a simple board."""
    board = Board()
    hexes = set()
    for q in range(-2, 3):
        for r in range(-2, 3):
            s = -q - r
            if abs(s) <= 2:
                hexes.add(Hex(q=q, r=r, s=s))
    z1 = Zone(id="z1", hexes=hexes, neighbors=[])
    board.zones = {"z1": z1}
    board.populate_tiles_from_zones()

    brogan = Hero(id="brogan", name="Brogan", team=TeamColor.RED, deck=[], level=1)
    enemy = Hero(id="enemy", name="Enemy", team=TeamColor.BLUE, deck=[], level=1)

    state = GameState(
        board=board,
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[brogan], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[enemy], minions=[]),
        },
    )
    state.place_entity("brogan", Hex(q=0, r=0, s=0))
    state.place_entity("enemy", Hex(q=1, r=0, s=-1))
    state.current_actor_id = "brogan"
    return state


# =============================================================================
# PlayedCardFilter unit tests
# =============================================================================


class TestPlayedCardFilter:
    """Tests for PlayedCardFilter in isolation."""

    def test_resolved_attack_card_passes(self):
        """Hero with resolved attack card at current turn index passes."""
        state = _make_base_state()
        brogan = state.get_hero("brogan")
        brogan.resolved_turn_count = 0  # current turn index = 0

        enemy = state.get_hero("enemy")
        atk = _make_attack_card()
        enemy.played_cards = [atk]  # resolved at index 0

        f = PlayedCardFilter(action_type=ActionType.ATTACK)
        assert f.apply("enemy", state, {}) is True

    def test_current_turn_card_face_up_attack_passes(self):
        """Hero with face-up current_turn_card attack passes."""
        state = _make_base_state()
        brogan = state.get_hero("brogan")
        brogan.resolved_turn_count = 0

        enemy = state.get_hero("enemy")
        enemy.current_turn_card = _make_attack_card()

        f = PlayedCardFilter(action_type=ActionType.ATTACK)
        assert f.apply("enemy", state, {}) is True

    def test_facedown_current_turn_card_fails(self):
        """Hero with facedown current_turn_card fails (can't see action type)."""
        state = _make_base_state()
        brogan = state.get_hero("brogan")
        brogan.resolved_turn_count = 0

        enemy = state.get_hero("enemy")
        enemy.current_turn_card = _make_attack_card(is_facedown=True)

        f = PlayedCardFilter(action_type=ActionType.ATTACK)
        assert f.apply("enemy", state, {}) is False

    def test_non_attack_card_fails(self):
        """Hero with movement card fails when filtering for ATTACK."""
        state = _make_base_state()
        brogan = state.get_hero("brogan")
        brogan.resolved_turn_count = 0

        enemy = state.get_hero("enemy")
        enemy.current_turn_card = _make_movement_card()

        f = PlayedCardFilter(action_type=ActionType.ATTACK)
        assert f.apply("enemy", state, {}) is False

    def test_no_played_cards_fails(self):
        """Hero with no played cards and no current_turn_card fails."""
        state = _make_base_state()
        brogan = state.get_hero("brogan")
        brogan.resolved_turn_count = 0

        f = PlayedCardFilter(action_type=ActionType.ATTACK)
        assert f.apply("enemy", state, {}) is False

    def test_wrong_turn_index_fails(self):
        """Hero's resolved card at wrong turn index doesn't match."""
        state = _make_base_state()
        brogan = state.get_hero("brogan")
        brogan.resolved_turn_count = 1  # looking at index 1

        enemy = state.get_hero("enemy")
        enemy.played_cards = [_make_attack_card()]  # only index 0

        f = PlayedCardFilter(action_type=ActionType.ATTACK)
        assert f.apply("enemy", state, {}) is False

    def test_card_color_filter_matches(self):
        """Color filter matches card with matching color."""
        state = _make_base_state()
        brogan = state.get_hero("brogan")
        brogan.resolved_turn_count = 0

        enemy = state.get_hero("enemy")
        enemy.current_turn_card = _make_red_attack_card()

        f = PlayedCardFilter(card_color=CardColor.RED)
        assert f.apply("enemy", state, {}) is True

    def test_card_color_filter_rejects_wrong_color(self):
        """Color filter rejects card with different color."""
        state = _make_base_state()
        brogan = state.get_hero("brogan")
        brogan.resolved_turn_count = 0

        enemy = state.get_hero("enemy")
        enemy.current_turn_card = _make_red_attack_card()

        f = PlayedCardFilter(card_color=CardColor.BLUE)
        assert f.apply("enemy", state, {}) is False

    def test_combined_action_and_color_filter(self):
        """Both action_type and card_color must match."""
        state = _make_base_state()
        brogan = state.get_hero("brogan")
        brogan.resolved_turn_count = 0

        enemy = state.get_hero("enemy")
        enemy.current_turn_card = _make_red_attack_card()

        # Both match
        f = PlayedCardFilter(action_type=ActionType.ATTACK, card_color=CardColor.RED)
        assert f.apply("enemy", state, {}) is True

        # Action matches, color doesn't
        f2 = PlayedCardFilter(action_type=ActionType.ATTACK, card_color=CardColor.BLUE)
        assert f2.apply("enemy", state, {}) is False

    def test_non_hero_candidate_fails(self):
        """Non-hero candidate (e.g. minion ID) fails gracefully."""
        state = _make_base_state()
        brogan = state.get_hero("brogan")
        brogan.resolved_turn_count = 0

        f = PlayedCardFilter(action_type=ActionType.ATTACK)
        assert f.apply("nonexistent_unit", state, {}) is False

    def test_no_filter_criteria_matches_any_card(self):
        """With no action_type or card_color, any card passes."""
        state = _make_base_state()
        brogan = state.get_hero("brogan")
        brogan.resolved_turn_count = 0

        enemy = state.get_hero("enemy")
        enemy.current_turn_card = _make_skill_card()

        f = PlayedCardFilter()
        assert f.apply("enemy", state, {}) is True


# =============================================================================
# Shield Bash integration tests
# =============================================================================


class TestShieldBashEffect:
    """Integration tests for the Shield Bash card effect."""

    def test_shield_bash_select_filters_correctly(self):
        """SelectStep with PlayedCardFilter + TeamFilter only shows valid targets."""
        state = _make_base_state()
        brogan = state.get_hero("brogan")
        enemy = state.get_hero("enemy")

        brogan.current_turn_card = _make_shield_bash_card()
        brogan.resolved_turn_count = 0

        # Enemy played an attack card
        enemy.current_turn_card = _make_attack_card()

        from goa2.engine.filters import TeamFilter, UnitTypeFilter, RangeFilter

        select = SelectStep(
            target_type=TargetType.UNIT,
            prompt="Select adjacent enemy hero who played an attack card this turn",
            output_key="bash_victim",
            is_mandatory=False,
            filters=[
                UnitTypeFilter(unit_type="HERO"),
                TeamFilter(relation="ENEMY"),
                RangeFilter(max_range=1),
                PlayedCardFilter(action_type=ActionType.ATTACK),
            ],
        )
        push_steps(state, [select])
        req = process_resolution_stack(state)

        assert req is not None
        assert req["type"] == "SELECT_UNIT"
        # Only enemy should be in candidates
        candidates = req.get("candidates", [])
        assert "enemy" in candidates
        assert "brogan" not in candidates

    def test_shield_bash_no_valid_target_skips(self):
        """No adjacent enemy with attack card → step auto-skips (optional)."""
        state = _make_base_state()
        brogan = state.get_hero("brogan")
        enemy = state.get_hero("enemy")

        brogan.current_turn_card = _make_shield_bash_card()
        brogan.resolved_turn_count = 0

        # Enemy played a MOVEMENT card, not attack
        enemy.current_turn_card = _make_movement_card()

        from goa2.engine.filters import TeamFilter, UnitTypeFilter, RangeFilter

        select = SelectStep(
            target_type=TargetType.UNIT,
            prompt="Select target",
            output_key="bash_victim",
            is_mandatory=False,
            filters=[
                UnitTypeFilter(unit_type="HERO"),
                TeamFilter(relation="ENEMY"),
                RangeFilter(max_range=1),
                PlayedCardFilter(action_type=ActionType.ATTACK),
            ],
        )
        push_steps(state, [select])
        req = process_resolution_stack(state)

        # Should auto-skip since no valid targets (optional step)
        assert req is None

    def test_shield_bash_force_discard_flow(self):
        """Full effect flow: select valid target → force discard."""
        state = _make_base_state()
        brogan = state.get_hero("brogan")
        enemy = state.get_hero("enemy")

        brogan.current_turn_card = _make_shield_bash_card()
        brogan.resolved_turn_count = 0

        # Enemy played an attack card (resolved)
        enemy.played_cards = [_make_attack_card()]
        # Enemy has a card in hand to discard
        filler = _make_filler_card("enemy_hand_card")
        enemy.hand = [filler]

        from goa2.engine.filters import TeamFilter, UnitTypeFilter, RangeFilter
        from goa2.engine.steps import ForceDiscardStep

        # Push the same steps that ShieldBashEffect.build_steps would create
        push_steps(
            state,
            [
                SelectStep(
                    target_type=TargetType.UNIT,
                    prompt="Select target",
                    output_key="bash_victim",
                    is_mandatory=False,
                    filters=[
                        UnitTypeFilter(unit_type="HERO"),
                        TeamFilter(relation="ENEMY"),
                        RangeFilter(max_range=1),
                        PlayedCardFilter(action_type=ActionType.ATTACK),
                    ],
                ),
                ForceDiscardStep(victim_key="bash_victim"),
            ],
        )

        # 1. Select the enemy
        req = process_resolution_stack(state)
        assert req is not None
        assert req["type"] == "SELECT_UNIT"
        state.execution_stack[-1].pending_input = {"selection": "enemy"}

        # 2. ForceDiscardStep resolves and spawns card selection for victim
        req = process_resolution_stack(state)
        assert req is not None
        assert req["type"] == "SELECT_CARD"
        state.execution_stack[-1].pending_input = {"selection": "enemy_hand_card"}

        # 3. DiscardCardStep resolves
        req = process_resolution_stack(state)
        assert req is None

        # Enemy's card was discarded
        assert len(enemy.hand) == 0
        assert len(enemy.discard_pile) == 1
        assert enemy.discard_pile[0].id == "enemy_hand_card"

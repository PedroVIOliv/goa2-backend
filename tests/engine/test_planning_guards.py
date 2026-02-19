"""Tests for planning phase guards: double-commit prevention and auto-pass."""

import pytest

from goa2.domain.board import Board
from goa2.domain.models import (
    ActionType,
    Card,
    CardColor,
    CardTier,
    GamePhase,
    Hero,
    Team,
    TeamColor,
)
from goa2.domain.state import GameState
from goa2.engine.phases import commit_card, end_turn


def _make_card(card_id: str, color: CardColor = CardColor.RED) -> Card:
    return Card(
        id=card_id,
        name=card_id,
        tier=CardTier.I,
        color=color,
        initiative=10,
        primary_action=ActionType.ATTACK,
        primary_action_value=2,
        effect_id="e",
        effect_text="t",
    )


def _make_state_2v2(h1_hand=None, h2_hand=None):
    """Create a 2-hero state in PLANNING phase with configurable hands."""
    c1 = _make_card("c1")
    c2 = _make_card("c2", CardColor.BLUE)
    h1 = Hero(
        id="h1",
        name="H1",
        team=TeamColor.RED,
        deck=[c1],
        hand=h1_hand if h1_hand is not None else [c1],
    )
    h2 = Hero(
        id="h2",
        name="H2",
        team=TeamColor.BLUE,
        deck=[c2],
        hand=h2_hand if h2_hand is not None else [c2],
    )
    state = GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[h1], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[h2], minions=[]),
        },
        phase=GamePhase.PLANNING,
    )
    return state, h1, h2, c1, c2


# ---- Double commit guard ----


def test_double_commit_raises_error():
    """Second commit from same hero raises ValueError."""
    state, h1, h2, c1, c2 = _make_state_2v2()
    commit_card(state, "h1", c1)

    # Second commit should fail
    c_extra = _make_card("c_extra")
    h1.hand.append(c_extra)
    with pytest.raises(ValueError, match="already committed"):
        commit_card(state, "h1", c_extra)


def test_double_commit_does_not_corrupt_state():
    """After a rejected double-commit, the original card is preserved."""
    state, h1, h2, c1, c2 = _make_state_2v2()
    commit_card(state, "h1", c1)

    c_extra = _make_card("c_extra")
    h1.hand.append(c_extra)
    with pytest.raises(ValueError):
        commit_card(state, "h1", c_extra)

    # Original card still in pending_inputs
    assert state.pending_inputs["h1"] == c1
    assert len(state.pending_inputs) == 1


def test_different_heroes_can_both_commit():
    """Two different heroes committing is fine — only same hero twice is blocked."""
    state, h1, h2, c1, c2 = _make_state_2v2()
    commit_card(state, "h1", c1)
    commit_card(state, "h2", c2)

    # Both committed successfully, phase transitions
    assert state.phase == GamePhase.RESOLUTION


# ---- Auto-pass for empty hands ----


def test_auto_pass_empty_hand_on_new_turn():
    """Heroes with empty hands are auto-passed when a new planning turn starts.

    When both heroes have empty hands at turn 3, end_turn cascades:
    turn 3 → PLANNING (auto-pass) → REVELATION → RESOLUTION → end_turn →
    turn 4 → PLANNING (auto-pass) → REVELATION → RESOLUTION → end_turn →
    CLEANUP (turn 4 is last).
    """
    state, h1, h2, c1, c2 = _make_state_2v2()

    h1.hand.clear()
    h2.hand.clear()
    state.phase = GamePhase.RESOLUTION
    state.turn = 3
    state.unresolved_hero_ids = []

    end_turn(state)

    # Cascaded through turn 4 → CLEANUP
    assert state.turn == 4
    assert state.phase == GamePhase.CLEANUP


def test_auto_pass_all_empty_skips_planning():
    """If ALL heroes have empty hands, planning is skipped (no input needed).

    We verify by checking that at turn 3→4 the phase advances past PLANNING
    automatically without any manual commit_card or pass_turn calls.
    """
    state, h1, h2, c1, c2 = _make_state_2v2()

    h1.hand.clear()
    h2.hand.clear()
    state.phase = GamePhase.RESOLUTION
    state.turn = 3
    state.unresolved_hero_ids = []

    end_turn(state)

    # Ended up past PLANNING — the auto-pass worked
    assert state.phase != GamePhase.PLANNING


def test_auto_pass_partial_empty_hands():
    """Only heroes with empty hands are auto-passed; others must commit."""
    state, h1, h2, c1, c2 = _make_state_2v2()

    # h1 has no cards, h2 still has one
    h1.hand.clear()
    state.phase = GamePhase.RESOLUTION
    state.turn = 1
    state.unresolved_hero_ids = []

    end_turn(state)

    # h1 auto-passed, h2 not yet
    assert "h1" in state.pending_inputs
    assert state.pending_inputs["h1"] is None
    assert "h2" not in state.pending_inputs
    # Still in PLANNING, waiting for h2
    assert state.phase == GamePhase.PLANNING

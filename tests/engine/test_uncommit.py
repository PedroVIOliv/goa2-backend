"""Tests for uncommitting a card during Planning (take-back before lock-in)."""

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
from goa2.domain.models.enums import CardState
from goa2.domain.state import GameState
from goa2.engine.phases import commit_card, pass_turn, uncommit_card
from goa2.engine.session import GameSession


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


def test_uncommit_returns_card_to_hand():
    state, h1, _, c1, _ = _make_state_2v2()
    commit_card(state, "h1", c1)
    assert c1 not in h1.hand

    returned = uncommit_card(state, "h1")

    assert returned is c1
    assert c1 in h1.hand
    assert c1.state == CardState.HAND
    assert c1.is_facedown is False
    assert c1.played_this_round is False
    assert h1.current_turn_card is None
    assert "h1" not in state.pending_inputs
    assert state.phase == GamePhase.PLANNING


def test_uncommit_then_commit_other_card():
    extra = _make_card("c1b")
    state, h1, _, c1, _ = _make_state_2v2(h1_hand=None)
    h1.hand.append(extra)

    commit_card(state, "h1", c1)
    uncommit_card(state, "h1")
    commit_card(state, "h1", extra)

    assert state.pending_inputs["h1"] is extra
    assert h1.current_turn_card is extra
    assert c1 in h1.hand


def test_uncommit_without_commit_raises():
    state, _, _, _, _ = _make_state_2v2()
    with pytest.raises(ValueError, match="no committed card"):
        uncommit_card(state, "h1")


def test_uncommit_after_pass_raises():
    state, _, _, _, _ = _make_state_2v2(h2_hand=[])
    pass_turn(state, "h2")
    with pytest.raises(ValueError, match="passed"):
        uncommit_card(state, "h2")


def test_uncommit_rejected_outside_planning():
    """Once the last commit fires revelation, take-backs are locked out."""
    state, _, _, c1, c2 = _make_state_2v2()
    commit_card(state, "h1", c1)
    commit_card(state, "h2", c2)  # last commit -> revelation -> resolution
    assert state.phase != GamePhase.PLANNING
    with pytest.raises(ValueError, match="phase"):
        uncommit_card(state, "h1")


def test_uncommit_lifo_second_card_first_and_clears_planning_done():
    """Two-card hero (Emmitt's Alternative Timelines): LIFO take-back.

    The second-commit state shape is constructed directly (same shape
    commit_card produces) so the test doesn't need the real ultimate wiring.
    """
    extra = _make_card("c1b")
    state, h1, _, c1, _ = _make_state_2v2()
    h1.hand.append(extra)

    commit_card(state, "h1", c1)
    h1.play_card(extra)
    state.pending_second_cards["h1"] = extra
    state.planning_done.append("h1")

    returned = uncommit_card(state, "h1")

    assert returned is extra
    assert extra in h1.hand
    assert h1.current_turn_card is c1  # restored to the first commit
    assert state.pending_inputs["h1"] is c1  # first commit stays
    assert "h1" not in state.pending_second_cards
    assert "h1" not in state.planning_done

    returned2 = uncommit_card(state, "h1")

    assert returned2 is c1
    assert c1 in h1.hand
    assert h1.current_turn_card is None
    assert "h1" not in state.pending_inputs


def test_uncommit_first_card_alone_clears_planning_done():
    state, h1, _, c1, _ = _make_state_2v2()
    h1.hand.append(_make_card("c1b"))
    commit_card(state, "h1", c1)
    state.planning_done.append("h1")

    uncommit_card(state, "h1")

    assert "h1" not in state.planning_done


def test_session_uncommit_card():
    state, _, _, c1, _ = _make_state_2v2()
    session = GameSession(state)
    session.commit_card("h1", c1)

    result = session.uncommit_card("h1")

    assert result.current_phase == GamePhase.PLANNING
    assert "h1" not in state.pending_inputs


def test_session_uncommit_rejected_outside_planning():
    state, _, _, _, _ = _make_state_2v2()
    state.phase = GamePhase.RESOLUTION
    session = GameSession(state)
    with pytest.raises(ValueError, match="Cannot uncommit"):
        session.uncommit_card("h1")

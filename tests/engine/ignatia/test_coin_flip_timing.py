"""F0b — Tie Breaker coin flips AFTER the winner's card resolves.

Locked ruling: on a cross-team initiative tie, the favored team's hero acts
while the coin still shows its original face; the coin flips only after that
hero's card resolves, before the next initiative check. This lets Ignatia (as
a cross-team tie winner) read the correct (pre-flip) face on her turn.
"""

import pytest

from goa2.domain.board import Board
from goa2.domain.hex import Hex
from goa2.domain.models import ActionType, Card, CardColor, CardTier, Hero, Team, TeamColor
from goa2.domain.types import HeroID
from goa2.engine.handler import process_stack, push_steps
from goa2.engine.steps import ResolveTieBreakerStep


def _filler_hand():
    return [
        Card(
            id=f"filler_{i}",
            name=f"Filler {i}",
            tier=CardTier.I,
            color=CardColor.RED,
            initiative=1,
            primary_action=ActionType.SKILL,
            primary_action_value=None,
            effect_id="e",
            effect_text="t",
        )
        for i in range(3)
    ]


@pytest.fixture
def cross_team_tie_state():
    """Red favored (orange face). Cross-team tie A(RED) vs B(BLUE); RED has a
    single candidate so A auto-wins with no input."""
    a = Hero(id=HeroID("A"), name="A", team=TeamColor.RED, deck=[], hand=_filler_hand())
    b = Hero(id=HeroID("B"), name="B", team=TeamColor.BLUE, deck=[], hand=_filler_hand())
    state = GameState_factory(a, b)
    card = Card(
        id="c1",
        name="C",
        tier=CardTier.I,
        color=CardColor.RED,
        initiative=10,
        primary_action=ActionType.SKILL,
        primary_action_value=None,
        effect_id="e",
        effect_text="t",
        is_facedown=False,
    )
    a.current_turn_card = card
    b.current_turn_card = card
    state.move_unit(a.id, Hex(q=0, r=0, s=0))
    state.move_unit(b.id, Hex(q=1, r=0, s=-1))
    return state


def GameState_factory(a, b):
    from goa2.domain.state import GameState

    return GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(color=TeamColor.RED, heroes=[a], minions=[]),
            TeamColor.BLUE: Team(color=TeamColor.BLUE, heroes=[b], minions=[]),
        },
        tie_breaker_team=TeamColor.RED,
    )


def test_coin_not_flipped_when_cross_team_winner_is_picked(cross_team_tie_state):
    state = cross_team_tie_state
    step = ResolveTieBreakerStep(tied_hero_ids=["A", "B"])

    result = step.resolve(state, {})

    # A (favored RED) is installed as the actor...
    assert state.current_actor_id == "A"
    assert result.is_finished
    # ...but the coin has NOT flipped yet — it flips after A's card resolves.
    assert state.tie_breaker_team == TeamColor.RED


def test_coin_flips_after_cross_team_winner_turn_resolves(cross_team_tie_state):
    state = cross_team_tie_state
    push_steps(state, [ResolveTieBreakerStep(tied_hero_ids=["A", "B"])])

    # A auto-wins and is prompted for their action.
    req = process_stack(state).input_request
    assert req["type"] == "CHOOSE_ACTION"
    assert req["player_id"] == "A"
    state.execution_stack[-1].pending_input = {"selection": "HOLD"}

    req = process_stack(state).input_request
    assert req["type"] == "CHOOSE_ACTION"  # ConfirmResolutionStep
    state.execution_stack[-1].pending_input = {"selection": "CONFIRM"}
    req = process_stack(state).input_request
    assert req is None

    # Now (after the full turn) the coin has flipped.
    assert state.tie_breaker_team == TeamColor.BLUE

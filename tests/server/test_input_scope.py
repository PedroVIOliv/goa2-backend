"""A 'simultaneous' per-hero request (UPGRADE_PHASE) may only be answered for
the submitting player's own hero, so one client cannot force another player's
upgrade choice."""

import pytest

from goa2.domain.input import InputRequestType, create_input_request
from goa2.server.errors import NotYourTurnError, validate_simultaneous_input_scope


def _upgrade_request():
    return create_input_request(
        request_type=InputRequestType.UPGRADE_PHASE,
        player_id="simultaneous",
        prompt="Upgrade",
        players={"hero_a": {"remaining": 1, "options": []}},
    )


def test_rejects_upgrade_for_another_hero():
    req = _upgrade_request()
    with pytest.raises(NotYourTurnError):
        validate_simultaneous_input_scope(req, {"hero_id": "hero_b", "card_id": "x"}, "hero_a")


def test_allows_upgrade_for_own_hero():
    req = _upgrade_request()
    # Should not raise.
    validate_simultaneous_input_scope(req, {"hero_id": "hero_a", "card_id": "x"}, "hero_a")


def test_ignores_non_simultaneous_requests():
    req = create_input_request(
        request_type=InputRequestType.SELECT_UNIT,
        player_id="hero_a",
        prompt="Pick",
        options=["minion_1"],
    )
    # Not a simultaneous request → no scope check, must not raise.
    validate_simultaneous_input_scope(req, {"hero_id": "hero_b"}, "hero_a")


def test_ignores_non_dict_selection():
    req = _upgrade_request()
    # A non-dict selection carries no hero_id to police; must not raise here.
    validate_simultaneous_input_scope(req, "SKIP", "hero_a")


def test_ignores_missing_request():
    validate_simultaneous_input_scope(None, {"hero_id": "hero_b"}, "hero_a")


def _team_state():
    """Two heroes on RED, one on BLUE."""
    from goa2.domain.board import Board
    from goa2.domain.models import Hero, Team, TeamColor
    from goa2.domain.state import GameState

    return GameState(
        board=Board(),
        teams={
            TeamColor.RED: Team(
                color=TeamColor.RED,
                heroes=[
                    Hero(id="hero_a", name="A", team=TeamColor.RED, deck=[]),
                    Hero(id="hero_b", name="B", team=TeamColor.RED, deck=[]),
                ],
                minions=[],
            ),
            TeamColor.BLUE: Team(
                color=TeamColor.BLUE,
                heroes=[Hero(id="hero_c", name="C", team=TeamColor.BLUE, deck=[])],
                minions=[],
            ),
        },
    )


def _team_request():
    return create_input_request(
        request_type=InputRequestType.SELECT_HEX,
        player_id="team:RED",
        prompt="Team RED, choose which blocked spawn point to resolve first.",
        options=[],
    )


def test_team_request_reaches_every_hero_on_that_team():
    """Every teammate must receive the payload, or nobody can answer it."""
    from goa2.server.visibility import input_request_for_viewer

    state, req = _team_state(), _team_request()

    assert input_request_for_viewer(req, state, "hero_a") is not None
    assert input_request_for_viewer(req, state, "hero_b") is not None
    assert input_request_for_viewer(req, state, "hero_c") is None
    assert input_request_for_viewer(req, state, None) is None


def test_team_request_names_every_teammate_as_awaited():
    from goa2.server.visibility import awaiting_input_hero_ids

    assert awaiting_input_hero_ids(_team_request(), _team_state()) == ["hero_a", "hero_b"]


def test_team_request_accepts_input_from_any_teammate():
    from goa2.server.errors import validate_input_turn

    state = _team_state()
    validate_input_turn("team:RED", "hero_a", state)
    validate_input_turn("team:RED", "hero_b", state)
    with pytest.raises(NotYourTurnError):
        validate_input_turn("team:RED", "hero_c", state)

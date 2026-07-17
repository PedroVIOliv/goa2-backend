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

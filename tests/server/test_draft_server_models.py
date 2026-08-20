from goa2.server.models import (
    CreateDraftRequest,
    DraftActionRequest,
    DraftViewResponse,
    JoinDraftRequest,
)


def test_create_request_defaults():
    req = CreateDraftRequest(host_name="Alice")
    assert req.map_name == "forgotten_island"
    assert req.game_type == "LONG"
    assert req.draft_mode == "sequential_ban_pick"
    assert req.cheats_enabled is False


def test_view_response_shape():
    resp = DraftViewResponse(draft={}, you=None)
    assert resp.draft == {} and resp.you is None and resp.game_token is None


def test_action_request():
    assert DraftActionRequest(hero="Arien").hero == "Arien"


def test_lobby_names_are_truncated_to_the_plaque_limit():
    """A lobby name must be the same string that later reaches the plaque."""
    long_name = "x" * 40
    assert JoinDraftRequest(display_name=long_name).display_name == "x" * 20
    assert CreateDraftRequest(host_name=long_name).host_name == "x" * 20


def test_lobby_names_are_stripped():
    assert JoinDraftRequest(display_name="  Tuck  ").display_name == "Tuck"


def test_blank_lobby_name_is_rejected():
    import pytest as _pytest
    from pydantic import ValidationError

    with _pytest.raises(ValidationError):
        JoinDraftRequest(display_name="   ")

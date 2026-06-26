from goa2.server.models import (
    CreateDraftRequest,
    DraftActionRequest,
    DraftViewResponse,
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

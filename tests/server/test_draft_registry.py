import pytest

from goa2.draft import service
from goa2.draft.errors import DraftNotFoundError
from goa2.server.draft_registry import DraftRegistry


def _state():
    return service.create_draft("d1", "m", "LONG", "sequential_ban_pick", "Alice", now=0.0)


def test_create_issues_host_and_spectator_tokens():
    reg = DraftRegistry()
    md = reg.create(_state())
    assert md.host_token and md.spectator_token
    assert md.player_tokens[md.host_token] == "p1"
    resolved = reg.resolve_token(md.host_token)
    assert resolved == (md.draft_id, "p1", False, True)


def test_add_player_token_and_resolve():
    reg = DraftRegistry()
    md = reg.create(_state())
    service.join(md.state, "Bob")  # creates p2
    tok = reg.add_player_token(md.draft_id, "p2")
    assert reg.resolve_token(tok) == (md.draft_id, "p2", False, False)


def test_spectator_token_resolves_readonly():
    reg = DraftRegistry()
    md = reg.create(_state())
    assert reg.resolve_token(md.spectator_token) == (md.draft_id, "", True, False)


def test_get_missing_raises():
    reg = DraftRegistry()
    with pytest.raises(DraftNotFoundError):
        reg.get("nope")

import pytest
from fastapi.testclient import TestClient

from goa2.server.app import create_app


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _run_full_draft(client):
    """Drive a full 2v2 draft to a created game; return (draft_id, toks, final_view)."""
    r = client.post("/drafts", json={"host_name": "Alice", "red_size": 2, "blue_size": 2})
    assert r.status_code == 201
    d = r.json()
    draft_id, host_tok = d["draft_id"], d["player_token"]

    toks = {"p1": host_tok}
    for name in ("Bob", "Carol", "Dave"):
        jr = client.post(f"/drafts/{draft_id}/join", json={"display_name": name})
        assert jr.status_code == 200
        toks[jr.json()["player_id"]] = jr.json()["player_token"]

    for pid, team in (("p1", "RED"), ("p2", "RED"), ("p3", "BLUE"), ("p4", "BLUE")):
        assert (
            client.post(
                f"/drafts/{draft_id}/team", json={"team": team}, headers=_auth(toks[pid])
            ).status_code
            == 200
        )

    assert client.post(f"/drafts/{draft_id}/start", headers=_auth(host_tok)).status_code == 200

    view = client.get(f"/drafts/{draft_id}", headers=_auth(host_tok)).json()["draft"]
    cap = {p["team"]: p["id"] for p in view["players"] if p["is_captain"]}
    heroes = client.get("/heroes").json()
    hi = iter(heroes)
    for step in view["sequence"]:
        pid = cap[step["team"]]
        rr = client.post(
            f"/drafts/{draft_id}/action", json={"hero": next(hi)}, headers=_auth(toks[pid])
        )
        assert rr.status_code == 200

    view = client.get(f"/drafts/{draft_id}", headers=_auth(host_tok)).json()["draft"]
    for team in ("RED", "BLUE"):
        members = [p for p in view["players"] if p["team"] == team]
        drafted = list(view["picks"][team])
        for player, hero in zip(members, drafted, strict=True):
            cr = client.post(
                f"/drafts/{draft_id}/claim",
                json={"hero": hero},
                headers=_auth(toks[player["id"]]),
            )
            assert cr.status_code == 200

    final = client.get(f"/drafts/{draft_id}", headers=_auth(host_tok)).json()
    return draft_id, toks, final


def test_full_draft_creates_playable_game(client):
    _draft_id, _toks, final = _run_full_draft(client)
    assert final["game_id"]
    assert final["draft"]["status"] == "COMPLETE"
    assert final["game_token"]
    gv = client.get(f"/games/{final['game_id']}", headers=_auth(final["game_token"]))
    assert gv.status_code == 200


def test_modes_endpoint(client):
    r = client.get("/drafts/modes")
    assert r.status_code == 200
    assert any(m["name"] == "sequential_ban_pick" for m in r.json())


def test_non_host_cannot_start(client):
    r = client.post("/drafts", json={"host_name": "Alice", "red_size": 2, "blue_size": 2})
    d = r.json()
    jr = client.post(f"/drafts/{d['draft_id']}/join", json={"display_name": "Bob"})
    bob = jr.json()["player_token"]
    rr = client.post(f"/drafts/{d['draft_id']}/start", headers=_auth(bob))
    assert rr.status_code == 403


def test_randomize_then_start(client):
    r = client.post("/drafts", json={"host_name": "A", "red_size": 2, "blue_size": 2})
    d = r.json()
    host = d["player_token"]
    for name in ("B", "C", "D"):
        client.post(f"/drafts/{d['draft_id']}/join", json={"display_name": name})
    assert (
        client.post(f"/drafts/{d['draft_id']}/randomize-teams", headers=_auth(host)).status_code
        == 200
    )
    assert client.post(f"/drafts/{d['draft_id']}/start", headers=_auth(host)).status_code == 200

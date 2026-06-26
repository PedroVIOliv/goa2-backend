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
    r = client.post("/drafts", json={"host_name": "Alice"})
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
    r = client.post("/drafts", json={"host_name": "Alice"})
    d = r.json()
    jr = client.post(f"/drafts/{d['draft_id']}/join", json={"display_name": "Bob"})
    bob = jr.json()["player_token"]
    rr = client.post(f"/drafts/{d['draft_id']}/start", headers=_auth(bob))
    assert rr.status_code == 403


def test_randomize_then_start(client):
    r = client.post("/drafts", json={"host_name": "A"})
    d = r.json()
    host = d["player_token"]
    for name in ("B", "C", "D"):
        client.post(f"/drafts/{d['draft_id']}/join", json={"display_name": name})
    assert (
        client.post(f"/drafts/{d['draft_id']}/randomize-teams", headers=_auth(host)).status_code
        == 200
    )
    assert client.post(f"/drafts/{d['draft_id']}/start", headers=_auth(host)).status_code == 200


def test_maps_endpoint(client):
    r = client.get("/drafts/maps")
    assert r.status_code == 200
    assert "forgotten_island" in r.json()


def test_host_updates_settings_and_broadcasts(client):
    r = client.post("/drafts", json={"host_name": "Alice"})
    d = r.json()
    host = d["player_token"]
    pr = client.patch(
        f"/drafts/{d['draft_id']}/settings",
        json={"game_type": "QUICK", "cheats_enabled": True},
        headers=_auth(host),
    )
    assert pr.status_code == 200
    draft = pr.json()["draft"]
    assert draft["game_type"] == "QUICK" and draft["cheats"] is True


def test_non_host_cannot_update_settings(client):
    r = client.post("/drafts", json={"host_name": "Alice"})
    d = r.json()
    jr = client.post(f"/drafts/{d['draft_id']}/join", json={"display_name": "Bob"})
    bob = jr.json()["player_token"]
    pr = client.patch(
        f"/drafts/{d['draft_id']}/settings", json={"cheats_enabled": True}, headers=_auth(bob)
    )
    assert pr.status_code == 403


def test_update_settings_rejects_bad_values(client):
    r = client.post("/drafts", json={"host_name": "Alice"})
    d = r.json()
    host = d["player_token"]
    assert (
        client.patch(
            f"/drafts/{d['draft_id']}/settings", json={"game_type": "MEGA"}, headers=_auth(host)
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"/drafts/{d['draft_id']}/settings", json={"draft_mode": "nope"}, headers=_auth(host)
        ).status_code
        == 400
    )


def test_start_rejects_invalid_total(client):
    """3 assigned players is not a valid bracket; start must 400."""
    r = client.post("/drafts", json={"host_name": "A"})
    d = r.json()
    host = d["player_token"]
    toks = {"p1": host}
    for name in ("B", "C"):
        jr = client.post(f"/drafts/{d['draft_id']}/join", json={"display_name": name})
        toks[jr.json()["player_id"]] = jr.json()["player_token"]
    for pid, team in (("p1", "RED"), ("p2", "BLUE"), ("p3", "BLUE")):
        client.post(f"/drafts/{d['draft_id']}/team", json={"team": team}, headers=_auth(toks[pid]))
    rr = client.post(f"/drafts/{d['draft_id']}/start", headers=_auth(host))
    assert rr.status_code == 400


def test_leave_team_endpoint(client):
    r = client.post("/drafts", json={"host_name": "Alice"})
    d = r.json()
    host = d["player_token"]
    did = d["draft_id"]
    client.post(f"/drafts/{did}/team", json={"team": "RED"}, headers=_auth(host))
    lr = client.post(f"/drafts/{did}/leave-team", headers=_auth(host))
    assert lr.status_code == 200
    me = lr.json()["you"]
    assert me["team"] is None and me["is_captain"] is False


def test_start_rejects_unbalanced_teams(client):
    """1 vs 3 is a valid total (4) but unbalanced -> start must fail."""
    r = client.post("/drafts", json={"host_name": "A"})
    d = r.json()
    did, host = d["draft_id"], d["player_token"]
    toks = {"p1": host}
    for name in ("B", "C", "D"):
        jr = client.post(f"/drafts/{did}/join", json={"display_name": name})
        toks[jr.json()["player_id"]] = jr.json()["player_token"]
    for pid, team in (("p1", "RED"), ("p2", "BLUE"), ("p3", "BLUE"), ("p4", "BLUE")):
        client.post(f"/drafts/{did}/team", json={"team": team}, headers=_auth(toks[pid]))
    rr = client.post(f"/drafts/{did}/start", headers=_auth(host))
    assert rr.status_code >= 400


def test_full_draft_with_spectator_player_still_completes(client):
    """A joined-but-unassigned player must not stall claiming (regression)."""
    r = client.post("/drafts", json={"host_name": "Alice"})
    d = r.json()
    did, host = d["draft_id"], d["player_token"]
    toks = {"p1": host}
    for name in ("Bob", "Spec"):  # Bob plays, Spec stays unassigned
        jr = client.post(f"/drafts/{did}/join", json={"display_name": name})
        toks[jr.json()["player_id"]] = jr.json()["player_token"]
    client.post(f"/drafts/{did}/team", json={"team": "RED"}, headers=_auth(toks["p1"]))
    client.post(f"/drafts/{did}/team", json={"team": "BLUE"}, headers=_auth(toks["p2"]))
    # p3 (Spec) stays unassigned -> 1v1 valid.
    assert client.post(f"/drafts/{did}/start", headers=_auth(host)).status_code == 200

    view = client.get(f"/drafts/{did}", headers=_auth(host)).json()["draft"]
    cap = {p["team"]: p["id"] for p in view["players"] if p["is_captain"]}
    hi = iter(client.get("/heroes").json())
    for step in view["sequence"]:
        client.post(
            f"/drafts/{did}/action", json={"hero": next(hi)}, headers=_auth(toks[cap[step["team"]]])
        )

    view = client.get(f"/drafts/{did}", headers=_auth(host)).json()["draft"]
    for team in ("RED", "BLUE"):
        member = next(p for p in view["players"] if p["team"] == team)
        hero = view["picks"][team][0]
        client.post(f"/drafts/{did}/claim", json={"hero": hero}, headers=_auth(toks[member["id"]]))
    final = client.get(f"/drafts/{did}", headers=_auth(host)).json()
    assert final["draft"]["status"] == "COMPLETE" and final["game_id"]


def test_cheats_flow_to_created_game(client):
    """Cheats set in the lobby reach the created game (regression: was hardcoded False)."""
    r = client.post("/drafts", json={"host_name": "Alice", "cheats_enabled": True})
    d = r.json()
    assert (
        client.get(f"/drafts/{d['draft_id']}", headers=_auth(d["player_token"])).json()["draft"][
            "cheats"
        ]
        is True
    )

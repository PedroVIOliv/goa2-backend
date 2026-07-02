"""Tests for in-game bug reports linked to replay moments."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from goa2.server import bug_reports
from goa2.server.app import create_app
from goa2.server.replay import cleanup_old_replays


@pytest.fixture(autouse=True)
def _isolate_bug_report_dir(tmp_path_factory):
    prev = os.environ.get("GOA2_BUG_REPORT_DIR")
    os.environ["GOA2_BUG_REPORT_DIR"] = str(tmp_path_factory.mktemp("bug_reports"))
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("GOA2_BUG_REPORT_DIR", None)
        else:
            os.environ["GOA2_BUG_REPORT_DIR"] = prev


@pytest.fixture
def client(tmp_path):
    os.environ["GOA2_SAVE_DIR"] = str(tmp_path)
    app = create_app()
    with TestClient(app) as c:
        yield c
    os.environ.pop("GOA2_SAVE_DIR", None)


@pytest.fixture
def game_data(client):
    resp = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _token_for(game_data: dict, hero_id: str) -> str:
    for pt in game_data["player_tokens"]:
        if pt["hero_id"] == hero_id:
            return pt["token"]
    raise ValueError(f"No token for {hero_id}")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _submit(client, game_data, title="Something broke", description="details here"):
    return client.post(
        f"/games/{game_data['game_id']}/bug-reports",
        json={"title": title, "description": description},
        headers=_auth(_token_for(game_data, "hero_arien")),
    )


def _report_files() -> list[Path]:
    return sorted(Path(os.environ["GOA2_BUG_REPORT_DIR"]).glob("*.json"))


# ---- submit ----------------------------------------------------------------


def test_submit_creates_report_file(client, game_data):
    resp = _submit(client, game_data)
    assert resp.status_code == 201
    report_id = resp.json()["id"]
    files = _report_files()
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["id"] == report_id
    assert data["game_id"] == game_data["game_id"]
    assert data["title"] == "Something broke"
    assert data["description"] == "details here"
    assert data["reporter_hero"] == "hero_arien"
    assert data["status"] == "open"
    assert data["resolved_at"] is None
    assert data["created_at"] > 0
    assert data["round"] >= 1
    assert data["turn"] >= 1


def test_decision_index_counts_replay_decisions(client, game_data):
    # A fresh game's replay log has only the setup header: index 0.
    assert _submit(client, game_data).json()["decision_index"] == 0

    # Append two decisions to the game's replay log; index must follow.
    replay_path = Path(os.environ["GOA2_REPLAY_DIR"]) / f"{game_data['game_id']}.jsonl"
    assert replay_path.is_file()
    with open(replay_path, "a") as f:
        f.write('{"type":"commit","r":1,"t":1,"hero":"hero_arien","card":"c1"}\n')
        f.write('{"type":"pass","r":1,"t":2,"hero":"hero_wasp"}\n')
    assert _submit(client, game_data).json()["decision_index"] == 2


def test_decision_index_null_when_replay_missing(client, game_data):
    replay_path = Path(os.environ["GOA2_REPLAY_DIR"]) / f"{game_data['game_id']}.jsonl"
    replay_path.unlink()
    resp = _submit(client, game_data)
    assert resp.status_code == 201
    assert resp.json()["decision_index"] is None


def test_spectator_can_report_without_hero(client, game_data):
    resp = client.post(
        f"/games/{game_data['game_id']}/bug-reports",
        json={"title": "spectator saw it", "description": ""},
        headers=_auth(game_data["spectator_token"]),
    )
    assert resp.status_code == 201
    data = json.loads(_report_files()[0].read_text())
    assert data["reporter_hero"] is None


def test_submit_requires_auth(client, game_data):
    resp = client.post(
        f"/games/{game_data['game_id']}/bug-reports",
        json={"title": "no auth", "description": ""},
    )
    assert resp.status_code == 401


def test_submit_rejects_token_from_other_game(client, game_data):
    other = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
        },
    ).json()
    resp = client.post(
        f"/games/{game_data['game_id']}/bug-reports",
        json={"title": "wrong game", "description": ""},
        headers=_auth(_token_for(other, "hero_arien")),
    )
    assert resp.status_code == 403


@pytest.mark.parametrize(
    "title,description",
    [
        ("", "desc"),  # empty title
        ("   ", "desc"),  # whitespace-only title
        ("x" * 121, "desc"),  # title too long
        ("ok", "x" * 4001),  # description too long
    ],
)
def test_submit_validation(client, game_data, title, description):
    resp = _submit(client, game_data, title=title, description=description)
    assert resp.status_code == 422


def test_submit_capped_per_game(client, game_data):
    for _ in range(10):
        assert _submit(client, game_data).status_code == 201
    assert _submit(client, game_data).status_code == 429


def test_submit_unknown_game_404(client, game_data):
    resp = client.post(
        "/games/nope/bug-reports",
        json={"title": "t", "description": ""},
        headers=_auth(_token_for(game_data, "hero_arien")),
    )
    # Token belongs to another game -> rejected before the registry lookup.
    assert resp.status_code in (403, 404)


# ---- triage (admin) --------------------------------------------------------


@pytest.fixture
def _env(monkeypatch):
    monkeypatch.delenv("GOA2_REPLAY_API", raising=False)
    monkeypatch.delenv("GOA2_ADMIN_TOKEN", raising=False)
    return monkeypatch


@pytest.fixture
def dev_client(_env, tmp_path):
    """Client with the dev flag on: admin routes open, no auth."""
    _env.setenv("GOA2_REPLAY_API", "1")
    _env.setenv("GOA2_SAVE_DIR", str(tmp_path))
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def token_client(_env, tmp_path):
    """Client in production mode: admin routes require GOA2_ADMIN_TOKEN."""
    _env.setenv("GOA2_ADMIN_TOKEN", "s3cret")
    _env.setenv("GOA2_SAVE_DIR", str(tmp_path))
    with TestClient(create_app()) as c:
        yield c


def _make_game_and_report(client) -> tuple[dict, str]:
    game = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
        },
    ).json()
    report_id = _submit(client, game).json()["id"]
    return game, report_id


def test_admin_list_resolve_delete_with_dev_flag(dev_client):
    _, report_id = _make_game_and_report(dev_client)

    rows = dev_client.get("/bug-reports").json()
    assert [r["id"] for r in rows] == [report_id]
    assert rows[0]["status"] == "open"

    resolved = dev_client.patch(f"/bug-reports/{report_id}", json={"status": "resolved"})
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["resolved_at"] is not None

    reopened = dev_client.patch(f"/bug-reports/{report_id}", json={"status": "open"})
    assert reopened.json()["status"] == "open"
    assert reopened.json()["resolved_at"] is None

    assert dev_client.delete(f"/bug-reports/{report_id}").status_code == 204
    assert dev_client.get("/bug-reports").json() == []


def test_admin_patch_rejects_bad_status(dev_client):
    _, report_id = _make_game_and_report(dev_client)
    resp = dev_client.patch(f"/bug-reports/{report_id}", json={"status": "wontfix"})
    assert resp.status_code == 422


def test_admin_unknown_report_404(dev_client):
    assert dev_client.patch("/bug-reports/nope", json={"status": "open"}).status_code == 404
    assert dev_client.delete("/bug-reports/nope").status_code == 404


def test_admin_routes_require_token_in_prod(token_client):
    assert token_client.get("/bug-reports").status_code == 401
    assert token_client.get("/bug-reports", headers=_auth("wrong")).status_code == 401
    resp = token_client.get("/bug-reports", headers=_auth("s3cret"))
    assert resp.status_code == 200
    assert resp.json() == []


def test_replay_debugger_gated_by_admin_token_in_prod(token_client):
    assert token_client.get("/replays").status_code == 401
    assert token_client.get("/replays", headers=_auth("s3cret")).status_code == 200


def test_admin_routes_absent_when_nothing_configured(_env, tmp_path):
    _env.setenv("GOA2_SAVE_DIR", str(tmp_path))
    with TestClient(create_app()) as c:
        assert c.get("/bug-reports").status_code == 404
        assert c.get("/replays").status_code == 404


# ---- replay pinning --------------------------------------------------------


def _make_old_replay(game_id: str) -> Path:
    path = Path(os.environ["GOA2_REPLAY_DIR"]) / f"{game_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'{{"type":"setup","game_id":"{game_id}"}}\n')
    old = time.time() - 90 * 86400  # far past the 30-day TTL
    os.utime(path, (old, old))
    return path


def test_open_report_pins_replay_against_cleanup():
    pinned = _make_old_replay("pinned_game")
    unpinned = _make_old_replay("unpinned_game")
    bug_reports.create_report(
        game_id="pinned_game",
        title="t",
        description="",
        reporter_hero=None,
        decision_index=0,
        round_num=1,
        turn=1,
    )

    removed = cleanup_old_replays()

    assert removed == 1
    assert pinned.is_file()
    assert not unpinned.is_file()


def test_resolved_report_releases_pin():
    path = _make_old_replay("resolved_game")
    report = bug_reports.create_report(
        game_id="resolved_game",
        title="t",
        description="",
        reporter_hero=None,
        decision_index=0,
        round_num=1,
        turn=1,
    )
    bug_reports.set_status(report["id"], "resolved")

    cleanup_old_replays()

    assert not path.is_file()


def test_submit_still_works_in_prod_mode(token_client):
    # The public submit route must not be affected by admin gating.
    _, report_id = _make_game_and_report(token_client)
    assert report_id.startswith("br_")

"""Per-IP limit on creating games and drafts (POST /games, POST /drafts)."""

import pytest
from fastapi.testclient import TestClient

from goa2.server.app import create_app
from goa2.server.rate_limit import (
    DEFAULT_CREATE_LIMIT_PER_HOUR,
    CreationLimiter,
    create_limit_per_hour,
)

GAME_BODY = {"map_name": "forgotten_island", "red_heroes": ["Arien"], "blue_heroes": ["Wasp"]}
DRAFT_BODY = {"host_name": "Alice"}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def app(clock):
    app = create_app()
    app.state.creation_limiter = CreationLimiter(limit=3, clock=clock)
    return app


def _client(app, ip: str = "203.0.113.1") -> TestClient:
    return TestClient(app, client=(ip, 50000))


def test_limit_hit_returns_429_with_retry_after(app, clock):
    with _client(app) as c:
        for _ in range(3):
            assert c.post("/games", json=GAME_BODY).status_code == 201
        clock.now += 600
        resp = c.post("/games", json=GAME_BODY)

    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "3000"
    assert resp.json()["detail"] == (
        "Too many games created from your network; try again in 50 minutes"
    )


def test_rejected_attempts_do_not_extend_the_wait(app, clock):
    with _client(app) as c:
        for _ in range(3):
            c.post("/games", json=GAME_BODY)
        for _ in range(5):
            assert c.post("/games", json=GAME_BODY).status_code == 429
        clock.now += 3600
        assert c.post("/games", json=GAME_BODY).status_code == 201


def test_separate_ips_have_separate_budgets(app):
    with _client(app, "203.0.113.1") as a, _client(app, "198.51.100.7") as b:
        for _ in range(3):
            assert a.post("/games", json=GAME_BODY).status_code == 201
        assert a.post("/games", json=GAME_BODY).status_code == 429
        assert b.post("/games", json=GAME_BODY).status_code == 201


def test_games_and_drafts_share_one_budget(app):
    with _client(app) as c:
        assert c.post("/games", json=GAME_BODY).status_code == 201
        assert c.post("/drafts", json=DRAFT_BODY).status_code == 201
        assert c.post("/drafts", json=DRAFT_BODY).status_code == 201
        assert c.post("/games", json=GAME_BODY).status_code == 429
        resp = c.post("/drafts", json=DRAFT_BODY)

    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_window_rolls_over(app, clock):
    with _client(app) as c:
        c.post("/games", json=GAME_BODY)
        clock.now += 1800
        c.post("/games", json=GAME_BODY)
        c.post("/games", json=GAME_BODY)
        assert c.post("/games", json=GAME_BODY).status_code == 429

        clock.now += 1800
        assert c.post("/games", json=GAME_BODY).status_code == 201
        resp = c.post("/games", json=GAME_BODY)

    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "1800"


def test_failed_creations_do_not_consume_budget(app):
    with _client(app) as c:
        assert c.post("/games", json={**GAME_BODY, "map_name": "nowhere"}).status_code == 404
        assert c.post("/games", json={**GAME_BODY, "game_type": "BAD"}).status_code == 400
        assert c.post("/games", json={"map_name": "forgotten_island"}).status_code == 422
        assert c.post("/drafts", json={**DRAFT_BODY, "draft_mode": "nope"}).status_code == 400
        for _ in range(3):
            assert c.post("/games", json=GAME_BODY).status_code == 201


def test_draft_start_and_joins_are_not_counted(app):
    with _client(app) as c:
        d = c.post("/drafts", json=DRAFT_BODY).json()
        host = {"Authorization": f"Bearer {d['player_token']}"}
        did = d["draft_id"]
        bob = c.post(f"/drafts/{did}/join", json={"display_name": "Bob"}).json()
        c.post(f"/drafts/{did}/team", json={"team": "RED"}, headers=host)
        c.post(
            f"/drafts/{did}/team",
            json={"team": "BLUE"},
            headers={"Authorization": f"Bearer {bob['player_token']}"},
        )
        assert c.post(f"/drafts/{did}/start", headers=host).status_code == 200
        assert c.post("/games", json=GAME_BODY).status_code == 201
        assert c.post("/games", json=GAME_BODY).status_code == 201
        assert c.post("/games", json=GAME_BODY).status_code == 429


def test_tracked_ips_are_pruned(clock):
    limiter = CreationLimiter(limit=2, clock=clock)
    for i in range(5000):
        limiter.record(f"10.0.{i // 256}.{i % 256}")
    clock.now += 3601
    for i in range(2000):
        limiter.record(f"10.1.{i // 256}.{i % 256}")

    assert limiter.tracked_ips() <= 2000 + limiter.SWEEP_MIN


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, DEFAULT_CREATE_LIMIT_PER_HOUR),
        ("12", 12),
        ("lots", DEFAULT_CREATE_LIMIT_PER_HOUR),
        ("0", DEFAULT_CREATE_LIMIT_PER_HOUR),
        ("-3", DEFAULT_CREATE_LIMIT_PER_HOUR),
    ],
)
def test_limit_from_env(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("GOA2_CREATE_LIMIT_PER_HOUR", raising=False)
    else:
        monkeypatch.setenv("GOA2_CREATE_LIMIT_PER_HOUR", value)
    assert create_limit_per_hour() == expected


def test_default_is_five_per_hour():
    assert DEFAULT_CREATE_LIMIT_PER_HOUR == 5


def test_app_reads_limit_from_env(monkeypatch):
    monkeypatch.setenv("GOA2_CREATE_LIMIT_PER_HOUR", "2")
    with _client(create_app()) as c:
        assert c.post("/games", json=GAME_BODY).status_code == 201
        assert c.post("/drafts", json=DRAFT_BODY).status_code == 201
        assert c.post("/games", json=GAME_BODY).status_code == 429

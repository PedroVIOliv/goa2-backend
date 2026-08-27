"""Player-facing replay-share minting contract."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool

import pytest
from fastapi.testclient import TestClient

from goa2.domain.models import GamePhase, TeamColor
from goa2.domain.types import HeroID
from goa2.server import share_mint, shares
from goa2.server.app import create_app
from goa2.server.share_bake import bake_replay_share


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _player_token(game_data: dict, hero_id: str = "hero_arien") -> str:
    return next(row["token"] for row in game_data["player_tokens"] if row["hero_id"] == hero_id)


def _create_game(client: TestClient) -> dict:
    response = client.post(
        "/games",
        json={
            "map_name": "forgotten_island",
            "red_heroes": ["Arien"],
            "blue_heroes": ["Wasp"],
            "game_type": "QUICK",
        },
    )
    assert response.status_code == 201
    return response.json()


def _finish_recorded_replay(client: TestClient, game_data: dict) -> None:
    game = client.app.state.registry.get(game_data["game_id"])
    recorder = game.replay_recorder
    assert recorder is not None

    for team in game.session.state.teams.values():
        for hero in team.heroes:
            card = hero.hand[0]
            recorder.record_commit(
                hero.id, card.id, game.session.state.round, game.session.state.turn
            )
            game.session.commit_card(HeroID(hero.id), card)

    recorder.record_override(
        {
            "type": "ov_patch",
            "r": game.session.state.round,
            "t": game.session.state.turn,
            "hero": "hero_arien",
            "op": "set_life_counters",
            "args": {"team": "BLUE", "value": 0},
            "voters": ["hero_arien", "hero_wasp"],
        }
    )
    game.session.state.phase = GamePhase.GAME_OVER
    game.session.state.winner = TeamColor.RED


@pytest.fixture
def client(monkeypatch):
    async def run_inline(fn, *args):
        return fn(*args)

    monkeypatch.setattr(share_mint, "run_heavy", run_inline)
    with TestClient(create_app()) as test_client:
        yield test_client


def test_player_can_mint_finished_game_and_second_mint_is_idempotent(client):
    game = _create_game(client)
    _finish_recorded_replay(client, game)
    headers = _auth(_player_token(game))

    first = client.post(f"/games/{game['game_id']}/share", headers=headers)
    second = client.post(f"/games/{game['game_id']}/share", headers=headers)

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert first.json()["url"] == f"/shared/{first.json()['token']}"
    assert len(shares.list_shares()) == 1


def test_player_cannot_mint_unfinished_game_without_dispatching_heavy_work(client, monkeypatch):
    game = _create_game(client)

    async def unexpected_run_heavy(*args):
        pytest.fail("unfinished live game reached the heavy worker")

    monkeypatch.setattr(share_mint, "run_heavy", unexpected_run_heavy)

    response = client.post(f"/games/{game['game_id']}/share", headers=_auth(_player_token(game)))

    assert response.status_code == 409
    assert "finished" in response.json()["detail"]


def test_token_for_another_game_cannot_mint(client):
    first = _create_game(client)
    second = _create_game(client)

    response = client.post(f"/games/{second['game_id']}/share", headers=_auth(_player_token(first)))

    assert response.status_code == 403


def test_spectator_cannot_mint(client):
    game = _create_game(client)

    response = client.post(
        f"/games/{game['game_id']}/share", headers=_auth(game["spectator_token"])
    )

    assert response.status_code == 403


def test_broken_share_worker_returns_500(client, monkeypatch):
    game = _create_game(client)
    _finish_recorded_replay(client, game)

    async def broken_worker(*args):
        raise BrokenProcessPool("worker died")

    monkeypatch.setattr(share_mint, "run_heavy", broken_worker)

    response = client.post(f"/games/{game['game_id']}/share", headers=_auth(_player_token(game)))

    assert response.status_code == 500
    assert "bake process died" in response.json()["detail"]


def test_concurrent_player_mints_bake_once_through_shared_pool(client, monkeypatch):
    game = _create_game(client)
    _finish_recorded_replay(client, game)
    headers = _auth(_player_token(game))
    calls = []
    replay_loads = []
    real_load_replay = share_mint.load_replay

    def counted_load_replay(path):
        replay_loads.append(path)
        return real_load_replay(path)

    async def counted_run_heavy(fn, *args):
        calls.append((fn, args))
        await asyncio.sleep(0.05)  # let the second request reach the per-game lock
        return fn(*args)

    monkeypatch.setattr(share_mint, "run_heavy", counted_run_heavy)
    monkeypatch.setattr(share_mint, "load_replay", counted_load_replay)

    def mint():
        return client.post(f"/games/{game['game_id']}/share", headers=headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(mint)
        second_future = pool.submit(mint)
        first, second = first_future.result(), second_future.result()

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert len(calls) == 1
    assert len(replay_loads) == 1
    assert calls[0][0] is bake_replay_share
    assert len(shares.list_shares()) == 1

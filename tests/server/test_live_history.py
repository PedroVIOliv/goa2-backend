"""Captured views, effective branches, durable groups and authenticated reads."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from pathlib import Path

import brotli
import pytest
from fastapi.testclient import TestClient

from goa2.domain.input import InputResponse
from goa2.domain.models import GamePhase
from goa2.domain.types import HeroID
from goa2.engine.handler import push_steps
from goa2.engine.steps import AskConfirmationStep
from goa2.server import history_backfill, live_history
from goa2.server.app import create_app
from goa2.server.history_backfill import build_history
from goa2.server.live_history import HistoryUnavailable, LiveHistory, canonical_views
from goa2.server.registry import GameRegistry
from goa2.server.replay import load_replay
from goa2.server.replay_codec import GroupBuilder, decode, encode, for_delivery, reconstruct


def views(value=0, phase="RESOLUTION", turn=1):
    public = {"view": {"phase": phase, "round": 1, "turn": turn, "value": value}, "winner": None}
    return {"spectator": public, "hero_arien": {**deepcopy(public), "private": "secret"}}


def test_codec_batch_incremental_roundtrip_and_boundaries():
    builder = GroupBuilder(0, {"items": [1, 2]}, max_patches=3)
    assert builder.append(1, {"items": [2]}) is None
    assert builder.append(2, {"items": [2]}) is None
    closed = builder.append(3, {"items": [], "new": True})
    assert reconstruct(closed, 1) == {"items": [2]}
    assert reconstruct(closed, 2) == {"items": [2]}
    assert reconstruct(builder.group, 3) == {"items": [], "new": True}
    restored = GroupBuilder.restore(decode(encode(closed)))
    assert restored.previous == {"items": [2]}
    assert restored.append(3, {"items": [3]}) is None
    # Returned documents and cached keyframes are independent.
    reconstruct(closed, 0)["items"].append(100)
    assert closed["keyframe"] == {"items": [1, 2]}
    stored = encode(closed)
    assert for_delivery(stored, accepts_brotli=True) == (stored, "br")
    import gzip

    assert json.loads(gzip.decompress(for_delivery(stored, accepts_brotli=False)[0])) == closed
    with pytest.raises(ValueError, match="outside"):
        reconstruct(closed, 4)
    with pytest.raises(ValueError, match="consecutive"):
        builder.append(8, {})
    with pytest.raises(ValueError, match="Invalid"):
        decode(brotli.compress(b"[]"))


def test_codec_size_budget_starts_new_keyframe():
    builder = GroupBuilder(0, {}, check_every=1, budget_multiple=0)
    assert builder.append(1, {"large": list(range(300))}) is not None
    assert builder.group["start"] == 1


def test_effective_planning_rollback_and_nested_rewind():
    history = LiveHistory()
    history.capture_views(views(0, "PLANNING"), 0)
    history.capture_views(views(1, "PLANNING"), 1)
    history.capture_views(views(2, "PLANNING"), 2, {"type": "uncommit"})
    assert history.active == [2]
    history.capture_views(views(3), 3, anchor="anchor")
    anchor = history.active[-1]
    history.capture_views(views(4), 4, anchor="anchor")
    history.capture_views(views(5), 5, anchor="anchor")
    history.capture_views(views(3), 6, {"type": "rollback"}, anchor="anchor")
    assert history.active == [2, 6]
    assert history.anchors["anchor"] == 6
    assert anchor not in history.active
    history.capture_views(views(7), 7, anchor="anchor")
    history.capture_views(views(3), 8, {"type": "rollback"}, anchor="anchor")
    assert history.active == [2, 8]
    history.capture_views(views(0, "PLANNING"), 9, {"type": "ov_rewind", "to": 0})
    assert history.active == [9]
    history.capture_views(views(7), 10, {"type": "ov_rewind", "to": 7})
    assert history.active[:-1] == [2, 6]
    assert history.reader().read(history.active[-1], "spectator")["view"]["value"] == 7
    assert len(history.records) == 11  # Audit captures remain intact.


def test_anchor_reanchor_dedup_and_capture_failure(monkeypatch):
    history = LiveHistory()
    history.capture_views(views(), 0, anchor="first")
    history.capture_views(views(1), 1, anchor="first")
    history.capture_views(views(1), 2, anchor="second")
    assert history.anchors["second"] == 1
    history.capture_views(views(2), 3, anchor="second")
    history.capture_views(views(1), 4, {"type": "rollback"}, anchor="second")
    assert history.active == [0, 3]  # The foreign-response boundary is retained.
    history.capture_views(views(0), 5, {"type": "rollback"}, anchor="unknown")
    assert history.active == [4]
    assert history.gaps
    monkeypatch.setattr(live_history, "canonical_views", lambda _: 1 / 0)
    history.capture_safely(None, 6)
    assert history.builder is None
    history.capture_views(views(6), 7)
    assert history.groups[-1]["start"] == 5


def test_storage_restore_orphans_gaps_and_read_isolation(tmp_path):
    history = LiveHistory(tmp_path)
    for count in range(12):
        history.capture_views(views(count), count)
    manifest = history.prepare_manifest()
    history.committed()
    (tmp_path / ("f" * 64 + ".br")).write_bytes(b"orphan")
    (tmp_path / "unfinished.tmp").write_bytes(b"partial")
    restored = LiveHistory.restore(tmp_path, manifest)
    assert not (tmp_path / "unfinished.tmp").exists()
    assert restored.reader().read(3, "spectator")["view"]["value"] == 3
    private = restored.reader().read(3, "hero_arien")
    private["view"]["value"] = 999
    assert restored.reader().read(3, "hero_arien")["view"]["value"] == 3
    assert "secret" not in json.dumps(restored.reader().read(3, "spectator"))
    restored.capture_views(views(12), 12)
    restored.prepare_manifest()
    restored.committed()
    assert restored.reader().read(12, "spectator")["view"]["value"] == 12
    with pytest.raises(HistoryUnavailable):
        restored.reader().read(10000, "spectator")
    with pytest.raises(HistoryUnavailable):
        LiveHistory.restore(tmp_path, {"format": -1})
    # A known-but-damaged tail cannot masquerade as a correct state.
    Path(tmp_path / restored.groups[-1]["file"]).write_bytes(b"corrupt")
    damaged = LiveHistory.restore(tmp_path, restored.prepare_manifest())
    assert damaged.gaps
    with pytest.raises(HistoryUnavailable):
        damaged.reader().read_all(0)


@pytest.fixture
def client_game():
    app = create_app()
    with TestClient(app) as client:
        data = client.post(
            "/games", json={"red_heroes": ["Arien"], "blue_heroes": ["Wasp"], "game_type": "QUICK"}
        ).json()
        yield client, app.state.registry, data


def auth(data, index=0):
    return {"Authorization": f"Bearer {data['player_tokens'][index]['token']}"}


def commit(client, data, index=0):
    headers = auth(data, index)
    view = client.get(f"/games/{data['game_id']}", headers=headers).json()["view"]
    hero_id = data["player_tokens"][index]["hero_id"]
    hero = next(h for team in view["teams"].values() for h in team["heroes"] if h["id"] == hero_id)
    card = hero["hand"][0]["id"]
    response = client.post(
        f"/games/{data['game_id']}/cards", headers=headers, json={"card_id": card}
    )
    assert response.status_code == 200, response.text
    return card


def test_api_auth_planning_invalidation_scoping_and_live_metadata(client_game):
    client, registry, data = client_game
    base = f"/games/{data['game_id']}/history"
    assert client.get(base).status_code == 401
    first = client.get(base, headers=auth(data)).json()
    initial = first["position_id"]
    card = commit(client, data)
    newer = client.get(base, headers=auth(data)).json()
    assert newer["total"] == 1
    assert newer["epoch"] > first["epoch"]
    assert client.get(base + f"/state?position_id={initial}", headers=auth(data)).status_code == 410
    assert client.get(base + "/state?position_id=9999", headers=auth(data)).status_code == 404
    assert (
        client.get(base + f"?revision={first['revision']}", headers=auth(data)).status_code == 409
    )
    position = newer["position_id"]
    own = client.get(base + f"/state?position_id={position}", headers=auth(data)).json()
    enemy = client.get(base + f"/state?position_id={position}", headers=auth(data, 1)).json()
    spectator_headers = {"Authorization": f"Bearer {data['spectator_token']}"}
    public = client.get(base + f"/state?position_id={position}", headers=spectator_headers).json()
    assert card in json.dumps(own)
    assert card not in json.dumps(enemy)
    assert card not in json.dumps(public)
    live = client.get(f"/games/{data['game_id']}", headers=auth(data)).json()
    assert live["history"]["position_id"] == position
    assert own["view"]["clock"] is None
    game = registry.get(data["game_id"])
    assert (
        game.history.metadata_for_view({**live["view"], "round": -1}, None)["position_id"] is None
    )


def test_api_groups_pagination_and_missing_frames(client_game):
    client, registry, data = client_game
    base = f"/games/{data['game_id']}/history"
    commit(client, data, 0)
    commit(client, data, 1)
    index = client.get(base, headers=auth(data)).json()
    ids = [p["position_id"] for p in index["positions"]]
    assert len(ids) >= 2
    for encoding in ("br", "gzip"):
        response = client.get(
            base + f"/frames?from_position_id={ids[0]}",
            headers={**auth(data), "Accept-Encoding": encoding},
        )
        assert response.status_code == 200
        assert response.headers["content-encoding"] == encoding
        group = response.json()
        assert [p["position_id"] for p in group["positions"]] == ids
        for offset, record_id in enumerate(ids):
            expected = client.get(
                base + f"/state?position_id={record_id}", headers=auth(data)
            ).json()
            assert reconstruct(group, offset)["view"] == expected["view"]
    page = client.get(base + f"?before_position_id={ids[-1]}&limit=1", headers=auth(data)).json()
    assert page["positions"][0]["position_id"] == ids[-2]
    assert client.get(base + "?limit=101", headers=auth(data)).status_code == 422
    assert (
        client.get(
            base + f"/frames?from_position_id={ids[0]}&limit=31", headers=auth(data)
        ).status_code
        == 422
    )
    game = registry.get(data["game_id"])
    # Remove backing state and invalidate the read cache: return an explicit gap.
    game.history.builder = None
    game.history.groups.clear()
    live_history._CACHE.clear()
    assert client.get(base + f"/state?position_id={ids[0]}", headers=auth(data)).status_code == 503


def test_restart_and_replay_backfill_use_shared_driver(client_game, tmp_path, monkeypatch):
    client, registry, data = client_game
    commit(client, data, 0)
    game = registry.get(data["game_id"])
    old_id = game.history.active[-1]
    count = len(game.history.records)
    setup, decisions = load_replay(str(game.replay_recorder.path))
    rebuilt = build_history(setup, decisions)
    assert rebuilt.latest_views == canonical_views(game.session)
    restored = GameRegistry(save_dir=registry._save_dir)
    assert restored.restore_all() == 1
    again = restored.get(game.game_id)
    assert again.history.active[-1] == old_id
    assert again.history.reader().read(old_id, "hero_arien") == game.history.reader().read(
        old_id, "hero_arien"
    )

    async def inline(fn, *args):
        return fn(*args)

    monkeypatch.setattr(history_backfill, "run_heavy", inline)
    # Simulate a legacy save, where the current state is the only baseline.
    legacy = LiveHistory()
    legacy.capture(game.session, len(decisions))
    legacy.backfill_status = "pending"
    game.history = legacy
    asyncio.run(history_backfill.ensure_backfill(game, registry))
    assert game.history.backfill_status == "complete"
    assert game.history.epoch > 0
    assert game.history.latest_views == canonical_views(game.session)
    assert game.history.records[-1]["position_id"] >= len(legacy.records)
    assert len(game.history.records) > count


@pytest.mark.parametrize(
    "before,after",
    [
        ({"a/b": {"~x": True}}, {"a/b": {"~x": 1}}),
        ({"items": [1, 2]}, {"items": [2, 1]}),
        ({"items": [1, 2]}, {"items": []}),
        ({"old": 1}, {"new": None}),
    ],
)
def test_codec_changed_subtrees_preserve_json_types_and_paths(before, after):
    import jsonpatch

    from goa2.server.replay_codec import make_patch

    actual = jsonpatch.apply_patch(before, make_patch(before, after))
    assert json.dumps(actual, sort_keys=True) == json.dumps(after, sort_keys=True)


def test_captured_views_are_frozen_and_match_standard_projection(client_game):
    from goa2.domain.views import build_view

    _client, registry, data = client_game
    game = registry.get(data["game_id"])
    captures = game.history.latest_views
    for viewer in captures:
        expected = build_view(
            game.session.state, for_hero_id=None if viewer == "spectator" else HeroID(viewer)
        )
        expected["clock"] = expected["starting_position"] = None
        assert expected == captures[viewer]["view"]
    frozen = deepcopy(captures)
    hero = game.session.state.get_hero("hero_arien")
    hero.gold += 10
    hero.hand[0].is_facedown = not hero.hand[0].is_facedown
    zone = next(iter(game.session.state.board.zones.values()))
    zone.neighbors.append("temporary-test-zone")
    assert captures == frozen


def test_real_rollback_segments_survive_restart(client_game):
    _client, registry, data = client_game
    game = registry.get(data["game_id"])
    state = game.session.state
    state.phase = GamePhase.RESOLUTION
    state.current_actor_id = HeroID("hero_arien")
    push_steps(
        state,
        [
            AskConfirmationStep(player_id="hero_arien", prompt="Before"),
            AskConfirmationStep(player_id="hero_wasp", prompt="Foreign", output_key="foreign_done"),
            AskConfirmationStep(player_id="hero_arien", prompt="After"),
            AskConfirmationStep(player_id="hero_arien", prompt="Last"),
        ],
    )
    result = game.session.advance()
    game.history.capture(game.session, 0)
    first_anchor = game.session.rollback_anchor_id
    for _ in range(3):
        player = result.input_request.player_id
        result = game.session.advance(
            InputResponse(request_id=result.input_request.id, selection="YES")
        )
        game.last_result = result
        game.replay_recorder.record_input(player, "YES", 1, 1)
        registry.save_game(game.game_id)
        if result.input_request.prompt == "After":
            safe_position = game.history.active[-1]
    abandoned = game.history.active[-1]
    assert game.session.rollback_anchor_id != first_anchor
    restored = GameRegistry(registry._save_dir)
    restored.restore_all()
    game = restored.get(game.game_id)
    anchor_id = game.session.rollback_anchor_id
    result = game.session.rollback()
    game.replay_recorder.record_rollback("hero_arien", 1, 1)
    restored.save_game(game.game_id)
    assert result.input_request.prompt == "After"
    assert game.session.rollback_anchor_id == anchor_id
    assert game.session.state.execution_context["foreign_done"] is True
    assert abandoned not in game.history.active
    assert safe_position not in game.history.active
    assert game.history.records[game.history.active[-1]]["kind"] == "rollback"
    assert len(game.history.active) == 4


def test_websocket_history_and_foreign_game_tokens(client_game):
    client, registry, data = client_game
    game_id = data["game_id"]
    token = data["player_tokens"][0]["token"]
    with client.websocket_connect(f"/games/{game_id}/ws?token={token}") as socket:
        first = socket.receive_json()
        assert first["type"] == "STATE_UPDATE"
        assert first["history"]["total"] == 1
        hero = registry.get(game_id).session.state.get_hero("hero_arien")
        socket.send_json({"type": "COMMIT_CARD", "card_id": hero.hand[0].id})
        assert socket.receive_json()["type"] == "ACTION_RESULT"
        update = socket.receive_json()
        assert update["history"]["epoch"] > first["history"]["epoch"]
        assert update["history"]["position_id"] != first["history"]["position_id"]
    other = client.post("/games", json={"red_heroes": ["Arien"], "blue_heroes": ["Wasp"]}).json()
    assert client.get(f"/games/{game_id}/history", headers=auth(other)).status_code == 403


def test_history_write_failure_keeps_last_committed_files_and_game_state(client_game, monkeypatch):
    client, registry, data = client_game
    game = registry.get(data["game_id"])
    committed = deepcopy(game.history.last_manifest)
    original = live_history._atomic_bytes

    def fail(*_):
        raise OSError("disk full")

    monkeypatch.setattr(live_history, "_atomic_bytes", fail)
    commit(client, data)
    persisted = json.loads((Path(registry._save_dir) / f"{game.game_id}.json").read_text())
    assert persisted["live_history"]["active"] == committed["active"]
    for group in committed["groups"]:
        assert (game.history.directory / group["file"]).is_file()
    assert game.history.gaps
    monkeypatch.setattr(live_history, "_atomic_bytes", original)
    registry.save_game(game.game_id)
    restored = GameRegistry(registry._save_dir)
    restored.restore_all()
    again = restored.get(game.game_id)
    assert again.history.latest_views == canonical_views(again.session)


def test_backfill_single_flight_cancellation_and_failure(client_game, monkeypatch):
    client, registry, data = client_game
    game = registry.get(data["game_id"])
    commit(client, data)
    game.history.backfill_status = "pending"
    calls = []

    async def scenario():
        entered, finish = asyncio.Event(), asyncio.Event()

        async def worker(fn, *args):
            if fn is build_history:
                calls.append(1)
            entered.set()
            await finish.wait()
            return fn(*args)

        monkeypatch.setattr(history_backfill, "run_heavy", worker)
        first = asyncio.create_task(history_backfill.ensure_backfill(game, registry))
        await entered.wait()
        second = asyncio.create_task(history_backfill.ensure_backfill(game, registry))
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        finish.set()
        await second

    asyncio.run(scenario())
    assert calls == [1]
    assert game.history.backfill_status == "complete"
    game.history.backfill_status = "pending"

    async def broken(*_):
        raise ValueError("engine drift")

    monkeypatch.setattr(history_backfill, "run_heavy", broken)
    asyncio.run(history_backfill.ensure_backfill(game, registry))
    assert game.history.backfill_status == "unavailable"
    assert game.history.reader().read(game.history.active[-1], "spectator")


def test_read_detects_concurrent_correction(client_game, monkeypatch):
    from goa2.server import routes_history

    _client, registry, data = client_game
    game = registry.get(data["game_id"])
    original = live_history.HistoryReader.read

    def correcting(reader, *args):
        body = original(reader, *args)
        game.history.epoch += 1
        return body

    monkeypatch.setattr(live_history.HistoryReader, "read", correcting)
    with pytest.raises(Exception) as exc:
        asyncio.run(
            routes_history._read(game, registry, "spectator", game.history.active[-1], 1, None)
        )
    assert exc.value.status_code == 409


def test_backfill_repairs_corrupt_groups_and_keeps_original_ids_reserved(client_game, monkeypatch):
    client, registry, data = client_game
    commit(client, data)
    game = registry.get(data["game_id"])
    old_count = len(game.history.records)
    # Remove both the on-disk tail and its in-memory builder, as after a crash.
    path = game.history.directory / game.history.groups[-1]["file"]
    path.write_bytes(b"broken")
    game.history.builder = None
    game.history.backfill_status = "pending"

    async def inline(fn, *args):
        return fn(*args)

    monkeypatch.setattr(history_backfill, "run_heavy", inline)
    asyncio.run(history_backfill.ensure_backfill(game, registry))
    assert game.history.backfill_status == "complete"
    assert min(game.history.active) >= old_count
    assert game.history.latest_views == canonical_views(game.session)
    assert game.history.gaps == []


def test_save_failure_restart_uses_old_manifest_and_removes_orphans(client_game, monkeypatch):
    from goa2.engine import persistence

    client, registry, data = client_game
    game = registry.get(data["game_id"])
    old_active = game.history.active.copy()
    original = persistence.save_game
    monkeypatch.setattr(
        persistence, "save_game", lambda **_: (_ for _ in ()).throw(OSError("save failed"))
    )
    commit(client, data)
    assert game.history.active != old_active
    monkeypatch.setattr(persistence, "save_game", original)
    restored = GameRegistry(registry._save_dir)
    restored.restore_all()
    again = restored.get(game.game_id)
    assert again.history.active == old_active
    assert not again.session.state.pending_inputs
    assert {p.name for p in again.history.directory.iterdir()} == {
        g["file"] for g in again.history.groups
    }


def test_unsupported_history_format_reserves_ids_and_backfills(client_game, monkeypatch):
    client, registry, data = client_game
    commit(client, data)
    game = registry.get(data["game_id"])
    old_count = len(game.history.records)
    path = Path(registry._save_dir) / f"{game.game_id}.json"
    save = json.loads(path.read_text())
    save["live_history"]["format"] = -1
    path.write_text(json.dumps(save))
    restored = GameRegistry(registry._save_dir)
    restored.restore_all()
    again = restored.get(game.game_id)
    assert min(again.history.active) >= old_count

    async def inline(fn, *args):
        return fn(*args)

    monkeypatch.setattr(history_backfill, "run_heavy", inline)
    asyncio.run(history_backfill.ensure_backfill(again, restored))
    assert again.history.backfill_status == "complete"
    assert again.history.latest_views == canonical_views(again.session)


def test_live_capture_during_backfill_merges_without_resimulation(client_game, monkeypatch):
    client, registry, data = client_game
    commit(client, data)
    game = registry.get(data["game_id"])
    game.history.backfill_status = "pending"
    calls = []

    async def append_during_worker(fn, *args):
        result = fn(*args)
        if fn is build_history:
            calls.append(1)
            game.session.state.get_hero("hero_arien").gold += 3
            game.replay_recorder.record_cheat_gold("hero_arien", 3, 1, 1)
        return result

    monkeypatch.setattr(history_backfill, "run_heavy", append_during_worker)
    asyncio.run(history_backfill.ensure_backfill(game, registry))
    assert calls == [1]
    assert game.history.backfill_status == "complete"
    assert game.history.latest_views == canonical_views(game.session)


def test_worker_payload_can_cross_process_boundary(client_game):
    import pickle

    _client, registry, data = client_game
    game = registry.get(data["game_id"])
    setup, decisions = load_replay(str(game.replay_recorder.path))
    rebuilt = pickle.loads(pickle.dumps(build_history(setup, decisions)))
    assert rebuilt.latest_views == canonical_views(game.session)


def test_group_reads_do_not_mutate_patch_values_or_future_snapshots():
    from goa2.server.replay_codec import reconstruct_many

    builder = GroupBuilder(0, {"items": []})
    builder.append(1, {"items": [{"gold": 1}]})
    builder.append(2, {"items": [{"gold": 2}]})
    group = deepcopy(builder.group)
    assert reconstruct(builder.group, 2) == {"items": [{"gold": 2}]}
    assert reconstruct(builder.group, 1) == {"items": [{"gold": 1}]}
    result = reconstruct_many(builder.group, [2, 0, 1])
    result[2]["items"][0]["gold"] = 100
    assert builder.group == group
    assert result[1]["items"][0]["gold"] == 1
    with pytest.raises(ValueError):
        reconstruct_many(group, [-1])


def test_member_projection_strips_other_seats_and_rejects_cross_scope_moves():
    from goa2.server.replay_codec import project_member

    builder = GroupBuilder(0, {"a/b": {"items": [1, 2]}, "other": {"secret": "hidden"}})
    builder.append(1, {"a/b": {"items": [2, 1]}, "other": {"secret": "changed"}})
    scoped = project_member(builder.group, "a/b")
    assert "hidden" not in json.dumps(scoped)
    assert "changed" not in json.dumps(scoped)
    assert reconstruct(scoped, 1) == {"items": [2, 1]}
    base = {"start": 0, "keyframe": {"mine": {"value": 1}, "other": {"secret": 2}}}
    for operation in (
        {"op": "move", "from": "/mine/value", "path": "/other/x"},
        {"op": "copy", "from": "/other/secret", "path": "/mine/x"},
    ):
        with pytest.raises(ValueError, match="Cross-member"):
            project_member({**base, "patches": [[operation]]}, "mine")
    root = {
        **base,
        "patches": [
            [{"op": "replace", "path": "", "value": {"mine": {"value": 3}, "other": {"secret": 4}}}]
        ],
    }
    assert reconstruct(project_member(root, "mine"), 1) == {"value": 3}


def test_reader_snapshot_is_stable_while_writer_appends():
    history = LiveHistory()
    history.capture_views(views(0), 0)
    reader = history.reader()
    history.capture_views(views(1), 1, {"type": "input"})
    assert reader.read(0, "spectator")["view"]["value"] == 0
    with pytest.raises(HistoryUnavailable):
        reader.read_many([1], "spectator")
    values = history.reader().read_many([0, 1], "spectator")
    assert [value["view"]["value"] for value in values] == [0, 1]


def test_multiple_durable_groups_and_cache_eviction(tmp_path):
    history = LiveHistory(tmp_path)
    history.capture_views(views(), 0)
    history.builder.max_patches = 3
    for count in range(1, 135):
        history.capture_views(views(count), count, {"type": "input"})
    manifest = history.prepare_manifest()
    history.committed()
    assert len(history.groups) > 1
    restored = LiveHistory.restore(tmp_path, manifest)
    reader = restored.reader()
    assert [b["view"]["value"] for b in reader.read_many([0, 3, 134], "spectator")] == [0, 3, 134]
    live_history._CACHE.clear()
    for count in range(135):
        reader.read(count, "spectator")
    assert len(live_history._CACHE) == 128
    assert (restored.cache_id, "spectator", 0) not in live_history._CACHE


def test_batched_projection_matches_live_views_through_resolution(client_game):
    import random

    from goa2.domain.views import build_view
    from goa2.server.time_control import _timeout_selection

    client, registry, data = client_game
    commit(client, data, 0)
    game = registry.get(data["game_id"])
    planning_id = game.history.active[-1]
    card_id = game.session.state.get_hero("hero_arien").current_turn_card.id
    commit(client, data, 1)
    for _ in range(6):
        captures = canonical_views(game.session)
        for viewer, body in captures.items():
            expected = build_view(
                game.session.state, for_hero_id=None if viewer == "spectator" else HeroID(viewer)
            )
            expected["clock"] = expected["starting_position"] = None
            assert body["view"] == expected
        request = game.last_result.input_request if game.last_result else None
        if request is None:
            break
        game.last_result = game.session.advance(
            InputResponse(
                request_id=request.id, selection=_timeout_selection(request, random.Random(3))
            )
        )
    past = game.history.reader().read(planning_id, "hero_wasp")
    assert card_id not in json.dumps(past)  # Later public revelation cannot rewrite the past.


def test_failed_repair_storage_does_not_restart_on_every_read(client_game, monkeypatch):
    client, registry, data = client_game
    commit(client, data)
    game = registry.get(data["game_id"])
    committed_active = game.history.last_manifest["active"].copy()
    game.history.backfill_status = "pending"
    calls = []

    async def inline(fn, *args):
        if fn is build_history:
            calls.append(1)
        return fn(*args)

    def disk_full(*_):
        raise OSError("persistent disk failure")

    monkeypatch.setattr(history_backfill, "run_heavy", inline)
    monkeypatch.setattr(live_history, "_atomic_bytes", disk_full)
    asyncio.run(history_backfill.ensure_backfill(game, registry))
    assert game.history.backfill_status == "unavailable"
    asyncio.run(history_backfill.ensure_backfill(game, registry))
    assert calls == [1]
    saved = json.loads((Path(registry._save_dir) / f"{game.game_id}.json").read_text())
    assert saved["live_history"]["active"] == committed_active


def test_backfill_roundtrip_through_real_worker_pool(client_game):
    client, registry, data = client_game
    commit(client, data)
    game = registry.get(data["game_id"])
    game.history.backfill_status = "pending"
    asyncio.run(history_backfill.ensure_backfill(game, registry))
    assert game.history.backfill_status == "complete"
    assert game.history.latest_views == canonical_views(game.session)


def test_backfill_publishes_new_epoch_to_connected_clients(client_game, monkeypatch):
    client, registry, data = client_game
    game = registry.get(data["game_id"])

    async def inline(fn, *args):
        return fn(*args)

    monkeypatch.setattr(history_backfill, "run_heavy", inline)
    token = data["player_tokens"][0]["token"]
    with client.websocket_connect(f"/games/{game.game_id}/ws?token={token}") as socket:
        first = socket.receive_json()
        game.history.backfill_status = "pending"
        index = client.get(f"/games/{game.game_id}/history", headers=auth(data))
        assert index.status_code == 200
        update = socket.receive_json()
        assert update["type"] == "STATE_UPDATE"
        assert update["history"]["epoch"] > first["history"]["epoch"]
        assert update["history"]["epoch"] == index.json()["epoch"]


def test_legacy_save_without_replay_keeps_readable_baseline(client_game):
    client, registry, data = client_game
    commit(client, data)
    game = registry.get(data["game_id"])
    path = Path(registry._save_dir) / f"{game.game_id}.json"
    saved = json.loads(path.read_text())
    saved["live_history"] = saved["replay_log"] = None
    path.write_text(json.dumps(saved))
    game.replay_recorder.path.unlink()
    restored = GameRegistry(registry._save_dir)
    restored.restore_all()
    again = restored.get(game.game_id)
    assert again.history.backfill_status == "pending"
    asyncio.run(history_backfill.ensure_backfill(again, restored))
    assert again.history.backfill_status == "unavailable"
    body = again.history.reader().read(again.history.active[-1], "hero_arien")
    assert body == canonical_views(again.session)["hero_arien"]

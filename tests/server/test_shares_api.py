"""Tests for baked, shareable replay artifacts (public read + admin mint/revoke)."""

from __future__ import annotations

import asyncio
import gzip
import json
import os
from pathlib import Path

import brotli
import jsonpatch
import pytest
from fastapi.testclient import TestClient

from goa2.domain.types import HeroID
from goa2.engine.session import GameSession
from goa2.engine.setup import GameSetup
from goa2.server import routes_replays, share_mint, shares
from goa2.server.app import create_app
from goa2.server.replay import ReplayRecorder, _resolve_map_path, cleanup_old_replays
from goa2.server.share_bake import bake_replay_share
from goa2.server.workers import run_heavy, shutdown_heavy_pool

MAP = "forgotten_island"
RED = ["Arien"]
BLUE = ["Wasp"]
FINISHED = "sharefin1"
UNFINISHED = "shareopen1"
REWOUND = "sharerewind1"


def _hero_ids(state) -> list[str]:
    return [h.id for team in state.teams.values() for h in team.heroes]


def _record_game(game_id: str, *, finish: bool, seed: int = 42) -> None:
    """Record a short game; optionally end it with a recorded override.

    Playing a real game to its natural end takes thousands of decisions. An
    ``ov_patch`` dropping a team to zero life counters is a genuine, replayable
    decision that produces a real GAME_OVER state, so the finished fixture
    exercises the same reconstruction path a naturally-won game would.
    """
    state = GameSetup.create_game(_resolve_map_path(MAP), RED, BLUE, False, "QUICK", seed=seed)
    live = GameSession(state)
    rec = ReplayRecorder(game_id)
    rec.record_setup(
        map_name=MAP, red_heroes=RED, blue_heroes=BLUE, game_type="QUICK", cheats=False, seed=seed
    )
    for hero_id in _hero_ids(live.state):
        card = live.state.get_hero(HeroID(hero_id)).hand[0]
        rec.record_commit(hero_id, card.id, live.state.round, live.state.turn)
        live.commit_card(HeroID(hero_id), card)

    if finish:
        rec.record_override(
            {
                "type": "ov_patch",
                "r": live.state.round,
                "t": live.state.turn,
                "hero": _hero_ids(live.state)[0],
                "op": "set_life_counters",
                "args": {"team": "BLUE", "value": 0},
                "voters": _hero_ids(live.state),
            }
        )


_REWOUND_DEAD_CARD = ""
_REWOUND_KEPT_CARD = ""


def _record_rewound_game(game_id: str, seed: int = 42) -> None:
    """Record a game whose table voted to rewind, then replayed the turn differently.

    Decision 1 (the first Wasp commit) is rewound away by decision 2 and replaced
    by decision 3, so the effective timeline is 0, 3, 4.
    """
    global _REWOUND_DEAD_CARD, _REWOUND_KEPT_CARD

    state = GameSetup.create_game(_resolve_map_path(MAP), RED, BLUE, False, "QUICK", seed=seed)
    live = GameSession(state)
    rec = ReplayRecorder(game_id)
    rec.record_setup(
        map_name=MAP, red_heroes=RED, blue_heroes=BLUE, game_type="QUICK", cheats=False, seed=seed
    )
    red_id, blue_id = _hero_ids(live.state)[0], _hero_ids(live.state)[1]

    card = live.state.get_hero(HeroID(red_id)).hand[0]
    rec.record_commit(red_id, card.id, live.state.round, live.state.turn)
    live.commit_card(HeroID(red_id), card)

    blue_hand = live.state.get_hero(HeroID(blue_id)).hand
    _REWOUND_DEAD_CARD, _REWOUND_KEPT_CARD = blue_hand[0].id, blue_hand[1].id

    rec.record_commit(blue_id, _REWOUND_DEAD_CARD, live.state.round, live.state.turn)
    rec.record_override(
        {
            "type": "ov_rewind",
            "r": live.state.round,
            "t": live.state.turn,
            "hero": blue_id,
            "to": 1,
            "voters": [red_id, blue_id],
        }
    )
    rec.record_commit(blue_id, _REWOUND_KEPT_CARD, live.state.round, live.state.turn)
    live.commit_card(HeroID(blue_id), blue_hand[1])

    rec.record_override(
        {
            "type": "ov_patch",
            "r": live.state.round,
            "t": live.state.turn,
            "hero": red_id,
            "op": "set_life_counters",
            "args": {"team": "BLUE", "value": 0},
            "voters": [red_id, blue_id],
        }
    )


@pytest.fixture
def client(monkeypatch):
    """TestClient with the admin API enabled and both fixture games recorded."""

    async def run_inline(fn, *args):
        return fn(*args)

    monkeypatch.setattr(share_mint, "run_heavy", run_inline)
    routes_replays._CACHE.clear()
    prev = os.environ.get("GOA2_REPLAY_API")
    os.environ["GOA2_REPLAY_API"] = "1"
    try:
        _record_game(FINISHED, finish=True)
        _record_game(UNFINISHED, finish=False)
        with TestClient(create_app()) as c:
            yield c
    finally:
        routes_replays._CACHE.clear()
        if prev is None:
            os.environ.pop("GOA2_REPLAY_API", None)
        else:
            os.environ["GOA2_REPLAY_API"] = prev


def _mint(client) -> str:
    res = client.post(f"/replays/{FINISHED}/share")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["url"] == f"/shared/{body['token']}"
    return body["token"]


def _fetch_position(client, token: str, query: str) -> dict:
    """Read one position the way the frontend does: fetch a group, apply patches.

    The response is a whole group, so this mirrors the client contract rather
    than hiding it — a test that broke reconstruction would otherwise pass.
    """
    res = client.get(f"/shared/{token}/state?{query}", headers={"Accept-Encoding": "br"})
    assert res.status_code == 200, res.text
    # httpx decodes Content-Encoding transparently, exactly as a browser does.
    group = res.json()
    target = int(res.headers["x-replay-position"])
    body = group["keyframe"]
    for patch in group["patches"][: target - group["start"]]:
        body = jsonpatch.JsonPatch(patch).apply(body)
    return body


def _strip_volatile(obj):
    """Drop non-deterministic instance identifiers (step_id = id(object()))."""
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items() if k != "step_id"}
    if isinstance(obj, list):
        return [_strip_volatile(v) for v in obj]
    return obj


# --- minting --------------------------------------------------------------


def test_real_shared_worker_pool_can_bake_a_share():
    """Keep spawn/pickling/worker initialization covered end to end."""
    _record_game(FINISHED, finish=True)
    replay_path = Path(os.environ["GOA2_REPLAY_DIR"]) / f"{FINISHED}.jsonl"
    try:
        result = asyncio.run(
            run_heavy(
                bake_replay_share,
                str(replay_path),
                FINISHED,
                os.environ["GOA2_SHARE_DIR"],
            )
        )
    finally:
        shutdown_heavy_pool()

    assert result["ok"] is True
    assert shares.share_for_game(FINISHED)["token"] == result["token"]


def test_mint_requires_a_finished_game(client):
    res = client.post(f"/replays/{UNFINISHED}/share")
    assert res.status_code == 409
    assert "finished" in res.json()["detail"]


def test_rejected_mint_leaves_no_artifact(client):
    client.post(f"/replays/{UNFINISHED}/share")
    assert shares.list_shares() == []


def test_mint_unknown_game_404(client):
    assert client.post("/replays/nope/share").status_code == 404


@pytest.mark.parametrize(
    "lines, expected_status",
    [
        # No setup header at all, and a corrupt line: rejected before any bake.
        ([{"type": "pass", "r": 1, "t": 1, "hero": "hero_arien"}], 422),
        ("{not json", 422),
        # Malformed decision records: these reach the engine and must still come
        # back as 422, not a 500. A missing key raises KeyError rather than the
        # ValueError engine drift produces, which once escaped as a 500.
        ([{"type": "commit", "r": 1, "t": 1, "card": "x"}], 422),
        ([{"type": "teleport", "r": 1, "t": 1, "hero": "hero_arien"}], 422),
    ],
)
def test_broken_replays_are_rejected_not_500(client, lines, expected_status):
    path = Path(os.environ["GOA2_REPLAY_DIR"]) / "broken.jsonl"
    header = (Path(os.environ["GOA2_REPLAY_DIR"]) / f"{FINISHED}.jsonl").read_text().splitlines()[0]
    if isinstance(lines, str):
        path.write_text(header + "\n" + lines + "\n")
    else:
        body = "\n".join(json.dumps(d) for d in lines)
        # First case deliberately omits the header to exercise that path.
        prefix = "" if lines[0].get("type") == "pass" else header + "\n"
        path.write_text(prefix + body + "\n")

    res = client.post("/replays/broken/share")
    assert res.status_code == expected_status, res.text
    assert shares.list_shares() == []  # nothing published, no staging left behind


def test_minting_twice_returns_the_same_share(client):
    """A finished game's artifact can never change, so re-sharing must not re-bake."""
    first = _mint(client)
    second = _mint(client)
    assert first == second
    assert len(shares.list_shares()) == 1


def test_existing_share_is_returned_when_original_replay_is_missing(client):
    token = _mint(client)
    (Path(os.environ["GOA2_REPLAY_DIR"]) / f"{FINISHED}.jsonl").unlink()

    response = client.post(f"/replays/{FINISHED}/share")

    assert response.status_code == 201
    assert response.json() == {"token": token, "url": f"/shared/{token}"}


# --- listing (drives the replay-list UI) ----------------------------------


def test_list_shares_reports_what_the_ui_needs(client):
    token = _mint(client)
    rows = client.get("/shares").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["token"] == token
    assert row["game_id"] == FINISHED
    assert row["total_decisions"] == 3
    assert row["size_bytes"] > 0  # recorded at bake time, not stat'd per request
    assert row["created_at"] is not None


def test_list_shares_empty_before_minting(client):
    assert client.get("/shares").json() == []


def test_listing_requires_admin(client):
    prev = os.environ.pop("GOA2_REPLAY_API", None)
    try:
        with TestClient(create_app()) as anon:
            assert anon.get("/shares").status_code == 404
    finally:
        if prev is not None:
            os.environ["GOA2_REPLAY_API"] = prev


# --- the load-bearing property -------------------------------------------


def test_every_baked_position_matches_dynamic_reconstruction(client):
    """A baked position must equal what /replays/{id}/state returns at that index."""
    token = _mint(client)
    total = client.get(f"/shared/{token}").json()
    assert len(total["decisions"]) == 3

    for n in range(4):
        baked = _fetch_position(client, token, f"decision={n}")
        live = client.get(f"/replays/{FINISHED}/state?decision={n}").json()
        assert _strip_volatile(baked) == _strip_volatile(live), f"mismatch at decision {n}"


def test_shared_meta_matches_replay_meta(client):
    token = _mint(client)
    shared = client.get(f"/shared/{token}").json()
    admin = client.get(f"/replays/{FINISHED}").json()
    assert shared["decisions"] == admin["decisions"]
    assert shared["setup"] == admin["setup"]


# --- public serving -------------------------------------------------------


def test_state_is_served_brotli_when_accepted(client):
    token = _mint(client)
    res = client.get(f"/shared/{token}/state?decision=0", headers={"Accept-Encoding": "br"})
    assert res.status_code == 200
    assert res.headers["content-encoding"] == "br"
    assert res.headers["vary"] == "Accept-Encoding"
    assert res.json()["start"] == 0


def test_state_falls_back_to_gzip_without_brotli(client):
    token = _mint(client)
    res = client.get(f"/shared/{token}/state?decision=0", headers={"Accept-Encoding": "gzip"})
    assert res.status_code == 200
    assert res.headers["content-encoding"] == "gzip"
    assert res.json()["start"] == 0


def test_both_encodings_carry_identical_content(client):
    token = _mint(client)
    q = {"Accept-Encoding": "br"}, {"Accept-Encoding": "gzip"}
    br, gz = (client.get(f"/shared/{token}/state?decision=0", headers=h) for h in q)
    assert br.json() == gz.json()


def test_only_brotli_is_stored(client):
    """The gzip a non-brotli client gets is transcoded per request, not kept."""
    token = _mint(client)
    directory = Path(os.environ["GOA2_SHARE_DIR"]) / token
    assert sorted(p.suffix for p in directory.glob("g*")) == [".br"]
    assert (
        client.get(f"/shared/{token}/state", headers={"Accept-Encoding": "gzip"}).status_code == 200
    )
    assert sorted(p.suffix for p in directory.glob("g*")) == [".br"]


def test_state_clamps_out_of_range(client):
    token = _mint(client)
    body = _fetch_position(client, token, "decision=999")
    assert body["position"]["decision_index"] == 3
    assert body["position"]["total_decisions"] == 3


def test_state_defaults_to_end_of_game(client):
    token = _mint(client)
    body = _fetch_position(client, token, "")
    assert body["position"]["decision_index"] == 3
    assert body["winner"] is not None


def test_round_jump_works_without_the_engine(client):
    token = _mint(client)
    baked = _fetch_position(client, token, "round=1")
    live = client.get(f"/replays/{FINISHED}/state?round=1").json()
    assert baked["position"] == live["position"]


# --- revocation & errors --------------------------------------------------


def test_revoke_makes_the_link_dead(client):
    token = _mint(client)
    assert client.get(f"/shared/{token}").status_code == 200
    assert client.delete(f"/shares/{token}").status_code == 204
    assert client.get(f"/shared/{token}").status_code == 404
    assert client.get(f"/shared/{token}/state?decision=0").status_code == 404


def test_revoke_unknown_token_404(client):
    assert client.delete("/shares/doesnotexist").status_code == 404


def test_unknown_token_404(client):
    assert client.get("/shared/doesnotexist").status_code == 404


@pytest.mark.parametrize("bad", ["..%2F..%2Fetc", "with/slash", "with.dot"])
def test_malformed_tokens_are_rejected(client, bad):
    assert client.get(f"/shared/{bad}").status_code == 404
    assert client.get(f"/shared/{bad}/state?decision=0").status_code == 404


# --- gating ---------------------------------------------------------------


def test_shares_readable_without_admin_but_not_mintable(client):
    """The share router is public; minting and revoking are not."""
    token = _mint(client)
    prev = os.environ.get("GOA2_REPLAY_API")
    os.environ.pop("GOA2_REPLAY_API", None)
    try:
        with TestClient(create_app()) as anon:
            assert anon.get(f"/shared/{token}").status_code == 200
            assert anon.get(f"/shared/{token}/state?decision=0").status_code == 200
            # Admin routers are not mounted at all without a token or the dev flag.
            assert anon.post(f"/replays/{FINISHED}/share").status_code == 404
            assert anon.delete(f"/shares/{token}").status_code == 404
    finally:
        if prev is not None:
            os.environ["GOA2_REPLAY_API"] = prev


# --- retention ------------------------------------------------------------


def test_shared_replay_is_pinned_against_ttl(client):
    _mint(client)
    # TTL of 0 days: everything unpinned is stale.
    removed = cleanup_old_replays(ttl_days=0)
    assert removed == 1  # only the unshared game went
    assert shares.shared_game_ids() == {FINISHED}


def test_revoked_share_releases_the_pin(client):
    token = _mint(client)
    client.delete(f"/shares/{token}")
    removed = cleanup_old_replays(ttl_days=0)
    assert removed == 2


# --- rewinds collapse into the shared timeline ----------------------------


def test_a_rewound_game_bakes_its_final_timeline(client):
    """A share is the game as it ended, not the dead branches it took to get there.

    The rewound-away commit must be absent from the shared decision list, and
    the surviving one present, so a viewer scrubs a clean monotonic timeline.
    """
    _record_rewound_game(REWOUND)

    res = client.post(f"/replays/{REWOUND}/share")
    assert res.status_code == 201, res.text

    body = client.get(f"/shared/{res.json()['token']}").json()
    types = [d["type"] for d in body["decisions"]]
    assert "ov_rewind" not in types
    assert types == ["commit", "commit", "ov_patch"]

    cards = [d["card"] for d in body["decisions"] if d["type"] == "commit"]
    assert _REWOUND_KEPT_CARD in cards
    assert _REWOUND_DEAD_CARD not in cards


def test_every_baked_position_of_a_rewound_game_is_reachable(client):
    """Baking walks the collapsed list, so every index must render a position."""
    _record_rewound_game(REWOUND)
    token = client.post(f"/replays/{REWOUND}/share").json()["token"]

    for n in range(4):
        body = _fetch_position(client, token, f"decision={n}")
        assert body["position"]["decision_index"] == n
    assert _fetch_position(client, token, "")["winner"] is not None


# --- group layout ---------------------------------------------------------


def _bulky_body(index: int) -> dict:
    """A body big enough that patches are worth taking, changing a little per step.

    Mirrors the real shape: a large mostly-static board plus a few volatile
    fields, which is what makes the keyframe/patch trade pay.
    """
    tiles = {
        f"{q},{r}": {"hex": [q, r], "zone": "mid", "occupant": None}
        for q in range(20)
        for r in range(20)
    }
    tiles[f"{index % 20},{index % 20}"]["occupant"] = f"minion_{index}"
    return {
        "view": {"board": {"tiles": tiles}, "round": index // 10, "turn": index % 10},
        "position": {
            "decision_index": index,
            "round": index // 10,
            "turn": index % 10,
            "total_decisions": 400,
        },
        "winner": None,
    }


def _bake_stub(tmp_path, count: int) -> tuple[str, dict]:
    os.environ["GOA2_SHARE_DIR"] = str(tmp_path)
    token = shares.bake_share(
        game_id="g",
        setup={"engine": "test"},
        decisions=[{"type": "commit", "r": i // 10, "t": i % 10} for i in range(count)],
        render=_bulky_body,
    )
    assert token
    return token, shares.load_meta(token)


def test_new_share_has_constant_time_game_index(tmp_path, monkeypatch):
    token, _meta = _bake_stub(tmp_path, 1)
    index_path = shares._game_index_path(tmp_path, "g")
    assert index_path.is_file()

    def unexpected_scan():
        pytest.fail("indexed lookup scanned every share")

    monkeypatch.setattr(shares, "list_shares", unexpected_scan)
    assert shares.share_for_game("g")["token"] == token


def test_existing_unindexed_shares_are_migrated_once(tmp_path, monkeypatch):
    os.environ["GOA2_SHARE_DIR"] = str(tmp_path)
    token = "existingShareToken"
    directory = tmp_path / token
    directory.mkdir()
    (directory / "meta.json").write_text(
        json.dumps(
            {
                "token": token,
                "game_id": "existing-game",
                "created_at": 1,
                "decisions": [],
            }
        )
    )
    other_token = "otherExistingToken"
    other_directory = tmp_path / other_token
    other_directory.mkdir()
    (other_directory / "meta.json").write_text(
        json.dumps(
            {
                "token": other_token,
                "game_id": "other-existing-game",
                "created_at": 2,
                "decisions": [],
            }
        )
    )

    assert not shares._game_index_path(tmp_path, "existing-game").exists()
    assert shares.share_for_game("existing-game")["token"] == token
    assert shares._game_index_path(tmp_path, "existing-game").is_file()

    def unexpected_scan():
        pytest.fail("migrated lookup scanned every share")

    monkeypatch.setattr(shares, "list_shares", unexpected_scan)
    assert shares.share_for_game("existing-game")["token"] == token
    assert shares.share_for_game("other-existing-game")["token"] == other_token
    assert shares.share_for_game("game-with-no-share") is None


def test_stale_game_index_repairs_from_existing_share(tmp_path):
    os.environ["GOA2_SHARE_DIR"] = str(tmp_path)
    token = "repairableShareToken"
    directory = tmp_path / token
    directory.mkdir()
    (directory / "meta.json").write_text(
        json.dumps(
            {
                "token": token,
                "game_id": "repair-game",
                "created_at": 1,
                "decisions": [],
            }
        )
    )
    shares._write_game_index(tmp_path, "repair-game", "missingShareToken")

    assert shares.share_for_game("repair-game")["token"] == token
    index = json.loads(shares._game_index_path(tmp_path, "repair-game").read_text())
    assert index == {"game_id": "repair-game", "token": token}


def test_revoking_share_removes_its_game_index(tmp_path):
    token, _meta = _bake_stub(tmp_path, 1)
    index_path = shares._game_index_path(tmp_path, "g")
    assert index_path.is_file()

    assert shares.revoke_share(token)
    assert not index_path.exists()


def test_index_publication_failure_leaves_no_share_artifact(tmp_path, monkeypatch):
    os.environ["GOA2_SHARE_DIR"] = str(tmp_path)

    def fail_index(*args):
        raise OSError("disk full")

    monkeypatch.setattr(shares, "_write_game_index", fail_index)

    with pytest.raises(OSError, match="disk full"):
        shares.bake_share(
            game_id="g",
            setup={"engine": "test"},
            decisions=[],
            render=_bulky_body,
        )

    assert list(tmp_path.iterdir()) == []


def test_a_long_game_is_split_into_several_groups(tmp_path):
    _token, meta = _bake_stub(tmp_path, 400)
    assert meta["format"] == 2
    assert len(meta["groups"]) > 1, "400 positions should not fit in one group"
    # Groups tile the timeline exactly: contiguous, ordered, covering every index.
    assert meta["groups"][0]["start"] == 0
    covered = 0
    for group in meta["groups"]:
        assert group["start"] == covered
        covered += group["count"]
    assert covered == 401


def test_every_position_reconstructs_across_group_boundaries(tmp_path):
    token, meta = _bake_stub(tmp_path, 400)
    for group in meta["groups"]:
        doc = json.loads(brotli.decompress(shares.group_path(token, group["start"]).read_bytes()))
        body = doc["keyframe"]
        assert body == _bulky_body(group["start"])
        for offset, patch in enumerate(doc["patches"], start=1):
            body = jsonpatch.JsonPatch(patch).apply(body)
            assert body == _bulky_body(
                group["start"] + offset
            ), f"position {group['start'] + offset} does not reconstruct"


def test_grouping_is_far_smaller_than_one_file_per_position(tmp_path):
    token, _meta = _bake_stub(tmp_path, 400)
    grouped = sum(p.stat().st_size for p in Path(tmp_path, token).glob("*.json.br"))
    whole = sum(len(gzip.compress(json.dumps(_bulky_body(i)).encode(), 6)) for i in range(401))
    assert grouped * 10 < whole, f"expected a large reduction, got {whole / grouped:.1f}x"


def test_every_index_maps_into_a_group_that_contains_it(tmp_path):
    _, meta = _bake_stub(tmp_path, 400)
    spans = {g["start"]: g["count"] for g in meta["groups"]}
    for index in range(401):
        start = shares.group_start_for(meta, index)
        assert start <= index < start + spans[start]


# --- shares baked before groups existed -----------------------------------


def test_format_1_shares_are_still_served(tmp_path, client):
    """An artifact on disk from before this change must keep working untouched."""
    token = "legacyToken123"
    directory = Path(os.environ["GOA2_SHARE_DIR"]) / token
    directory.mkdir(parents=True)
    body = {"view": {}, "position": {"decision_index": 1, "total_decisions": 1}, "winner": "RED"}
    for index in (0, 1):
        (directory / f"{index:03d}.json.gz").write_bytes(
            gzip.compress(json.dumps(body).encode(), 6)
        )
    (directory / "meta.json").write_text(
        json.dumps(
            {"token": token, "game_id": "old", "setup": {}, "decisions": [], "total_decisions": 1}
        )
    )

    assert shares.is_grouped(shares.load_meta(token)) is False
    res = client.get(f"/shared/{token}/state?decision=1")
    assert res.status_code == 200
    assert res.headers["content-encoding"] == "gzip"
    assert res.json() == body


# --- converting shares baked before groups existed ------------------------


def _write_format_1_share(directory: Path, bodies: list[dict]) -> str:
    """Lay out a share exactly as the old bake did: one gzip file per position."""
    token = "legacyMigrate1"
    share = directory / token
    share.mkdir(parents=True)
    for index, body in enumerate(bodies):
        (share / f"{index:03d}.json.gz").write_bytes(gzip.compress(json.dumps(body).encode(), 6))
    (share / "meta.json").write_text(
        json.dumps(
            {
                "token": token,
                "game_id": "old",
                "setup": {"engine": "old"},
                "decisions": [
                    {"index": i, "type": "commit", "r": i // 10 + 1, "t": i % 10 + 1}
                    for i in range(len(bodies) - 1)
                ],
                "total_decisions": len(bodies) - 1,
                "size_bytes": 1234,
            }
        )
    )
    return token


def _reconstruct_all(token: str, meta: dict) -> list[dict]:
    out: list[dict] = []
    for group in meta["groups"]:
        doc = json.loads(brotli.decompress(shares.group_path(token, group["start"]).read_bytes()))
        body = doc["keyframe"]
        out.append(json.loads(json.dumps(body)))
        for patch in doc["patches"]:
            body = jsonpatch.JsonPatch(patch).apply(body)
            out.append(json.loads(json.dumps(body)))
    return out


def test_migration_preserves_every_position(tmp_path):
    """Converting must be lossless: the artifact is what recipients already see."""
    os.environ["GOA2_SHARE_DIR"] = str(tmp_path)
    bodies = [_bulky_body(i) for i in range(401)]
    token = _write_format_1_share(tmp_path, bodies)

    meta = shares.migrate_share_to_groups(token)
    assert meta is not None
    assert _reconstruct_all(token, meta) == bodies


def test_migration_keeps_the_token_and_the_decision_list(tmp_path):
    """Links already handed out must keep working, so nothing identifying moves."""
    os.environ["GOA2_SHARE_DIR"] = str(tmp_path)
    bodies = [_bulky_body(i) for i in range(60)]
    token = _write_format_1_share(tmp_path, bodies)
    before = shares.load_meta(token)

    after = shares.migrate_share_to_groups(token)
    assert after["token"] == token
    assert after["decisions"] == before["decisions"]
    assert after["game_id"] == before["game_id"]
    assert after["setup"] == before["setup"]
    assert (tmp_path / token).is_dir()


def test_migration_removes_the_old_position_files(tmp_path):
    os.environ["GOA2_SHARE_DIR"] = str(tmp_path)
    token = _write_format_1_share(tmp_path, [_bulky_body(i) for i in range(60)])
    shares.migrate_share_to_groups(token)

    share = tmp_path / token
    assert list(share.glob("*.json.gz")) == []
    assert list(share.glob("*.json.tmp")) == []
    assert share.glob("g*.json.br")


def test_migration_shrinks_the_share(tmp_path):
    os.environ["GOA2_SHARE_DIR"] = str(tmp_path)
    bodies = [_bulky_body(i) for i in range(401)]
    token = _write_format_1_share(tmp_path, bodies)
    was = sum(p.stat().st_size for p in (tmp_path / token).glob("*.json.gz"))

    meta = shares.migrate_share_to_groups(token)
    assert meta["size_bytes"] * 10 < was


def test_migration_is_safe_to_run_again(tmp_path):
    os.environ["GOA2_SHARE_DIR"] = str(tmp_path)
    token = _write_format_1_share(tmp_path, [_bulky_body(i) for i in range(60)])
    first = shares.migrate_share_to_groups(token)

    assert shares.migrate_share_to_groups(token) is None
    assert shares.load_meta(token)["groups"] == first["groups"]


def test_migration_ignores_unknown_tokens(tmp_path):
    os.environ["GOA2_SHARE_DIR"] = str(tmp_path)
    assert shares.migrate_share_to_groups("nosuchtoken") is None


def test_a_migrated_share_serves_over_http(client):
    """The whole point: the same URL keeps working, now group-at-a-time."""
    bodies = [_bulky_body(i) for i in range(60)]
    token = _write_format_1_share(Path(os.environ["GOA2_SHARE_DIR"]), bodies)
    assert client.get(f"/shared/{token}/state?decision=5").json() == bodies[5]

    shares.migrate_share_to_groups(token)
    assert _fetch_position(client, token, "decision=5") == bodies[5]
    assert _fetch_position(client, token, "decision=59") == bodies[59]

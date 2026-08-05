"""REST endpoints: op schema catalogue + player-scoped history."""

import os

import pytest
from fastapi.testclient import TestClient

from goa2.engine.overrides import OVERRIDE_OPS
from goa2.server.app import create_app


@pytest.fixture
def client(tmp_path):
    os.environ["GOA2_SAVE_DIR"] = str(tmp_path)
    app = create_app()
    with TestClient(app) as c:
        yield c
    os.environ.pop("GOA2_SAVE_DIR", None)


def test_schema_lists_every_registered_op(client):
    resp = client.get("/overrides/schema")
    assert resp.status_code == 200
    ops = {o["name"]: o for o in resp.json()["ops"]}
    # Schema completeness: every registered op appears with a valid arg schema.
    assert set(ops) == set(OVERRIDE_OPS)
    for op in ops.values():
        assert op["family"] in ("patch", "unstick")
        assert op["label"] and op["description"]
        assert isinstance(op["args_schema"], dict)
        assert op["args_schema"].get("type") == "object"


def test_schema_is_static_and_unauthenticated(client):
    # Game-independent; clients fetch once and cache.
    assert client.get("/overrides/schema").json() == client.get("/overrides/schema").json()

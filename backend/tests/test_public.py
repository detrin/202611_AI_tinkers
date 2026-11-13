"""The public entrypoint serves the same API under /api (behind the Cloudflare tunnel) and still at /."""
import pytest
from fastapi.testclient import TestClient

import backend.app.public as public
from backend.app.main import create_app


@pytest.fixture
def api_client(env, monkeypatch):
    monkeypatch.setattr(public, "api", create_app(lambda: env.c))
    with TestClient(public.app) as c:
        yield c


def test_routes_work_under_api_prefix_and_without_it(api_client):
    assert api_client.get("/api/health").json() == {"ok": True}
    assert api_client.get("/health").json() == {"ok": True}
    uid = api_client.post("/api/users", json={"name": "Dan"}).json()["id"]
    assert api_client.get(f"/api/users/{uid}").status_code == 200
    assert api_client.get("/api/nope").status_code == 404
    assert api_client.get("/apix/health").status_code == 404


def test_docs_point_at_prefixed_openapi(api_client):
    assert api_client.get("/api/openapi.json").status_code == 200
    assert "/api/openapi.json" in api_client.get("/api/docs").text

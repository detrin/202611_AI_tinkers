import json
from types import SimpleNamespace

import pytest

from backend.app.adapters.claude_cli import ClaudeCLI, ClaudeCLIError
from backend.app.domain import ImageInput
from backend.app.errors import Conflict, NotFound
from backend.app.services.taste import TASTE_SCHEMA, wardrobe_facts


# ---------- pure facts ----------
def test_wardrobe_facts_counts_primary_colors_and_formality():
    items = [{"category": "top", "colors": ["navy", "white"], "formality": 3, "style_tags": ["preppy"]},
             {"category": "top", "colors": ["navy"], "formality": 3, "style_tags": ["preppy", "minimal"]},
             {"category": "shoes", "colors": [], "formality": 2}]
    f = wardrobe_facts(items)
    assert f["item_count"] == 3
    assert f["categories"][0] == ["top", 2]
    assert f["primary_colors"] == [["navy", 2]]
    assert ["white", 1] in f["all_colors"]
    assert f["style_tags"][0] == ["preppy", 2]
    assert f["formality_histogram"] == {2: 1, 3: 2}


def test_wardrobe_facts_empty():
    assert wardrobe_facts([])["item_count"] == 0


# ---------- service ----------
def _seed(env):
    uid = env.user()["id"]
    env.items(uid, 2)
    env.c.wardrobe.add(uid, [ImageInput(b"wish")], status="wanted")
    env.c.inspirations.add(uid, [ImageInput(b"look")])
    return uid


def test_evidence_separates_current_and_aspirational_sources(env):
    uid = _seed(env)
    ev = env.c.taste.evidence(uid)
    counts = env.c.taste.counts(ev)
    assert counts["owned_items"] == 2 and counts["wishlist_items"] == 1 and counts["inspiration_looks"] == 1
    assert ev["wardrobe_facts"]["item_count"] == 2                      # facts only from owned items


def test_evidence_includes_liked_products_and_rated_outfits(env):
    uid = _seed(env)
    env.c.recommendations.create(uid, ["coat"], n=1, per_query=1, marketplaces=[])
    env.c.feedback.record(uid, env.db.tables["products"][0]["id"], liked=True, bought=False)
    outfit = env.c.outfits.daily(uid, "office")
    env.c.outfits.feedback(uid, outfit["id"], {"worn": True, "rating": 5})
    ev = env.c.taste.evidence(uid)
    assert ev["liked_products"][0]["name"] == "coat 0"
    assert ev["outfit_feedback"][0]["feedback"] == {"worn": True, "rating": 5}


def test_build_sends_evidence_and_schema_and_persists(env):
    uid = _seed(env)
    row = env.c.taste.build(uid)
    assert row["model"] == "fake-opus" and row["profile"]["headline"].startswith("Clean")
    assert row["evidence_counts"]["owned_items"] == 2 and row["facts"]["item_count"] == 2
    assert env.taste_model.schemas[0] is TASTE_SCHEMA
    assert "ASPIRATIONAL" in env.taste_model.prompts[0] and "camel coat" in env.taste_model.prompts[0]
    assert env.c.taste.get(uid)["id"] == row["id"]


def test_latest_profile_wins(env):
    uid = _seed(env)
    env.c.taste.build(uid)
    env.taste_model.answer = {**env.taste_model.answer, "headline": "v2"}
    env.c.taste.build(uid)
    assert env.c.taste.get(uid)["profile"]["headline"] == "v2"


def test_not_enough_evidence_and_missing_profile(env):
    uid = env.user()["id"]
    with pytest.raises(Conflict):
        env.c.taste.ensure_enough(uid)
    with pytest.raises(NotFound):
        env.c.taste.get(uid)


# ---------- API ----------
def test_api_taste_profile_job_flow(client, env):
    uid = client.post("/users", json={"name": "Dan"}).json()["id"]
    assert client.post(f"/users/{uid}/taste-profile").status_code == 409
    assert client.get(f"/users/{uid}/taste-profile").status_code == 404
    client.post(f"/users/{uid}/wardrobe", data={"image_urls": ["https://img/1.jpg", "https://img/2.jpg", "https://img/3.jpg"]})
    assert client.get(f"/users/{uid}/taste-profile/evidence").json()["counts"]["owned_items"] == 3
    job = client.post(f"/users/{uid}/taste-profile").json()
    assert client.get(f"/jobs/{job['job_id']}").json()["status"] == "done"
    assert client.get(f"/users/{uid}/taste-profile").json()["profile"]["confidence"] == 0.6


# ---------- Claude CLI adapter (subprocess faked) ----------
def _runner(stdout: str, record: list):
    def run(cmd, **kw):
        record.append((cmd, kw))
        return SimpleNamespace(stdout=stdout, stderr="", returncode=0)
    return run


def test_claude_cli_returns_structured_output_and_drops_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "bad")
    calls = []
    cli = ClaudeCLI("claude-opus-5-5", runner=_runner(json.dumps({"is_error": False, "structured_output": {"a": 1}}), calls))
    assert cli.generate("hello", {"type": "object"}) == {"a": 1}
    cmd, kw = calls[0]
    assert cmd[:4] == ["claude", "-p", "--model", "claude-opus-5-5"] and "--json-schema" in cmd
    assert kw["input"] == "hello" and "ANTHROPIC_API_KEY" not in kw["env"]


@pytest.mark.parametrize("stdout", ["not json", json.dumps({"is_error": True, "result": "Invalid API key"}),
                                    json.dumps({"is_error": False, "result": "text only"})])
def test_claude_cli_errors(stdout):
    with pytest.raises(ClaudeCLIError):
        ClaudeCLI(runner=_runner(stdout, [])).generate("x", {})

"""Explore/exploit swipe deck: priors from user evidence, bandit updates, never re-serving pins, boards."""
import random

from backend.app.services.style_deck import StyleBelief, beliefs, next_pins, prior

OLD_MONEY = {"id": "s1", "name": "Old Money", "aliases": ["quiet luxury"], "key_pieces": ["cashmere sweater", "loafers"]}
GORPCORE = {"id": "s2", "name": "Gorpcore", "key_pieces": ["fleece", "hiking boots"]}
BOHO = {"id": "s3", "name": "Bohemian", "aliases": ["boho"], "key_pieces": ["maxi dress"]}


def _pins(style_id, n):
    return [{"id": f"{style_id}-{i}", "style_id": style_id, "title": f"look {i}", "image_url": f"u{i}"} for i in range(n)]


# ---------- pure bandit ----------
def test_prior_uses_taste_instagram_and_explicit_feedback():
    ctx_terms = [("Old Money", 1.0, "taste profile (aspirational)"), ("gorpcore", -0.8, "taste profile (avoid)")]
    m_old, why = prior(OLD_MONEY, ctx_terms, None)
    m_gorp, _ = prior(GORPCORE, ctx_terms, None)
    m_boho, _ = prior(BOHO, ctx_terms, None)
    assert m_old > 0.8 and m_gorp < 0.25 and m_boho == 0.5
    assert why == ["taste profile (aspirational)"]
    assert prior(BOHO, ctx_terms, False)[0] < 0.1 and prior(BOHO, [], True)[0] > 0.85


def test_swipes_update_beliefs():
    pins = {p["id"]: p for p in _pins("s1", 3) + _pins("s2", 3)}
    swipes = [{"pin_id": "s1-0", "liked": True}, {"pin_id": "s1-1", "liked": True}, {"pin_id": "s2-0", "liked": False}]
    b = beliefs([OLD_MONEY, GORPCORE], pins, swipes, {})
    assert (b["s1"].likes, b["s2"].dislikes) == (2, 1)
    assert b["s1"].mean > 0.5 > b["s2"].mean


def test_explore_targets_uncertainty_and_exploit_targets_likes():
    known = StyleBelief("s1", "Old Money", 0.5, likes=8, dislikes=1)     # well known, liked
    unknown = StyleBelief("s2", "Gorpcore", 0.5)                          # never swiped
    state, unseen = {"s1": known, "s2": unknown}, {"s1": _pins("s1", 5), "s2": _pins("s2", 5)}
    explore = next_pins(state, unseen, 1, explore=1.0, liked_terms=set(), rng=random.Random(0))
    exploit = next_pins(state, unseen, 1, explore=0.0, liked_terms=set(), rng=random.Random(0))
    assert (explore[0]["style_id"], explore[0]["mode"]) == ("s2", "explore")
    assert (exploit[0]["style_id"], exploit[0]["mode"]) == ("s1", "exploit")
    assert "liked 8 of 9" in exploit[0]["reason"] and "Exploring Gorpcore" in explore[0]["reason"]


def test_half_explore_half_exploit_and_batch_spans_styles():
    state = {s["id"]: StyleBelief(s["id"], s["name"]) for s in (OLD_MONEY, GORPCORE, BOHO)}
    unseen = {sid: _pins(sid, 40) for sid in state}
    out = next_pins(state, unseen, 60, explore=0.5, liked_terms=set(), rng=random.Random(1))
    explore = sum(p["mode"] == "explore" for p in out)
    assert 20 <= explore <= 40
    assert len({p["style_id"] for p in out[:3]}) == 3
    assert len({p["id"] for p in out}) == 60


def test_exploit_prefers_pins_like_liked_ones():
    state = {"s1": StyleBelief("s1", "Old Money")}
    pins = [{"id": "a", "style_id": "s1", "title": "beach party"}, {"id": "b", "style_id": "s1", "title": "navy blazer loafers"}]
    out = next_pins(state, {"s1": pins}, 1, explore=0.0, liked_terms={"loafer", "blazer"}, rng=random.Random(0))
    assert out[0]["id"] == "b"


# ---------- service ----------
def _library(env, n=6):
    env.pins.n = n
    env.c.styles.refresh(["old money", "gorpcore", "boho"], n)


def test_deck_never_reserves_and_swipes_keep_the_mode(env):
    _library(env)
    uid = env.user()["id"]
    first = env.c.preferences.deck(uid, 5, seed=1)
    second = env.c.preferences.deck(uid, 50, seed=2)
    assert not {p["id"] for p in first} & {p["id"] for p in second}
    assert len(first) + len(second) == 18 and env.c.preferences.deck(uid, 5) == []
    env.c.preferences.record(uid, [{"pin_id": first[0]["id"], "liked": True, "source": None}])
    assert env.c.preferences.board(uid)[0]["mode"] == first[0]["mode"]


def test_boards_split_interested_and_not_and_stay_out_of_wardrobe(env):
    _library(env)
    uid = env.user()["id"]
    a, b = env.c.preferences.deck(uid, 2, seed=0)
    env.c.preferences.record(uid, [{"pin_id": a["id"], "liked": True}, {"pin_id": b["id"], "liked": False,
                                                                        "source": "recommendations"}])
    yes, no = env.c.preferences.board(uid, True), env.c.preferences.board(uid, False)
    assert [r["pin_id"] for r in yes] == [a["id"]] and [r["pin_id"] for r in no] == [b["id"]]
    assert no[0]["source"] == "recommendations" and yes[0]["style_name"] in ("old money", "gorpcore", "boho")
    assert env.c.wardrobe.list(uid, status=None) == []


def test_likes_steer_exploit_towards_that_style(env):
    _library(env, 10)
    uid = env.user()["id"]
    styles = {s["name"]: s["id"] for s in env.c.styles.list()}
    gorp_pins = [p for p in env.db.tables["style_pins"] if p["style_id"] == styles["gorpcore"]][:3]
    env.c.preferences.record(uid, [{"pin_id": p["id"], "liked": True} for p in gorp_pins])
    picks = env.c.preferences.deck(uid, 3, explore=0.0, seed=0)
    assert picks[0]["style_name"] == "gorpcore" and picks[0]["mode"] == "exploit"
    top = env.c.preferences.beliefs(uid)[0]
    served = sum(p["style_name"] == "gorpcore" for p in picks)
    assert top["name"] == "gorpcore" and top["likes"] == 3 and top["unseen_pins"] == 10 - 3 - served


def test_prior_reads_inspirations_and_style_feedback(env):
    _library(env)
    uid = env.user()["id"]
    styles = {s["name"]: s["id"] for s in env.c.styles.list()}
    env.db.insert("inspirations", {"user_id": uid, "style_tags": ["boho", "boho"]})
    env.db.insert("user_style_feedback", {"user_id": uid, "style_id": styles["gorpcore"], "interested": False})
    b = {r["name"]: r for r in env.c.preferences.beliefs(uid)}
    assert b["boho"]["prior"] > 0.5 and "inspiration looks" in b["boho"]["prior_from"]
    assert b["gorpcore"]["prior"] < 0.1 and b["old money"]["prior"] == 0.5


def test_audience_filters_styles(env):
    _library(env)
    uid = env.user(fit_prefs={"audience": "menswear"})["id"]
    for s in env.db.tables["styles"]:
        s["audience"] = "womenswear" if s["name"] == "boho" else "unisex"
    assert {r["name"] for r in env.c.preferences.beliefs(uid)} == {"old money", "gorpcore"}


# ---------- API ----------
def test_api_deck_next_styles_beliefs_and_boards(client, env):
    _library(env)
    uid = client.post("/users", json={"name": "Dan"}).json()["id"]
    deck = client.get(f"/users/{uid}/swipe-deck?n=4&seed=3").json()
    assert {"id", "image_url", "title", "style_id", "style_name", "mode", "p_like", "reason"} <= set(deck[0])
    picks = client.get(f"/users/{uid}/next-styles?k=3&explore=0").json()
    assert {p["mode"] for p in picks} == {"exploit"} and not {p["id"] for p in picks} & {p["id"] for p in deck}
    client.post(f"/users/{uid}/swipes", json=[{"pin_id": deck[0]["id"], "liked": True}])
    assert len(client.get(f"/users/{uid}/swipes?liked=true").json()) == 1
    assert client.get(f"/users/{uid}/swipes?liked=false").json() == []
    assert len(client.get(f"/users/{uid}/style-beliefs").json()) == 3
    assert client.get(f"/users/{uid}/swipe-deck?explore=2").status_code == 422
    assert client.post(f"/users/{uid}/swipes", json=[{"pin_id": "x", "liked": True, "source": "tiktok"}]).status_code == 422


# ---------- filling pins for library styles ----------
def test_fill_pins_attaches_to_existing_styles_without_new_rows(env):
    a = env.db.insert("styles", {"name": "Old Money", "query": "old money", "search_term": "old money", "status": "active"})
    env.db.insert("styles", {"name": "Retired", "query": "x", "status": "rejected"})
    out = env.c.styles.fill_pins(3)
    assert out["styles_filled"] == 1 and env.pins.queries == ["old money outfit"]
    assert len(env.db.tables["styles"]) == 2 and {p["style_id"] for p in env.db.tables["style_pins"]} == {a["id"]}
    assert env.c.styles.fill_pins(3)["styles_filled"] == 0                  # already has enough
    assert env.c.styles.fill_pins(3, only_missing=False)["styles_filled"] == 1


def test_fill_pins_endpoint_runs_as_job(client, env):
    env.db.insert("styles", {"name": "Gorpcore", "query": "gorpcore", "status": "active"})
    job = client.post("/styles/pins/fill", json={"per_style": 2}).json()
    assert client.get(f"/jobs/{job['job_id']}").json()["result"]["pins"] == 2

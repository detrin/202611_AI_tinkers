from datetime import date

import pytest

from backend.app.domain import ImageInput
from backend.app.errors import Conflict, Invalid, NotFound


# ---------- users & images ----------
def test_selfie_stores_image_and_saves_color_profile(env):
    uid = env.user()["id"]
    profile = env.c.users.analyse_selfie(uid, ImageInput(b"face", "image/png"))
    assert profile["season"] == "Soft Autumn"
    assert env.c.users.get(uid)["color_profile"] == profile
    assert any(p.startswith(f"{uid}/selfie/") and p.endswith(".png") for p in env.store.objects)


def test_unknown_user_raises_not_found(env):
    with pytest.raises(NotFound):
        env.c.users.get("missing")


def test_image_from_url_wraps_fetch_errors(env):
    env.fetcher.fail = True
    with pytest.raises(Invalid):
        env.c.images.from_url("https://x/y.jpg")


# ---------- wardrobe ----------
def test_add_items_tags_stores_and_signs(env):
    uid = env.user()["id"]
    items = env.items(uid, 2)
    assert [i["subtype"] for i in items] == ["t-shirt", "t-shirt"]
    assert all(i["image_url"].startswith("https://signed/") for i in items)
    assert len(env.store.objects) == 2


def test_wardrobe_filters_by_category_and_color(env):
    uid = env.user()["id"]
    env.items(uid, 1)
    env.chat.answers["tag"] = {**env.chat.answers["tag"], "category": "shoes", "colors": ["black"]}
    env.items(uid, 1)
    assert len(env.c.wardrobe.list(uid, category="shoes")) == 1
    assert len(env.c.wardrobe.list(uid, color="white")) == 1


def test_wardrobe_is_scoped_per_user(env):
    a, b = env.user()["id"], env.user()["id"]
    item = env.items(a, 1)[0]
    with pytest.raises(NotFound):
        env.c.wardrobe.get(b, item["id"])


def test_update_and_delete_item(env):
    uid = env.user()["id"]
    item = env.items(uid, 1)[0]
    assert env.c.wardrobe.update(uid, item["id"], {"subtype": "polo"})["subtype"] == "polo"
    env.c.wardrobe.delete(uid, item["id"])
    assert env.c.wardrobe.list(uid) == []


# ---------- styles & preferences ----------
def test_refresh_styles_is_idempotent(env):
    env.c.styles.refresh(["old money"], 3)
    env.c.styles.refresh(["old money"], 3)
    assert len(env.c.styles.list()) == 1
    assert len(env.db.tables["style_pins"]) == 3


def test_swipe_deck_round_robins_and_skips_seen(env):
    env.c.styles.refresh(["a", "b"], 3)
    uid = env.user()["id"]
    deck = env.c.preferences.deck(uid, 4)
    assert len({p["style_id"] for p in deck[:2]}) == 2          # interleaved styles
    env.c.preferences.record(uid, [{"pin_id": deck[0]["id"], "liked": True}])
    assert deck[0]["id"] not in {p["id"] for p in env.c.preferences.deck(uid, 10)}


def test_signals_resolve_style_names(env):
    env.c.styles.refresh(["streetwear"], 2)
    uid = env.user()["id"]
    pins = env.c.preferences.deck(uid, 2)
    env.c.preferences.record(uid, [{"pin_id": pins[0]["id"], "liked": True}, {"pin_id": pins[1]["id"], "liked": False}])
    s = env.c.preferences.signals(uid)
    assert s["liked"][0]["style"] == "streetwear" and len(s["disliked"]) == 1


# ---------- profile ----------
def test_profile_compute_persists_and_latest_wins(env):
    uid = env.user()["id"]
    env.items(uid, 1)
    env.c.profiles.compute(uid)
    env.chat.answers["profile"] = {**env.chat.answers["profile"], "shop_queries": ["new"]}
    env.c.profiles.compute(uid)
    assert env.c.profiles.get(uid)["queries"] == ["new"]
    assert '"t-shirt"' in env.chat.calls[-1][1]                  # wardrobe reached the prompt


def test_profile_get_without_compute_is_not_found(env):
    with pytest.raises(NotFound):
        env.c.profiles.get(env.user()["id"])


# ---------- recommendations ----------
def test_recommendations_need_profile_or_queries(env):
    uid = env.user()["id"]
    with pytest.raises(Conflict):
        env.c.recommendations.queries_for(uid, None)
    assert env.c.recommendations.queries_for(uid, ["x"]) == ["x"]


def test_recommendations_drop_hallucinated_ids_and_foreign_wardrobe_ids(env):
    uid = env.user()["id"]
    item = env.items(uid, 1)[0]
    env.chat.answers["rank"] = [{"id": 1, "reason": "nice", "pairs_with": [item["id"], "ghost"]},
                                {"id": 99, "reason": "fake"}, {"id": "0", "reason": "bad type"}]
    res = env.c.recommendations.create(uid, ["coat"], n=3, per_query=2, marketplaces=["www.etsy.com"])
    recs = env.c.recommendations.get(uid, res["rec_set_id"])
    assert res["count"] == 1
    assert recs[0]["product"]["name"] == "coat 1" and recs[0]["pairs_with"] == [item["id"]]


def test_catalog_dedupes_products_by_url(env):
    uid = env.user()["id"]
    env.c.recommendations.create(uid, ["coat"], n=1, per_query=2, marketplaces=[])
    env.c.recommendations.create(uid, ["coat"], n=1, per_query=2, marketplaces=[])
    assert len(env.db.tables["products"]) == 2


# ---------- links ----------
def test_link_check_scrapes_judges_and_stores(env):
    uid = env.user()["id"]
    res = env.c.links.check(uid, "https://shop/x")
    assert res["score_1to10"] == 7 and res["product"]["name"] == "Linked thing"
    assert env.chat.calls[-1][2] == ["https://shop/x.jpg"]
    assert len(env.c.links.list(uid)) == 1


def test_link_check_unscrapable_url_is_invalid(env):
    with pytest.raises(Invalid):
        env.c.links.check(env.user()["id"], "https://broken")


# ---------- outfits ----------
def test_daily_outfit_keeps_only_owned_items(env):
    uid = env.user()["id"]
    items = env.items(uid, 2)
    env.chat.answers["outfit"] = {"item_ids": [items[0]["id"], "not-mine"], "explanation": "warm"}
    o = env.c.outfits.daily(uid, "office", day=date(2026, 11, 13))
    assert o["item_ids"] == [items[0]["id"]] and o["items"][0]["image_url"]
    assert env.weather.calls == [("Prague", date(2026, 11, 13))]


def test_daily_outfit_passes_recent_items_to_avoid_repeats(env):
    uid = env.user()["id"]
    item = env.items(uid, 1)[0]
    env.chat.answers["outfit"] = {"item_ids": [item["id"]]}
    env.c.outfits.daily(uid, "x")
    env.c.outfits.daily(uid, "y")
    assert item["id"] in env.chat.calls[-1][1].split("Recently worn")[1].split("Wardrobe")[0]


def test_daily_outfit_preconditions(env):
    no_city = env.c.users.create({"name": "x"})["id"]
    with pytest.raises(Invalid):
        env.c.outfits.daily(no_city, "x")
    with pytest.raises(Conflict):
        env.c.outfits.daily(env.user()["id"], "x")


def test_outfit_feedback(env):
    uid = env.user()["id"]
    env.items(uid, 1)
    o = env.c.outfits.daily(uid, "x")
    assert env.c.outfits.feedback(uid, o["id"], {"worn": True})["feedback"] == {"worn": True}


# ---------- jobs ----------
def test_job_success_and_failure_are_recorded(env):
    ok = env.c.jobs.submit("k", None, {}, lambda: {"v": 1})
    bad = env.c.jobs.submit("k", None, {}, lambda: 1 / 0)
    assert env.c.jobs.get(ok["job_id"])["status"] == "done"
    assert env.c.jobs.get(ok["job_id"])["result"] == {"v": 1}
    failed = env.c.jobs.get(bad["job_id"])
    assert failed["status"] == "failed" and "ZeroDivisionError" in failed["error"]

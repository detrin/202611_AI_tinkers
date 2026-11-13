import pytest

from backend.app.domain import ImageInput
from backend.app.errors import Invalid, NotFound


def _product(env, uid):
    env.c.recommendations.create(uid, ["coat"], n=1, per_query=1, marketplaces=[])
    return env.db.tables["products"][0]


# ---------- owned vs wanted ----------
def test_items_default_to_owned_and_lists_split_by_status(env):
    uid = env.user()["id"]
    env.items(uid, 1)
    env.c.wardrobe.add(uid, [ImageInput(b"wish")], status="wanted")
    assert [i["status"] for i in env.c.wardrobe.list(uid)] == ["owned"]
    assert [i["status"] for i in env.c.wardrobe.list(uid, "wanted")] == ["wanted"]
    assert len(env.c.wardrobe.list(uid, None)) == 2


def test_invalid_status_rejected(env):
    uid = env.user()["id"]
    with pytest.raises(Invalid):
        env.c.wardrobe.add(uid, [ImageInput(b"x")], status="borrowed")


def test_mark_owned_flips_status_without_retagging(env):
    uid = env.user()["id"]
    item = env.c.wardrobe.add(uid, [ImageInput(b"wish")], status="wanted")[0]
    tag_calls = sum(k == "tag" for k, *_ in env.chat.calls)
    assert env.c.wardrobe.mark_owned(uid, item["id"])["status"] == "owned"
    assert sum(k == "tag" for k, *_ in env.chat.calls) == tag_calls


def test_daily_outfit_ignores_wanted_items(env):
    uid = env.user()["id"]
    wanted = env.c.wardrobe.add(uid, [ImageInput(b"wish")], status="wanted")[0]
    owned = env.items(uid, 1)[0]
    env.chat.answers["outfit"] = {"item_ids": [wanted["id"], owned["id"]]}
    assert env.c.outfits.daily(uid, "office")["item_ids"] == [owned["id"]]


def test_liked_product_becomes_wanted_item_linked_to_product(env):
    uid = env.user()["id"]
    p = _product(env, uid)
    res = env.c.feedback.record(uid, p["id"], liked=True, bought=False)
    item = env.c.wardrobe.get(uid, res["item_id"])
    assert (item["status"], item["product_id"]) == ("wanted", p["id"])


def test_buying_a_wanted_product_flips_the_same_item(env):
    uid = env.user()["id"]
    p = _product(env, uid)
    wanted = env.c.feedback.record(uid, p["id"], liked=True, bought=False)
    fetches = len(env.fetcher.calls)
    bought = env.c.feedback.record(uid, p["id"], liked=True, bought=True)
    assert bought["item_id"] == wanted["item_id"] and bought["status"] == "owned"
    assert len(env.fetcher.calls) == fetches                      # no re-download
    assert len(env.c.wardrobe.list(uid, None)) == 1


def test_buying_unliked_product_adds_owned_item(env):
    uid = env.user()["id"]
    p = _product(env, uid)
    assert env.c.feedback.record(uid, p["id"], liked=None, bought=True)["status"] == "owned"


def test_profile_prompt_sees_owned_wishlist_and_inspiration(env):
    uid = env.user()["id"]
    env.items(uid, 1)
    env.c.wardrobe.add(uid, [ImageInput(b"wish")], status="wanted")
    env.c.inspirations.add(uid, [ImageInput(b"look")])
    env.c.profiles.compute(uid)
    prompt = env.chat.calls[-1][1]
    assert "owned_items" in prompt and "wishlist_items" in prompt and "camel coat" in prompt


def test_link_verdict_gets_owned_and_wishlist(env):
    uid = env.user()["id"]
    env.c.wardrobe.add(uid, [ImageInput(b"wish")], status="wanted")
    env.c.links.check(uid, "https://shop/x")
    assert '"wishlist": [{' in env.chat.calls[-1][1]


# ---------- inspirations ----------
def test_upload_inspiration_is_tagged_as_a_look(env):
    uid = env.user()["id"]
    look = env.c.inspirations.add(uid, [ImageInput(b"street style")])[0]
    assert look["style_tags"] == ["old money"] and look["pieces"][0]["subtype"] == "camel coat"
    assert look["image_url"].startswith("https://signed/")
    assert any(p.startswith(f"{uid}/inspiration/") for p in env.store.objects)
    assert env.c.wardrobe.list(uid, None) == []                    # a look is not a garment


def test_pin_promotion_records_like_uses_pin_url_and_is_idempotent(env):
    env.c.styles.refresh(["boho"], 2)
    uid = env.user()["id"]
    pin = env.c.preferences.deck(uid, 1)[0]
    first = env.c.inspirations.from_pin(uid, pin["id"])
    again = env.c.inspirations.from_pin(uid, pin["id"])
    assert first["id"] == again["id"] and first["image_url"] == pin["image_url"]
    assert env.chat.calls[-1][2] == [pin["image_url"]] and sum(k == "look" for k, *_ in env.chat.calls) == 1
    assert env.c.preferences.signals(uid)["liked"][0]["style"] == "boho"


def test_inspirations_scoped_per_user_and_deletable(env):
    a, b = env.user()["id"], env.user()["id"]
    look = env.c.inspirations.add(a, [ImageInput(b"x")])[0]
    with pytest.raises(NotFound):
        env.c.inspirations.get(b, look["id"])
    env.c.inspirations.delete(a, look["id"])
    assert env.c.inspirations.list(a) == []


def test_unknown_pin_is_not_found(env):
    with pytest.raises(NotFound):
        env.c.inspirations.from_pin(env.user()["id"], "nope")


# ---------- API ----------
def test_api_wanted_upload_filter_and_buy(client):
    uid = client.post("/users", json={"name": "Dan"}).json()["id"]
    item = client.post(f"/users/{uid}/wardrobe", data={"image_urls": ["https://img/1.jpg"], "status": "wanted"}).json()[0]
    assert client.get(f"/users/{uid}/wardrobe").json() == []
    assert len(client.get(f"/users/{uid}/wardrobe?status=wanted").json()) == 1
    assert client.post(f"/users/{uid}/wardrobe/{item['id']}/buy").json()["status"] == "owned"
    assert len(client.get(f"/users/{uid}/wardrobe?status=all").json()) == 1
    assert client.get(f"/users/{uid}/wardrobe?status=bogus").status_code == 422


def test_api_inspirations_flow(client):
    uid = client.post("/users", json={"name": "Dan"}).json()["id"]
    look = client.post(f"/users/{uid}/inspirations", files=[("files", ("l.jpg", b"x", "image/jpeg"))]).json()[0]
    assert look["vibe"] == "polished"
    client.post("/styles/refresh", json={"queries": ["boho"], "pins_per_style": 1})
    pin = client.get(f"/users/{uid}/swipe-deck").json()[0]
    assert client.post(f"/users/{uid}/inspirations/from-pin", json={"pin_id": pin["id"]}).status_code == 200
    assert len(client.get(f"/users/{uid}/inspirations").json()) == 2
    assert client.delete(f"/users/{uid}/inspirations/{look['id']}").json() == {"deleted": look["id"]}

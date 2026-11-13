"""HTTP layer over in-memory fakes: routing, validation, error mapping, job flow."""


def test_health(client):
    assert client.get("/health").json() == {"ok": True}


def test_user_crud_and_404(client):
    u = client.post("/users", json={"name": "Dan", "city": "Prague"}).json()
    assert client.patch(f"/users/{u['id']}", json={"budget": 100}).json()["budget"] == 100
    r = client.get("/users/missing")
    assert r.status_code == 404 and "users" in r.json()["detail"]


def test_wardrobe_upload_files_and_urls(client, env):
    uid = client.post("/users", json={"name": "Dan"}).json()["id"]
    r = client.post(f"/users/{uid}/wardrobe", files=[("files", ("a.jpg", b"x", "image/jpeg"))],
                    data={"image_urls": ["https://img/1.jpg"]})
    assert r.status_code == 200 and len(r.json()) == 2
    assert env.fetcher.calls == ["https://img/1.jpg"]


def test_wardrobe_upload_requires_input(client):
    uid = client.post("/users", json={"name": "Dan"}).json()["id"]
    assert client.post(f"/users/{uid}/wardrobe").status_code == 422


def test_item_patch_validates_ranges(client):
    uid = client.post("/users", json={"name": "Dan"}).json()["id"]
    item = client.post(f"/users/{uid}/wardrobe", data={"image_urls": ["https://img/1.jpg"]}).json()[0]
    assert client.patch(f"/users/{uid}/wardrobe/{item['id']}", json={"formality": 9}).status_code == 422
    assert client.patch(f"/users/{uid}/wardrobe/{item['id']}", json={"formality": 4}).json()["formality"] == 4


def test_recommendation_job_flow(client):
    uid = client.post("/users", json={"name": "Dan"}).json()["id"]
    assert client.post(f"/users/{uid}/recommendations", json={}).status_code == 409   # no profile yet
    client.post(f"/users/{uid}/profile/compute")
    job = client.post(f"/users/{uid}/recommendations", json={"n": 2}).json()
    done = client.get(f"/jobs/{job['job_id']}").json()
    assert done["status"] == "done"
    assert client.get(f"/users/{uid}/recommendations/{done['result']['rec_set_id']}").status_code == 200


def test_link_job_for_unknown_user_fails_fast(client):
    assert client.post("/users/nope/links", json={"url": "https://x"}).status_code == 404


def test_styles_refresh_and_swipes(client):
    job = client.post("/styles/refresh", json={"queries": ["boho"], "pins_per_style": 2}).json()
    assert client.get(f"/jobs/{job['job_id']}").json()["status"] == "done"
    uid = client.post("/users", json={"name": "Dan"}).json()["id"]
    deck = client.get(f"/users/{uid}/swipe-deck?n=5").json()
    assert len(deck) == 2
    assert client.post(f"/users/{uid}/swipes", json=[{"pin_id": deck[0]["id"], "liked": True}]).json() == {"saved": 1}
    assert client.post("/styles/refresh", json={"queries": []}).status_code == 422


def test_daily_outfit_endpoint(client):
    uid = client.post("/users", json={"name": "Dan", "city": "Prague"}).json()["id"]
    assert client.post(f"/users/{uid}/outfits/daily", json={"event": "office"}).status_code == 409   # empty wardrobe
    client.post(f"/users/{uid}/wardrobe", data={"image_urls": ["https://img/1.jpg"]})
    r = client.post(f"/users/{uid}/outfits/daily", json={"event": "office", "date": "2026-11-13"})
    assert r.status_code == 200 and r.json()["weather"]["city"] == "Prague"


def test_list_users_and_test_user_lookup(client, env):
    assert client.get("/users/test-user").status_code == 404
    old = client.post("/users", json={"name": "Test User (seed)"}).json()
    client.post("/users", json={"name": "Alice"})
    new = client.post("/users", json={"name": "Test User (seed)", "city": "Prague"}).json()
    assert client.get("/users/test-user").json()["id"] == new["id"] != old["id"]     # latest seed wins
    assert [u["name"] for u in client.get("/users?name=alice").json()] == ["Alice"]
    rows = client.get("/users?limit=2").json()
    assert len(rows) == 2 and set(rows[0]) == {"id", "name", "city", "created_at"}


def test_demo_user_lookup(client):
    assert client.get("/users/demo-user").status_code == 404
    client.post("/users", json={"name": "Test User (seed)"})
    demo = client.post("/users", json={"name": "Demo User"}).json()
    assert client.get("/users/demo-user").json()["id"] == demo["id"]

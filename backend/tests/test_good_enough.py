URL = "/users/{}/is-it-good-enough"
PHOTO = {"file": ("look.jpg", b"look-photo", "image/jpeg")}


def _post(client, uid, **data):
    return client.post(URL.format(uid), files=PHOTO, data=data)


def test_no_location_means_no_weather_and_no_wardrobe(client, env):
    uid = env.user()["id"]
    env.items(uid)
    r = _post(client, uid)
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "hell yeah" and body["good_enough"] is True and body["explanation"] == "Sharp."
    assert body["weather"] is None and body["weather_note"] is None and body["location_source"] is None
    assert body["used_wardrobe"] is False
    kind, prompt, images = env.chat.calls[-1]
    assert kind == "good_enough" and images[0].startswith("data:image/jpeg;base64,")
    assert '"weather": null' in prompt and '"wardrobe"' not in prompt
    assert not [c for c in env.weather.calls if c[0] == "now"]


def test_current_position_wins_over_city(client, env):
    uid = env.user()["id"]
    body = _post(client, uid, latitude="50.08", longitude="14.42", city="Berlin").json()
    assert env.weather.calls[-1] == ("now", None, 50.08, 14.42)
    assert body["location_source"] == "coordinates" and body["weather"]["current"]["temperature_2m"] == 4


def test_saved_city_only_when_asked(client, env):
    uid = env.user()["id"]
    assert _post(client, uid).json()["weather"] is None
    body = _post(client, uid, use_saved_city="true").json()
    assert env.weather.calls[-1] == ("now", "Prague", None, None) and body["location_source"] == "city"


def test_hell_nah_and_wardrobe_opt_in_filters_unknown_ids(client, env):
    uid = env.user()["id"]
    item_id = env.items(uid, 1)[0]["id"]
    env.chat.answers["good_enough"] = {"good_enough": "false", "explanation": "Too cold for that.",
                                       "swap_item_ids": [item_id, "made-up"]}
    body = _post(client, uid, include_wardrobe="true", occasion="date night").json()
    assert body["verdict"] == "hell nah" and body["good_enough"] is False
    assert body["swap_item_ids"] == [item_id] and body["used_wardrobe"] is True
    prompt = env.chat.calls[-1][1]
    assert '"wardrobe"' in prompt and item_id in prompt and "date night" in prompt


def test_weather_failure_still_judges(client, env):
    uid = env.user()["id"]
    body = _post(client, uid, city="Atlantis").json()
    assert body["verdict"] == "hell yeah" and body["weather"] is None


def test_validation(client, env):
    uid = env.user()["id"]
    assert client.post(URL.format(uid)).status_code == 422          # no photo
    assert _post(client, uid, latitude="50").status_code == 422     # half a coordinate
    assert _post(client, uid, latitude="500", longitude="1").status_code == 422


def test_points_are_title_detail_pairs_capped_at_three(client, env):
    uid = env.user()["id"]
    env.chat.answers["good_enough"] = {"good_enough": False, "explanation": "No.",
                                       "fixes": ["Tuck it in", {"title": "Darker shoes", "detail": "Grounds it"},
                                                 {"title": " "}, "a", "b"],
                                       "highlights": "not a list"}
    body = _post(client, uid).json()
    assert body["fixes"] == [{"title": "Tuck it in", "detail": ""}, {"title": "Darker shoes", "detail": "Grounds it"},
                             {"title": "a", "detail": ""}]
    assert body["highlights"] == []

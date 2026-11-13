from datetime import date
from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app.adapters.calendar import ICalCalendar
from backend.app.adapters.executors import InlineExecutor
from backend.app.container import build_services
from backend.app.main import create_app

from .conftest import Env

DAY = date(2026, 11, 13)
HEADERS = {"Authorization": "Bearer demo-test-token"}


class Calendar:
    def events(self, uid, day, timezone):
        assert day == DAY and timezone == "Europe/Prague"
        return [{"title": "Dinner", "start_time": "2026-11-13T18:30:00+01:00",
                 "end_time": "2026-11-13T21:00:00+01:00", "location": "Café Savoy"}]


class Weather:
    def hourly(self, city, day, timezone):
        assert (city, day, timezone) == ("Prague", DAY, "Europe/Prague")
        return {"city": city, "hourly": [
            {"time": "2026-11-13T12:00:00+01:00", "temperature_c": 14, "rain_probability": 0},
            {"time": "2026-11-13T19:00:00+01:00", "temperature_c": 5, "rain_probability": 0.7},
        ]}


def today_client(env, *, calendar=None, weather=None, venue=None):
    container = build_services(
        db=env.db, store=env.store, fetcher=env.fetcher, chat=env.chat, pins=env.pins,
        products=env.products, social=env.social, weather=env.weather, taste_model=env.taste_model,
        aesthetics=env.aesthetics, trends=env.trends, executor=InlineExecutor(),
        calendar=calendar, hourly_weather=weather, venue=venue, today_api_token="demo-test-token",
    )
    return TestClient(create_app(lambda: container))


def test_today_uses_event_hour_and_only_owned_available_items(env):
    uid = env.user(fit_prefs={"commute_mode": "metro"})["id"]
    available, laundry, lent, stored, wanted = env.items(uid, n=5)
    foreign = env.items(env.user()["id"], n=1)[0]
    for item, status in [(laundry, "laundry"), (lent, "lent"), (stored, "stored")]:
        env.c.wardrobe.update(uid, item["id"], {"availability": status})
    env.c.wardrobe.update(uid, wanted["id"], {"status": "wanted"})
    env.chat.answers["outfit"] = {
        "item_ids": [item["id"] for item in (available, laundry, lent, stored, wanted, foreign, available)],
        "explanation": "Wear an extra layer for the trip to dinner.",
    }

    with today_client(env, calendar=Calendar(), weather=Weather()) as client:
        response = client.post(f"/users/{uid}/outfits/today", json={"date": DAY.isoformat()}, headers=HEADERS)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["item_ids"] == [available["id"]]
    assert result["items"][0]["image_url"].startswith("https://signed/")
    assert result["context"]["weather"]["temperature_c"] == 5
    assert result["context"]["events"][0]["weather"]["rain_probability"] == 0.7
    assert result["context"]["commute"] == {"mode": "metro"}
    assert result["from_fallback"] is False
    assert len(result["steps"]) == 5
    assert len(env.db.select("outfits", {"user_id": uid})) == 1


def test_today_falls_back_when_new_picker_and_weather_fail(env, monkeypatch):
    uid = env.user()["id"]
    available, laundry = env.items(uid)
    env.c.wardrobe.update(uid, laundry["id"], {"availability": "laundry"})
    env.chat.answers["outfit"] = {"item_ids": [laundry["id"], available["id"]], "explanation": "Wear this."}
    complete = env.chat.complete

    def fail_today(prompt, images=()):
        if "venue_event_index" in prompt:
            raise ConnectionError("Today's picker failed")
        return complete(prompt, images)

    class FailedWeather:
        def hourly(self, city, day, timezone):
            raise ConnectionError("Forecast unavailable")

    monkeypatch.setattr(env.chat, "complete", fail_today)
    with today_client(env, weather=FailedWeather()) as client:
        response = client.post(f"/users/{uid}/outfits/today", json={"note": "Office meeting"}, headers=HEADERS)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["from_fallback"] is True
    assert result["item_ids"] == [available["id"]]
    assert result["context"]["weather"] == {}
    assert "Office meeting" in env.chat.calls[-1][1]


def test_today_requires_server_credentials(env):
    uid = env.user()["id"]
    with today_client(env) as client:
        assert client.post(f"/users/{uid}/outfits/today", json={}).status_code == 401
    assert env.db.select("outfits", {"user_id": uid}) == []


def test_today_can_finish_if_venue_lookup_fails(env):
    uid = env.user()["id"]
    item = env.items(uid, n=1)[0]

    class FailedVenue:
        async def category(self, location, city):
            assert (location, city) == ("Café Savoy", "Prague")
            raise ConnectionError("Venue unavailable")

    env.chat.answers["outfit"] = {"item_ids": [item["id"]], "venue_event_index": 0, "explanation": "Wear this."}
    with today_client(env, calendar=Calendar(), venue=FailedVenue()) as client:
        response = client.post(f"/users/{uid}/outfits/today", json={"date": DAY.isoformat()}, headers=HEADERS)

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["item_ids"] == [item["id"]]
    assert result["from_fallback"] is False
    assert result["steps"][-1]["summary"] == "Venue type unavailable"


def test_demo_calendar_limits_access_and_expands_recurring_events():
    feed = b"\r\n".join([
        b"BEGIN:VCALENDAR", b"VERSION:2.0", b"PRODID:-//Good Enough test//EN",
        b"BEGIN:VEVENT", b"UID:weekly", b"DTSTAMP:20261106T090000Z",
        b"DTSTART:20261106T180000Z", b"DTEND:20261106T190000Z", b"RRULE:FREQ=WEEKLY",
        b"SUMMARY:Dinner", b"LOCATION:Caf\xc3\xa9 Savoy", b"END:VEVENT",
        b"BEGIN:VEVENT", b"UID:all-day", b"DTSTAMP:20261106T090000Z",
        b"DTSTART;VALUE=DATE:20261113", b"SUMMARY:All day", b"END:VEVENT",
        b"BEGIN:VEVENT", b"UID:cancelled", b"DTSTAMP:20261106T090000Z",
        b"DTSTART:20261113T120000Z", b"STATUS:CANCELLED", b"SUMMARY:Cancelled", b"END:VEVENT",
        b"END:VCALENDAR", b"",
    ])
    calls = []

    def get(url, **options):
        calls.append(options)
        return SimpleNamespace(status_code=200, content=feed)

    calendar = ICalCalendar("https://example.test/calendar.ics", "demo", SimpleNamespace(get=get))
    assert calendar.events("other-user", DAY, "Europe/Prague") is None
    assert not calls
    assert calendar.events("demo", DAY, "Europe/Prague") == [{
        "title": "Dinner", "start_time": "2026-11-13T19:00:00+01:00",
        "end_time": "2026-11-13T20:00:00+01:00", "location": "Café Savoy",
    }]

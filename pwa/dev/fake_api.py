"""Stand-in backend for UI work: Dan's real FastAPI app wired to in-memory fakes, seeded with a small wardrobe.

No external services needed. Nothing is saved between restarts.

    uv run python pwa/dev/fake_api.py        # from the repo root, serves http://localhost:8000
"""
import io
import itertools
import json
import os
import re
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import uvicorn  # noqa: E402
from fastapi import Response  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from backend.app.adapters.calendar import DemoCalendar, ICalCalendar  # noqa: E402
from backend.app.adapters.executors import InlineExecutor  # noqa: E402
from backend.app.container import build_services  # noqa: E402
from backend.app.domain import ImageInput  # noqa: E402
from backend.app.main import create_app  # noqa: E402
from backend.app.services.stylist import Stylist  # noqa: E402
from backend.app.services.today import TodayService  # noqa: E402
from backend.tests import fakes  # noqa: E402
from backend.tests.fakes_styles import FakeAesthetics, FakeTrends  # noqa: E402

SEED = [  # subtype, category, colour name, rgb, formality, warmth
    ("oxford shirt", "top", "white", (236, 232, 222), 4, 2),
    ("crewneck knit", "top", "navy", (31, 47, 86), 3, 4),
    ("breton top", "top", "blue", (74, 127, 192), 2, 2),
    ("chino pants", "bottom", "beige", (201, 178, 140), 3, 2),
    ("jeans", "bottom", "blue", (60, 90, 140), 2, 3),
    ("wool blazer", "outerwear", "black", (40, 40, 40), 4, 3),
    ("leather loafers", "shoes", "black", (25, 25, 25), 4, 2),
    ("white sneakers", "shoes", "white", (240, 240, 240), 1, 2),
]


def swatch(rgb) -> bytes:
    im = Image.new("RGB", (400, 400), (240, 239, 234))
    ImageDraw.Draw(im).rounded_rectangle([90, 70, 310, 330], 36, fill=rgb)
    out = io.BytesIO()
    im.save(out, "JPEG")
    return out.getvalue()


class Store(fakes.FakeStore):
    def signed_url(self, path):
        return f"/api/_img/{path}"


LOOK_TURNS = itertools.cycle([True, False])


class Chat(fakes.ScriptedChat):
    """Like the scripted fake, but the outfit is a real pick from the wardrobe in the prompt."""

    def complete(self, prompt, images=()):
        if self.kind(prompt) == "good_enough":
            return json.dumps(self.look_verdict(prompt, images))
        if self.kind(prompt) != "outfit":
            return super().complete(prompt, images)
        venue_index = None
        if "venue_event_index" in prompt:
            context = json.loads(prompt.splitlines()[1])
            wardrobe = context["wardrobe"]
            if "You may request one venue lookup" in prompt:
                venue_index = next((i for i, event in enumerate(context["events"]) if event.get("location")), None)
        else:
            wardrobe = json.loads(re.search(r"Wardrobe: (\[.*\])$", prompt, re.M).group(1))
        avoid = set(re.findall(r"[0-9a-f-]{36}", prompt.split("different combination", 1)[1].split("Colour profile")[0])) if "different combination" in prompt else set()
        picked = []
        for cat in ("top", "bottom", "outerwear", "shoes"):
            pool = [w for w in wardrobe if w["category"] == cat and (w.get("availability") or "available") == "available"]
            pool.sort(key=lambda w: w["id"] in avoid)
            if pool:
                picked.append(pool[0])
        names = ", ".join(w["subtype"] for w in picked)
        return json.dumps({"item_ids": [w["id"] for w in picked],
                           "explanation": f"Demo stylist picked: {names}.",
                           "missing_item_tip": "a waterproof coat", "venue_event_index": venue_index})


    @staticmethod
    def look_verdict(prompt, images):
        """Alternates hell yeah / hell nah on each first check, so both can be seen. A closet re-check stays nah."""
        has_weather = '"weather": null' not in prompt
        has_closet = '"wardrobe"' in prompt
        good = False if has_closet else next(LOOK_TURNS)
        ids = re.findall(r'"id": "([0-9a-f-]{36})"', prompt)[:2]
        if good:
            return {"good_enough": True, "score_1to10": 8,
                    "explanation": "Clean lines, and the colours sit well together.",
                    "highlights": [{"title": "Trouser length is right", "detail": "A clean break over the shoes"},
                                   {"title": "Calm palette", "detail": "Navy and beige never argue"}],
                    "fixes": [], "weather_note": "Warm enough for 6°C" if has_weather else "", "swap_item_ids": []}
        fixes = ([{"title": "Change into the oxford shirt", "detail": "Crisper than the top you have on"},
                  {"title": "Swap to the crewneck knit", "detail": "Warmer, and navy calms the red"}]
                 if has_closet else
                 [{"title": "Tuck the top in at the front", "detail": "Shows the waist, less boxy"},
                  {"title": "Darker trousers", "detail": "The green fights the red top"},
                  {"title": "Add a layer", "detail": "It is 6°C and you will be cold"}])
        return {"good_enough": False, "score_1to10": 4,
                "explanation": "The top fights the trousers and the shape reads boxy.",
                "highlights": [{"title": "Shoes work", "detail": "Simple and dark"}], "fixes": fixes,
                "weather_note": "Cold for this, take a coat" if has_weather else "",
                "swap_item_ids": ids if has_closet else []}


class Weather(fakes.FakeWeather):
    def hourly(self, city, day, timezone):
        zone = ZoneInfo(timezone)
        return {"city": city, "hourly": [
            {"time": datetime(day.year, day.month, day.day, hour, tzinfo=zone).isoformat(),
             "temperature_c": 8 if hour < 17 else 5, "rain_probability": 0.1 if hour < 17 else 0.8}
            for hour in range(24)
        ]}


class Venue:
    async def category(self, location, city):
        return "Restaurant" if (location, city) == ("Café Savoy", "Prague") else None


store, chat, db, weather = Store(), Chat(), fakes.InMemoryDatabase(), Weather()
services = build_services(db=db, store=store, fetcher=fakes.FakeFetcher(), chat=chat, pins=fakes.FakePins(),
                          products=fakes.FakeProducts(), social=fakes.FakeSocial(), weather=weather,
                          taste_model=fakes.FakeTasteModel(), aesthetics=FakeAesthetics(), trends=FakeTrends(),
                          executor=InlineExecutor())
user = services.users.create({"name": "Demo (fake data)", "city": "Prague"})
for subtype, category, colour, rgb, formality, warmth in SEED:
    chat.answers["tag"] = {"category": category, "subtype": subtype, "colors": [colour], "pattern": "solid",
                           "material": "cotton", "fit": "regular", "formality_1to5": formality, "warmth_1to5": warmth}
    services.wardrobe.add(user["id"], [ImageInput(swatch(rgb))])

calendar_url = os.environ.get("CALENDAR_ICS_URL")
calendar = ICalCalendar(calendar_url, user["id"]) if calendar_url else DemoCalendar(user["id"])
services = replace(
    services,
    today=TodayService(services.users, services.outfits, Stylist(chat), calendar, weather, Venue(), "Europe/Prague"),
    today_api_token=os.environ.get("TODAY_API_TOKEN"),
)
app = create_app(lambda: services)


@app.get("/_img/{path:path}")
def image(path: str):
    return Response(store.objects.get(path, b""), media_type="image/jpeg")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n  Fake API on http://localhost:{port}   user id: {user['id']}\n", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

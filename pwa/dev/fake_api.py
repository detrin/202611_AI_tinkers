"""Stand-in backend for UI work: Dan's real FastAPI app wired to in-memory fakes, seeded with a small wardrobe.

No Supabase, Featherless or Apify needed. Nothing is saved between restarts.

    uv run python pwa/dev/fake_api.py        # from the repo root, serves http://localhost:8000
"""
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import uvicorn  # noqa: E402
from fastapi import Response  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from backend.app.adapters.executors import InlineExecutor  # noqa: E402
from backend.app.container import build_services  # noqa: E402
from backend.app.domain import ImageInput  # noqa: E402
from backend.app.main import create_app  # noqa: E402
from backend.tests import fakes  # noqa: E402

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


class Chat(fakes.ScriptedChat):
    """Like the scripted fake, but the outfit is a real pick from the wardrobe in the prompt."""

    def complete(self, prompt, images=()):
        if self.kind(prompt) != "outfit":
            return super().complete(prompt, images)
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
                           "explanation": f"Fake stylist picked: {names}. It suits a cool, rainy day. It fits the occasion you entered.",
                           "missing_item_tip": "a waterproof coat"})


store, chat, db = Store(), Chat(), fakes.InMemoryDatabase()
services = build_services(db=db, store=store, fetcher=fakes.FakeFetcher(), chat=chat, pins=fakes.FakePins(),
                          products=fakes.FakeProducts(), social=fakes.FakeSocial(), weather=fakes.FakeWeather(),
                          taste_model=fakes.FakeTasteModel(), executor=InlineExecutor())
user = services.users.create({"name": "Demo (fake data)", "city": "Prague"})
for subtype, category, colour, rgb, formality, warmth in SEED:
    chat.answers["tag"] = {"category": category, "subtype": subtype, "colors": [colour], "pattern": "solid",
                           "material": "cotton", "fit": "regular", "formality_1to5": formality, "warmth_1to5": warmth}
    services.wardrobe.add(user["id"], [ImageInput(swatch(rgb))])

app = create_app(lambda: services)


@app.get("/_img/{path:path}")
def image(path: str):
    return Response(store.objects.get(path, b""), media_type="image/jpeg")


if __name__ == "__main__":
    print(f"\n  Fake API on http://localhost:8000   user id: {user['id']}\n", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")

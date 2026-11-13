"""In-memory implementations of every port — unit tests never touch the network."""
import copy
import itertools
import json
import uuid
from datetime import date, datetime, timedelta, timezone

from backend.app.domain import Pin, Product

_clock = itertools.count()
_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


class InMemoryDatabase:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}

    def _t(self, table):
        return self.tables.setdefault(table, [])

    @staticmethod
    def _match(row, where):
        return all(row.get(k) == v for k, v in (where or {}).items())

    def insert(self, table, row):
        row = {"id": str(uuid.uuid4()), "created_at": (_EPOCH + timedelta(seconds=next(_clock))).isoformat(), **row}
        self._t(table).append(row)
        return copy.deepcopy(row)

    def upsert(self, table, rows, on_conflict):
        keys = on_conflict.split(",")
        out = []
        for row in rows:
            existing = next((r for r in self._t(table) if all(r.get(k) == row.get(k) for k in keys)), None)
            if existing:
                existing.update(row)
                out.append(copy.deepcopy(existing))
            else:
                out.append(self.insert(table, row))
        return out

    def update(self, table, where, patch):
        hits = [r for r in self._t(table) if self._match(r, where)]
        for r in hits:
            r.update(patch)
        return copy.deepcopy(hits)

    def delete(self, table, where):
        self.tables[table] = [r for r in self._t(table) if not self._match(r, where)]

    def select(self, table, where=None, *, contains=None, in_=None, order_by=None, desc=False, limit=None):
        rows = [r for r in self._t(table) if self._match(r, where)]
        rows = [r for r in rows if all(set(v) <= set(r.get(k) or []) for k, v in (contains or {}).items())]
        rows = [r for r in rows if all(r.get(k) in v for k, v in (in_ or {}).items())]
        if order_by:
            rows.sort(key=lambda r: (r.get(order_by) is None, r.get(order_by)), reverse=desc)
        return copy.deepcopy(rows[:limit] if limit else rows)


class FakeStore:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put(self, path, content, mime):
        self.objects[path] = content

    def signed_url(self, path):
        return f"https://signed/{path}"


class FakeFetcher:
    def __init__(self, fail: bool = False):
        self.fail, self.calls = fail, []

    def fetch(self, url):
        self.calls.append(url)
        if self.fail:
            raise ConnectionError("boom")
        return b"img:" + url.encode()


class ScriptedChat:
    """Answers by prompt type. Override with chat.answers[kind] = obj (JSON-dumped) or str (raw)."""

    KINDS = {"tag": "Identify the single main", "color": "seasonal colour analysis", "style": "Pinterest reference",
             "profile": "Build the user's style profile", "rank": "Candidate products",
             "verdict": "Judge whether this product", "outfit": "Build the best outfit"}

    def __init__(self):
        self.calls: list[tuple[str, str, list]] = []
        self.answers = {
            "tag": {"category": "top", "subtype": "t-shirt", "colors": ["white"], "pattern": "solid",
                    "material": "cotton", "formality_1to5": 2, "warmth_1to5": 1, "style_tags": ["casual"]},
            "color": {"season": "Soft Autumn", "best_colors": ["olive"], "avoid_colors": ["neon"]},
            "style": {"key_items": ["trench"], "palette": ["beige"], "vibe": "calm"},
            "profile": {"style_mix": [{"style": "minimal", "percent": 100, "why": "x"}], "taste_summary": "clean",
                        "wardrobe_gaps": [{"item": "coat", "why": "cold"}], "shop_queries": ["beige coat", "loafers"]},
            "rank": [],
            "verdict": {"score_1to10": 7, "pairs_with": [], "redundant_with": [], "verdict": "good"},
            "outfit": {"item_ids": [], "explanation": "fine", "missing_item_tip": ""},
        }

    def kind(self, prompt):
        return next(k for k, marker in self.KINDS.items() if marker in prompt)

    def complete(self, prompt, images=()):
        kind = self.kind(prompt)
        self.calls.append((kind, prompt, list(images)))
        answer = self.answers[kind]
        return answer if isinstance(answer, str) else "```json\n" + json.dumps(answer) + "\n```"


class FakePins:
    def __init__(self, n: int = 3):
        self.n, self.queries = n, []

    def search(self, query, limit):
        self.queries.append(query)
        return [Pin(url=f"https://pin/{query}/{i}", image_url=f"https://img/{query}/{i}.jpg", title=f"{query} {i}")
                for i in range(min(self.n, limit))]


class FakeProducts:
    def __init__(self):
        self.searches, self.detail_urls = [], []

    def search(self, query, marketplaces, limit):
        self.searches.append(query)
        return [Product(url=f"https://shop/{query}/{i}", name=f"{query} {i}", price=10.0 + i, currency="EUR",
                        image_url=f"https://shop/{query}/{i}.jpg") for i in range(limit)]

    def details(self, url):
        self.detail_urls.append(url)
        return [] if "broken" in url else [Product(url=url, name="Linked thing", price=50, currency="EUR",
                                                   image_url=url + ".jpg")]


class FakeWeather:
    def __init__(self):
        self.calls = []

    def daily(self, city, day: date | None = None):
        self.calls.append((city, day))
        return {"city": city, "temperature_2m_max": 8, "temperature_2m_min": 2, "precipitation_probability_max": 90}

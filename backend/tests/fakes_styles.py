"""Fakes for the style library / trends ports. Kept separate from fakes.py to avoid merge churn."""
import json
import re

from backend.app.domain import AestheticPage, TrendSeries

from .fakes import FakeTasteModel

DEFAULT_STYLE = {"aliases": [], "definition": "def", "key_pieces": ["oxford shirt", "chinos", "penny loafers", "tweed blazer"],
                 "palette": ["navy", "camel", "cream"], "materials": ["wool"], "formality_min": 2, "formality_max": 4,
                 "seasons": ["autumn"], "related": [], "audience": "unisex"}


class FakeOpus(FakeTasteModel):
    """One structured model for taste, style definitions and discovery — dispatches on the requested schema."""

    def __init__(self):
        super().__init__()
        self.overrides: dict[str, dict] = {}       # per style name
        self.not_fashion: set[str] = set()
        self.discover_answer = {"new_styles": []}

    def generate(self, prompt, schema):
        props = schema.get("properties", {})
        if "styles" in props:
            self.prompts.append(prompt)
            names = json.loads(re.search(r"REQUESTED: (\[.*?\])\n", prompt).group(1))
            wiki = {p["title"] for p in json.loads(prompt.split("WIKI PAGES: ", 1)[1])}
            return {"styles": [{**DEFAULT_STYLE, "name": n, "search_term": f"{n.lower()} aesthetic",
                                "wiki_title": n if n in wiki else None, "is_fashion_style": n not in self.not_fashion,
                                **self.overrides.get(n, {})} for n in names]}
        if "new_styles" in props:
            self.prompts.append(prompt)
            return self.discover_answer
        return super().generate(prompt, schema)


class FakeAesthetics:
    def __init__(self, known=("Old Money", "Dark Academia", "Gorpcore")):
        self.known, self.calls = set(known), []

    def pages(self, titles):
        self.calls.append(list(titles))
        return [AestheticPage(title=t, url=f"https://wiki/{t}", infobox={"key_colours": "navy"}, fashion_text="tweed")
                for t in titles if t in self.known]


def series(values, rising=()):
    return tuple((f"2026-{(i // 4) + 1:02d}-{(i % 4) * 7 + 1:02d}", v) for i, v in enumerate(values)), tuple(rising)


class FakeTrends:
    def __init__(self):
        self.calls, self.by_term = [], {}

    def interest(self, terms, geo=""):
        self.calls.append((list(terms), geo))
        out = []
        for t in terms:
            points, rising = self.by_term.get(t, series([50] * 52))
            out.append(TrendSeries(term=t, points=points, rising=rising))
        return out

"""Style library: source-grounded style records. Aesthetics Wiki gives the facts, a strong model (Opus) normalises them
into a consistent schema. Styles are fuzzy, so every record keeps its source for attribution and re-grounding."""
from __future__ import annotations

import json

from ..ports import AestheticSource, Database, Row, StructuredModel

BATCH = 10

SEED_STYLES = [
    "Old Money", "Quiet Luxury", "Dark Academia", "Light Academia", "Preppy", "Gorpcore", "Techwear", "Streetwear",
    "Skater", "Normcore", "Minimalism", "Scandinavian", "Coastal Grandmother", "Clean Girl", "Mob Wife",
    "Office Siren", "Balletcore", "Coquette", "Cottagecore", "Bohemian", "Grunge", "Indie Sleaze", "Y2K", "Mod",
    "Punk", "Gothic", "Western", "Workwear", "Blokecore", "Athleisure", "Business Casual", "Eclectic Grandpa",
    "Barbiecore", "Parisian", "E-Boy", "Soft Boy", "Ivy League", "Hipster", "Avant-garde", "Japanese Streetwear",
]

_STR_LIST = {"type": "array", "items": {"type": "string"}}
STYLES_SCHEMA = {"type": "object", "required": ["styles"], "properties": {"styles": {"type": "array", "items": {
    "type": "object",
    "required": ["name", "is_fashion_style", "wiki_title", "aliases", "search_term", "definition", "key_pieces", "audience",
                 "palette", "materials", "formality_min", "formality_max", "seasons", "related"],
    "properties": {
        "name": {"type": "string"}, "is_fashion_style": {"type": "boolean"},
        "wiki_title": {"type": ["string", "null"]}, "aliases": _STR_LIST,
        "search_term": {"type": "string", "description": "the 1-3 word phrase people actually google, e.g. 'old money', 'gorpcore'"},
        "definition": {"type": "string"}, "key_pieces": _STR_LIST,
        "audience": {"type": "string", "enum": ["menswear", "womenswear", "unisex"]}, "palette": _STR_LIST, "materials": _STR_LIST,
        "formality_min": {"type": "integer", "minimum": 1, "maximum": 5},
        "formality_max": {"type": "integer", "minimum": 1, "maximum": 5},
        "seasons": _STR_LIST, "related": _STR_LIST}}}}}

DEFINE = """You maintain a fashion style library. Define each REQUESTED style as a wearable clothing style.
Ground yourself in the WIKI PAGES when one matches (set wiki_title to its exact title, else null); use CONTEXT if given.
Rules:
- name: canonical display name (Title Case). aliases: other names people use.
- search_term: the short phrase people actually type into Google (1-3 words, usually the name itself, e.g.
  "old money", "gorpcore", "mob wife"). Add "aesthetic"/"style" only if the bare name is ambiguous
  ("mod style", "western style", "punk fashion"). Never use long phrases: they have no search volume.
- is_fashion_style: false if it is not really about clothing (music scene, interior, art movement only).
- definition: 1-2 sentences, concrete about clothes.
- key_pieces: 6-10 concrete garments/shoes/accessories as shoppable nouns ("tweed blazer", "penny loafers").
- palette: 4-8 plain colour names. materials: 2-6. seasons from spring/summer/autumn/winter.
- formality 1 (loungewear) .. 5 (black tie). related: other style names.
- audience: menswear / womenswear if the look is clearly worn mostly by one, else unisex.
REQUESTED: {names}
CONTEXT: {context}
WIKI PAGES: {pages}"""


def style_row(s: dict, source: str, source_url: str | None) -> Row:
    return {"name": s["name"], "query": s["search_term"], "search_term": s["search_term"], "status": "active",
            "definition": s["definition"], "key_pieces": s["key_pieces"], "audience": s.get("audience", "unisex"), "palette": s["palette"],
            "materials": s["materials"], "formality_min": s["formality_min"], "formality_max": s["formality_max"],
            "seasons": s["seasons"], "aliases": s["aliases"], "related": s["related"], "source": source,
            "source_url": source_url}


class StyleLibraryService:
    def __init__(self, db: Database, aesthetics: AestheticSource, model: StructuredModel):
        self._db, self._aesthetics, self._model = db, aesthetics, model

    def active(self) -> list[Row]:
        return self._db.select("styles", {"status": "active"}, order_by="name")

    def known_names(self) -> set[str]:
        return {n.lower() for s in self._db.select("styles") for n in [s["name"], *(s.get("aliases") or [])]}

    def define(self, names: list[str], source: str = "aesthetics_wiki", context: dict | None = None) -> list[Row]:
        rows = []
        for i in range(0, len(names), BATCH):
            rows += self._define_batch(names[i:i + BATCH], source, context or {})
        return self._db.upsert("styles", list({r["name"]: r for r in rows}.values()), "name") if rows else []

    def _define_batch(self, names: list[str], source: str, context: dict) -> list[Row]:
        pages = {p.title: p for p in self._aesthetics.pages(names)}
        wiki = [{"title": p.title, "infobox": p.infobox, "fashion_text": p.fashion_text} for p in pages.values()]
        prompt = DEFINE.format(names=json.dumps(names), context=json.dumps({n: context[n] for n in names if n in context}),
                               pages=json.dumps(wiki, ensure_ascii=False))
        styles = self._model.generate(prompt, STYLES_SCHEMA)["styles"]
        return [style_row(s, source, pages[s["wiki_title"]].url if s.get("wiki_title") in pages else None)
                for s in styles if s.get("is_fashion_style")]

    def seed(self, names: list[str] | None = None) -> dict:
        rows = self.define(names or SEED_STYLES)
        return {"defined": len(rows), "grounded_in_wiki": sum(bool(r.get("source_url")) for r in rows)}

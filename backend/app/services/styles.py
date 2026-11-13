from __future__ import annotations

from ..ports import Database, PinSource, Row
from .base import get_one
from .stylist import Stylist


class StyleService:
    def __init__(self, db: Database, pins: PinSource, stylist: Stylist):
        self._db, self._pins, self._stylist = db, pins, stylist

    def list(self) -> list[Row]:
        return self._db.select("styles", order_by="name")

    def get(self, style_id: str) -> Row:
        return get_one(self._db, "styles", id=style_id) | {"pins": self._db.select("style_pins", {"style_id": style_id})}

    def library(self) -> list[Row]:
        """Compact style descriptions for prompts."""
        return [{"name": s["name"], **(s.get("summary") or {})} for s in self.list()]

    def refresh(self, queries: list[str], pins_per_style: int) -> dict:
        return {"styles": [self._refresh_one(q, pins_per_style) for q in queries]}

    def _refresh_one(self, query: str, limit: int) -> Row:
        pins = self._pins.search(query, limit)
        summary = self._stylist.summarise_style(query, [p.image_url for p in pins])
        style = self._db.upsert("styles", [{"name": query, "query": query, "summary": summary}], "name")[0]
        self._db.upsert("style_pins", [{"style_id": style["id"], "pin_url": p.url, "image_url": p.image_url,
                                        "title": p.title} for p in pins], "pin_url")
        return {"style_id": style["id"], "name": query, "pins": len(pins)}

    def fill_pins(self, per_style: int, only_missing: bool = True, style_ids: list[str] | None = None) -> dict:
        """Attach Pinterest pins to existing library styles (the swipe deck serves these). No new style rows.
        only_missing: skip styles that already have >= per_style pins."""
        styles = [s for s in self.list() if s.get("status", "active") == "active"
                  and (style_ids is None or s["id"] in style_ids)]
        counts: dict[str, int] = {}
        for p in self._db.select("style_pins"):
            counts[p["style_id"]] = counts.get(p["style_id"], 0) + 1
        filled = []
        for style in styles:
            if only_missing and counts.get(style["id"], 0) >= per_style:
                continue
            query = f"{style.get('search_term') or style.get('query') or style['name']} outfit"
            pins = self._pins.search(query, per_style)
            self._db.upsert("style_pins", [{"style_id": style["id"], "pin_url": p.url, "image_url": p.image_url,
                                            "title": p.title} for p in pins if p.url], "pin_url")
            filled.append({"style_id": style["id"], "name": style["name"], "query": query, "pins": len(pins)})
        return {"styles_filled": len(filled), "pins": sum(f["pins"] for f in filled), "detail": filled}

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

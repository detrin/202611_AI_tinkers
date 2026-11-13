"""Swipe game: serves unseen pins round-robin across styles and records likes/dislikes."""
from itertools import chain, zip_longest

from ..ports import Database, Row


class PreferenceService:
    def __init__(self, db: Database, pool_size: int = 500):
        self._db, self._pool = db, pool_size

    def deck(self, uid: str, n: int) -> list[Row]:
        seen = {s["pin_id"] for s in self._db.select("swipes", {"user_id": uid})}
        by_style: dict[str, list[Row]] = {}
        for pin in self._db.select("style_pins", limit=self._pool):
            if pin["id"] not in seen:
                by_style.setdefault(pin["style_id"], []).append(pin)
        interleaved = [p for p in chain.from_iterable(zip_longest(*by_style.values())) if p]
        return interleaved[:n]

    def record(self, uid: str, swipes: list[Row]) -> int:
        self._db.upsert("swipes", [{"user_id": uid, **s} for s in swipes], "user_id,pin_id")
        return len(swipes)

    def signals(self, uid: str) -> dict[str, list[Row]]:
        """Liked/disliked pins as {style, title} for prompts."""
        swipes = self._db.select("swipes", {"user_id": uid})
        if not swipes:
            return {"liked": [], "disliked": []}
        pins = {p["id"]: p for p in self._db.select("style_pins", in_={"id": [s["pin_id"] for s in swipes]})}
        styles = {s["id"]: s["name"] for s in self._db.select("styles")}
        view = lambda s: {"style": styles.get(pins.get(s["pin_id"], {}).get("style_id")),
                          "title": pins.get(s["pin_id"], {}).get("title")}
        return {"liked": [view(s) for s in swipes if s["liked"]], "disliked": [view(s) for s in swipes if not s["liked"]]}

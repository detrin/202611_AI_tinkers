"""Swipe game: serves the next unseen style pins (explore/exploit bandit, see style_deck.py), records likes and
dislikes, and exposes them as the user's "interested" / "not interested" boards (separate from the wardrobe)."""
from __future__ import annotations

import random
from datetime import datetime, timezone

from ..ports import Database, Row
from .base import latest
from .style_deck import beliefs, next_pins, tokens

AUDIENCES = ("menswear", "womenswear")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PreferenceService:
    def __init__(self, db: Database, pool_size: int = 5000):
        self._db, self._pool = db, pool_size

    # ---------- belief state ----------
    def _styles(self, user: Row | None) -> list[Row]:
        audience = ((user or {}).get("fit_prefs") or {}).get("audience")
        return [s for s in self._db.select("styles")
                if s.get("status", "active") == "active"
                and (audience not in AUDIENCES or s.get("audience", "unisex") in ("unisex", audience))]

    def _context(self, uid: str, user: Row | None) -> Row:
        """Everything the user provided before/besides swiping (all optional)."""
        items = self._db.select("wardrobe_items", {"user_id": uid})
        return {
            "taste": (latest(self._db, "taste_profiles", user_id=uid) or {}).get("profile"),
            "instagram": (user or {}).get("style_profile"),
            "inspirations": self._db.select("inspirations", {"user_id": uid}),
            "wanted": [i for i in items if i.get("status") == "wanted"],
            "owned": [i for i in items if i.get("status", "owned") == "owned"],
            "style_feedback": {f["style_id"]: f["interested"] for f in self._db.select("user_style_feedback", {"user_id": uid})},
        }

    def _state(self, uid: str):
        user = next(iter(self._db.select("users", {"id": uid}, limit=1)), None)
        styles = self._styles(user)
        pins = {p["id"]: p for p in self._db.select("style_pins", limit=self._pool)}
        swipes = self._db.select("swipes", {"user_id": uid})
        return styles, pins, swipes, beliefs(styles, pins, swipes, self._context(uid, user))

    def beliefs(self, uid: str) -> list[Row]:
        """Current per-style belief (for debugging / the profile page), most liked first."""
        styles, pins, _, state = self._state(uid)
        unseen = self._unseen(uid, pins)
        rows = [{"style_id": b.style_id, "name": b.name, "p_like": round(b.mean, 3),
                 "uncertainty": round(b.variance ** 0.5, 3), "likes": b.likes, "dislikes": b.dislikes,
                 "prior": round(b.prior_mean, 3), "prior_from": b.evidence,
                 "unseen_pins": sum(1 for p in unseen if p["style_id"] == b.style_id)} for b in state.values()]
        return sorted(rows, key=lambda r: -r["p_like"])

    def _unseen(self, uid: str, pins: dict[str, Row]) -> list[Row]:
        seen = {s["pin_id"] for s in self._db.select("swipes", {"user_id": uid})}
        seen |= {i["pin_id"] for i in self._db.select("pin_impressions", {"user_id": uid})}
        return [p for p in pins.values() if p["id"] not in seen]

    # ---------- serving ----------
    def deck(self, uid: str, n: int, explore: float = 0.5, seed: int | None = None) -> list[Row]:
        """Next n unseen pins. Each is logged as seen (pin_impressions) so it is never served twice."""
        _, pins, swipes, state = self._state(uid)
        by_style: dict[str, list[Row]] = {}
        for p in self._unseen(uid, pins):
            by_style.setdefault(p["style_id"], []).append(p)
        liked_terms = set().union(*(tokens(pins[s["pin_id"]].get("title")) for s in swipes
                                    if s["liked"] and s["pin_id"] in pins))
        picked = next_pins(state, by_style, n, explore, liked_terms, random.Random(seed))
        if picked:
            self._db.upsert("pin_impressions", [{"user_id": uid, "pin_id": p["id"], "mode": p["mode"],
                                                 "p_like": p["p_like"], "served_at": _now()} for p in picked],
                            "user_id,pin_id")
        return picked

    # ---------- swipes & boards ----------
    def record(self, uid: str, swipes: list[Row]) -> int:
        """Swipes on served pins inherit the explore/exploit mode they were served with."""
        modes = {i["pin_id"]: i.get("mode") for i in self._db.select(
            "pin_impressions", {"user_id": uid}, in_={"pin_id": [s["pin_id"] for s in swipes]})} if swipes else {}
        rows = [{"user_id": uid, "source": "deck", **{k: v for k, v in s.items() if v is not None},
                 "mode": modes.get(s["pin_id"])} for s in swipes]
        self._db.upsert("swipes", rows, "user_id,pin_id")
        return len(swipes)

    def board(self, uid: str, liked: bool | None = None) -> list[Row]:
        """Swiped pins with image + style, newest first. liked=True: interested, False: not interested."""
        where = {"user_id": uid} | ({"liked": liked} if liked is not None else {})
        swipes = self._db.select("swipes", where, order_by="created_at", desc=True)
        if not swipes:
            return []
        pins = {p["id"]: p for p in self._db.select("style_pins", in_={"id": [s["pin_id"] for s in swipes]})}
        styles = {s["id"]: s["name"] for s in self._db.select("styles")}
        return [{**{k: s.get(k) for k in ("pin_id", "liked", "mode", "source", "created_at")},
                 **{k: pins.get(s["pin_id"], {}).get(k) for k in ("image_url", "pin_url", "title", "style_id")},
                 "style_name": styles.get(pins.get(s["pin_id"], {}).get("style_id"))} for s in swipes]

    def signals(self, uid: str) -> dict[str, list[Row]]:
        """Liked/disliked pins as {style, title} for prompts."""
        view = lambda r: {"style": r["style_name"], "title": r["title"]}
        rows = self.board(uid)
        return {"liked": [view(r) for r in rows if r["liked"]], "disliked": [view(r) for r in rows if not r["liked"]]}

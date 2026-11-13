"""Recommend styles the user doesn't wear yet. Deterministic, explainable scoring:

score = 0.35 aspiration + 0.30 wardrobe coverage + 0.15 colour fit + trend bonus - 0.25 already-wears
(+ greedy diversity: related to an already-picked style → -0.10)
"""
from __future__ import annotations

import re

from ..ports import Database, Row
from .base import latest
from .inspirations import InspirationService
from .style_library import StyleLibraryService
from .trends import STAGE_BONUS
from .users import UserService
from .wardrobe import WANTED, WardrobeService

W_ASPIRATION, W_COVERAGE, W_COLOR, W_CURRENT, DIVERSITY = 0.35, 0.30, 0.15, 0.25, 0.10
STOP = {"a", "an", "the", "and", "or", "with", "of", "style", "aesthetic", "core", "look", "piece", "pieces"}
# garment head nouns that mean the same thing (after singularisation)
SYNONYMS = {"pant": "trouser", "chino": "trouser", "slack": "trouser", "jean": "jeans", "denim": "jeans",
            "trainer": "sneaker", "tee": "t-shirt", "tshirt": "t-shirt", "jumper": "sweater", "pullover": "sweater",
            "knit": "sweater", "crewneck": "sweater", "loafer": "loafer", "boot": "boot", "parka": "coat",
            "overcoat": "coat", "topcoat": "coat"}


def tokens(text: str | None) -> set[str]:
    words = re.findall(r"[a-z]+", (text or "").lower())
    return {w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words} - STOP


def similarity(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def palette_overlap(palette: list[str], colors: list[str]) -> float:
    p, c = set().union(*map(tokens, palette or [])), set().union(*map(tokens, colors or []))
    return len(p & c) / len(p) if p else 0.0


def head(garment: str | None) -> str | None:
    """Head noun of a garment phrase: 'tweed blazer' → blazer, 'dress shirt' → shirt, 'long-sleeve t-shirt' → t-shirt."""
    words = re.findall(r"[a-z]+(?:-[a-z]+)*", (garment or "").lower())
    words = [w for w in words if w not in STOP]
    if not words:
        return None
    w = words[-1]
    w = w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "jeans")) else w
    return SYNONYMS.get(w, w)


def coverage(key_pieces: list[str], owned: list[Row]) -> tuple[list[Row], list[str]]:
    """A key piece is covered by an owned item with the same garment head noun; each item counts once."""
    have, missing, used = [], [], set()
    for piece in key_pieces or []:
        hit = next((i for i in owned if i["id"] not in used and head(piece) and head(piece) == head(i.get("subtype"))), None)
        if hit:
            used.add(hit["id"])
            have.append({"piece": piece, "item_id": hit["id"], "subtype": hit.get("subtype")})
        else:
            missing.append(piece)
    return have, missing


def affinity(style: Row, mix: list[Row]) -> float:
    """How strongly a style_mix (from the taste profile) points at this style: name/alias match or relation."""
    names = [style["name"], *(style.get("aliases") or [])]
    best = 0.0
    for m in mix or []:
        weight = (m.get("percent") or 0) / 100
        sim = max(similarity(n, m.get("style", "")) for n in names)
        if any(similarity(r, m.get("style", "")) >= 0.5 for r in style.get("related") or []):
            sim = max(sim, 0.5)
        best = max(best, sim * weight if weight else sim * 0.5)
    return best


def fits_audience(style: Row, audience: str | None) -> bool:
    return not audience or style.get("audience", "unisex") in ("unisex", audience)


def related_to_any(style: Row, others: list[Row]) -> bool:
    rel = {r.lower() for r in style.get("related") or []}
    return any(o["name"].lower() in rel or style["name"].lower() in {r.lower() for r in o.get("related") or []}
               for o in others)


def score(style: Row, ctx: Row) -> Row:
    have, missing = coverage(style.get("key_pieces") or [], ctx["owned"])
    cov = len(have) / max(len(style.get("key_pieces") or []), 1)
    aspiration = max(affinity(style, ctx["aspiration_mix"]), 0.5 * palette_overlap(style.get("palette"), ctx["aspiration_palette"]))
    current = affinity(style, ctx["current_mix"])
    color = palette_overlap(style.get("palette"), ctx["good_colors"]) - palette_overlap(style.get("palette"), ctx["bad_colors"])
    trend = STAGE_BONUS.get(style.get("lifecycle") or "unknown", 0.0)
    total = W_ASPIRATION * aspiration + W_COVERAGE * cov + W_COLOR * color + trend - W_CURRENT * current
    return {"score": round(total, 4), "components": {"aspiration": round(aspiration, 3), "coverage": round(cov, 3),
            "color_fit": round(color, 3), "trend": trend, "already_wears": round(current, 3)},
            "owned_pieces": have, "missing_pieces": missing}


def reasons(style: Row, s: Row) -> list[str]:
    c, out = s["components"], []
    if s["owned_pieces"]:
        out.append(f"You already own {len(s['owned_pieces'])} of {len(style.get('key_pieces') or [])} key pieces: "
                   + ", ".join(p["subtype"] or p["piece"] for p in s["owned_pieces"][:4]))
    if c["aspiration"] >= 0.3:
        out.append("Close to the looks you save and like")
    if c["color_fit"] > 0.2:
        out.append("Its palette suits your colours")
    if style.get("lifecycle") in ("emerging", "rising"):
        out.append(f"Trending: {style['lifecycle']}" + (f" ({style['trend']['growth']:+.0%} in 8 weeks)" if style.get("trend") else ""))
    return out


class StyleRecommendationService:
    def __init__(self, db: Database, users: UserService, wardrobe: WardrobeService, inspirations: InspirationService,
                 library: StyleLibraryService):
        self._db, self._users, self._wardrobe, self._inspirations, self._library = db, users, wardrobe, inspirations, library

    def context(self, uid: str) -> Row:
        user = self._users.get(uid)
        taste = (latest(self._db, "taste_profiles", user_id=uid) or {}).get("profile") or {}
        colors = user.get("color_profile") or {}
        fallback = [{"style": t, "percent": 50} for i in self._inspirations.items(uid) for t in i.get("style_tags") or []]
        fallback += [{"style": t, "percent": 30} for i in self._wardrobe.items(uid, WANTED) for t in i.get("style_tags") or []]
        return {
            "owned": self._wardrobe.items(uid),
            "aspiration_mix": (taste.get("aspirational_style") or {}).get("style_mix") or fallback,
            "aspiration_palette": (taste.get("aspirational_style") or {}).get("palette") or [],
            "current_mix": (taste.get("current_style") or {}).get("style_mix") or [],
            "good_colors": (colors.get("best_colors") or []) + ((taste.get("colors") or {}).get("wear_more") or []),
            "bad_colors": (colors.get("avoid_colors") or []) + ((taste.get("colors") or {}).get("avoid") or []),
            "rejected": {f["style_id"] for f in self._db.select("user_style_feedback", {"user_id": uid, "interested": False})},
            "audience": (user.get("fit_prefs") or {}).get("audience"),
        }

    def recommend(self, uid: str, n: int = 5) -> list[Row]:
        ctx = self.context(uid)
        remaining = [(st, score(st, ctx)) for st in self._library.active()
                     if st["id"] not in ctx["rejected"] and fits_audience(st, ctx["audience"])]
        picked: list[tuple[Row, Row]] = []
        while remaining and len(picked) < n:   # greedy: penalise styles related to ones already picked
            adjusted = [(st, s, s["score"] - (DIVERSITY if related_to_any(st, [p for p, _ in picked]) else 0))
                        for st, s in remaining]
            style, s, value = max(adjusted, key=lambda x: x[2])
            picked.append((style, {**s, "score": round(value, 4)}))
            remaining = [(st, sc) for st, sc in remaining if st["id"] != style["id"]]
        return [self._card(style, s) for style, s in picked]

    @staticmethod
    def _card(style: Row, s: Row) -> Row:
        keep = ("id", "name", "definition", "audience", "palette", "key_pieces", "lifecycle", "trend", "source_url")
        return {**{k: style.get(k) for k in keep}, **s, "reasons": reasons(style, s)}

    def feedback(self, uid: str, style_id: str, interested: bool) -> Row:
        self._users.get(uid)
        self._db.upsert("user_style_feedback", [{"user_id": uid, "style_id": style_id, "interested": interested}],
                        "user_id,style_id")
        return {"ok": True}

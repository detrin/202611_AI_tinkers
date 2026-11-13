"""Taste profile: deterministic wardrobe facts + weighted evidence → a strong model (Opus) writes the profile.

Two views are kept apart on purpose: how the user dresses (owned, worn, Instagram) vs how they want to dress
(inspiration, wishlist, likes). The gap between them drives shopping.
"""
from __future__ import annotations

import json
from collections import Counter

from ..errors import Conflict, NotFound
from ..ports import Database, Row, StructuredModel
from .base import latest
from .inspirations import InspirationService, summarise_looks
from .preferences import PreferenceService
from .styles import StyleService
from .users import UserService
from .wardrobe import WANTED, WardrobeService, summarise

TOP_K = 8
MIN_EVIDENCE = 3

WEIGHTS = """Evidence weights (how much to trust each source):
- HIGH: outfit_feedback (worn/rated), instagram_style (what they really wear), inspiration_looks (explicit aspiration)
- MEDIUM: owned_items (past choices, may include old/unloved items), wishlist_items, liked_products
- LOW: swipes (quick, noisy). Disliked swipes are useful negatives."""

PROMPT = """You are an expert personal stylist building a user's taste profile from evidence.
{weights}

Rules:
- Separate CURRENT style (owned items, worn outfits, Instagram) from ASPIRATIONAL style (inspirations, wishlist,
  liked products/swipes). Do not blend them.
- Use style names from the STYLE LIBRARY when they fit; you may add one custom style if nothing fits.
- Percentages in each style_mix must sum to 100. Cite concrete evidence (item subtypes, colours, looks) in `evidence`.
- Respect the colour profile (seasonal analysis) when recommending colours, if present.
- shop_queries: 3-6 short, concrete product searches that move the user from current to aspirational style,
  complement owned items, and do not duplicate the wishlist.
- confidence reflects how much evidence there is; list what would most improve the profile in missing_evidence.

EVIDENCE (JSON):
{evidence}"""

_STYLE_MIX = {"type": "array", "items": {"type": "object", "required": ["style", "percent", "evidence"], "properties": {
    "style": {"type": "string"}, "percent": {"type": "number"}, "evidence": {"type": "string"}}}}
_STR_LIST = {"type": "array", "items": {"type": "string"}}
_STYLE_VIEW = {"type": "object", "required": ["summary", "style_mix", "palette", "silhouettes", "formality_range"],
               "properties": {"summary": {"type": "string"}, "style_mix": _STYLE_MIX, "palette": _STR_LIST,
                              "silhouettes": _STR_LIST, "key_pieces": _STR_LIST,
                              "formality_range": {"type": "array", "items": {"type": "integer"}}}}

TASTE_SCHEMA = {
    "type": "object",
    "required": ["headline", "current_style", "aspirational_style", "gap", "colors", "avoid", "shop_queries",
                 "confidence", "missing_evidence"],
    "properties": {
        "headline": {"type": "string", "description": "one-line description of the user's taste"},
        "current_style": _STYLE_VIEW,
        "aspirational_style": _STYLE_VIEW,
        "gap": {"type": "object", "required": ["summary", "moves"], "properties": {
            "summary": {"type": "string"},
            "moves": {"type": "array", "items": {"type": "object", "required": ["action", "why"], "properties": {
                "action": {"type": "string"}, "why": {"type": "string"}}}}}},
        "colors": {"type": "object", "required": ["wear_more", "avoid"], "properties": {
            "wear_more": _STR_LIST, "avoid": _STR_LIST}},
        "avoid": _STR_LIST,
        "shop_queries": _STR_LIST,
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "missing_evidence": _STR_LIST,
    },
}


def _top(values, k: int = TOP_K) -> list[list]:
    return [[v, n] for v, n in Counter(v for v in values if v).most_common(k)]


def wardrobe_facts(items: list[Row]) -> Row:
    """Deterministic statistics over owned items — cheap, stable, explainable."""
    return {
        "item_count": len(items),
        "categories": _top((i.get("category") for i in items)),
        "primary_colors": _top(((i.get("colors") or [None])[0] for i in items)),
        "all_colors": _top((c for i in items for c in i.get("colors") or [])),
        "patterns": _top((i.get("pattern") for i in items)),
        "materials": _top((i.get("material") for i in items)),
        "fits": _top((i.get("fit") for i in items)),
        "style_tags": _top((t for i in items for t in i.get("style_tags") or [])),
        "formality_histogram": dict(sorted(Counter(i["formality"] for i in items if i.get("formality")).items())),
    }


class TasteService:
    def __init__(self, db: Database, users: UserService, wardrobe: WardrobeService, inspirations: InspirationService,
                 prefs: PreferenceService, styles: StyleService, model: StructuredModel):
        self._db, self._users, self._wardrobe, self._inspirations, self._prefs, self._styles = (
            db, users, wardrobe, inspirations, prefs, styles)
        self._model = model

    def evidence(self, uid: str) -> Row:
        user = self._users.get(uid)
        owned = self._wardrobe.items(uid)
        signals = self._prefs.signals(uid)
        liked_ids = [f["product_id"] for f in self._db.select("product_feedback", {"user_id": uid}) if f.get("liked")]
        liked = self._db.select("products", in_={"id": liked_ids}) if liked_ids else []
        outfits = [o for o in self._db.select("outfits", {"user_id": uid}, order_by="created_at", desc=True, limit=20)
                   if o.get("feedback")]
        by_id = {i["id"]: i.get("subtype") for i in owned}
        return {
            "user": {k: user.get(k) for k in ("city", "budget", "currency", "fit_prefs", "sizes")},
            "color_profile": user.get("color_profile"),
            "instagram_style": user.get("style_profile"),
            "wardrobe_facts": wardrobe_facts(owned),
            "owned_items": summarise(owned),
            "wishlist_items": summarise(self._wardrobe.items(uid, WANTED)),
            "inspiration_looks": summarise_looks(self._inspirations.items(uid)),
            "liked_swipes": signals["liked"],
            "disliked_swipes": signals["disliked"],
            "liked_products": [{"name": p.get("name"), "price": p.get("price")} for p in liked],
            "outfit_feedback": [{"event": o.get("event"), "items": [by_id.get(i) for i in o.get("item_ids") or []],
                                 "feedback": o["feedback"]} for o in outfits],
            "style_library": [s["name"] for s in self._styles.library()],
        }

    @staticmethod
    def counts(evidence: Row) -> Row:
        lists = ("owned_items", "wishlist_items", "inspiration_looks", "liked_swipes", "disliked_swipes",
                 "liked_products", "outfit_feedback")
        return {k: len(evidence[k]) for k in lists} | {"instagram": bool(evidence["instagram_style"]),
                                                        "color_profile": bool(evidence["color_profile"])}

    def ensure_enough(self, uid: str) -> None:
        """Validated eagerly, before a job is queued."""
        c = self.counts(self.evidence(uid))
        if sum(v for k, v in c.items() if isinstance(v, int) and not isinstance(v, bool)) < MIN_EVIDENCE:
            raise Conflict(f"Not enough evidence yet (need {MIN_EVIDENCE}+ items/looks/likes): {c}")

    def build(self, uid: str) -> Row:
        ev = self.evidence(uid)
        prompt = PROMPT.format(weights=WEIGHTS, evidence=json.dumps(ev, default=str, ensure_ascii=False))
        profile = self._model.generate(prompt, TASTE_SCHEMA)
        return self._db.insert("taste_profiles", {"user_id": uid, "model": getattr(self._model, "model", type(self._model).__name__), "profile": profile,
                                                  "facts": ev["wardrobe_facts"], "evidence_counts": self.counts(ev)})

    def get(self, uid: str) -> Row:
        if not (p := latest(self._db, "taste_profiles", user_id=uid)):
            raise NotFound("No taste profile yet; POST /users/{uid}/taste-profile")
        return p

"""Pasted product links: scrape → LLM verdict against the user's profile and wardrobe."""
from __future__ import annotations

from ..ports import Database, Row
from .catalog import CatalogService
from .profiles import ProfileService
from .stylist import Stylist
from .users import UserService
from .wardrobe import WANTED, WardrobeService, summarise

PRODUCT_FIELDS = ("id", "name", "price", "currency", "image_url", "url")


class LinkService:
    def __init__(self, db: Database, users: UserService, catalog: CatalogService, profiles: ProfileService,
                 wardrobe: WardrobeService, stylist: Stylist):
        self._db, self._users, self._catalog, self._profiles, self._wardrobe, self._stylist = (
            db, users, catalog, profiles, wardrobe, stylist)

    def ensure_user(self, uid: str) -> None:
        self._users.get(uid)

    def check(self, uid: str, url: str) -> Row:
        product = self._catalog.from_url(url)
        profile = self._profiles.current(uid) or {}
        verdict = self._stylist.link_verdict(
            {k: product.get(k) for k in ("name", "price", "currency", "description")},
            {"style_mix": profile.get("style_mix"), "taste": profile.get("taste_summary")},
            {"owned": summarise(self._wardrobe.items(uid)), "wishlist": summarise(self._wardrobe.items(uid, WANTED))},
            product.get("image_url"))
        row = self._db.insert("link_checks", {"user_id": uid, "product_id": product["id"], "url": url,
                                              "score": verdict.get("score_1to10"), "verdict": verdict})
        return {"link_check_id": row["id"], "product": {k: product.get(k) for k in PRODUCT_FIELDS}, **verdict}

    def list(self, uid: str) -> list[Row]:
        return self._db.select("link_checks", {"user_id": uid}, order_by="created_at", desc=True)

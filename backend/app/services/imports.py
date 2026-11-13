"""Import from a URL: a retailer product page (→ wardrobe item with page context) or an Instagram
profile/post (→ per-post outfit analysis, an aggregated style profile, optionally wardrobe items)."""
from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from ..errors import Invalid
from ..ports import Database, Row, SocialSource
from .catalog import CatalogService
from .images import ImageService
from .stylist import Stylist
from .users import UserService
from .wardrobe import OWNED, WardrobeService

log = logging.getLogger(__name__)

HANDLE = re.compile(r"^@?([A-Za-z0-9._]{1,30})$")
IG_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com"}
PRODUCT_FIELDS = ("id", "name", "price", "currency", "marketplace", "image_url", "url")


def resolve(ref: str, kind: str = "auto") -> tuple[str, str]:
    """User input → (kind, canonical url). Accepts '@handle', 'handle', instagram URLs and any http(s) URL."""
    ref = ref.strip()
    if not ref.startswith(("http://", "https://")):
        if kind in ("auto", "instagram") and (m := HANDLE.match(ref)):
            return "instagram", f"https://www.instagram.com/{m.group(1)}/"
        raise Invalid(f"Not a URL or Instagram handle: {ref!r}")
    detected = "instagram" if urlparse(ref).netloc.lower() in IG_HOSTS else "product"
    if kind != "auto" and kind != detected:
        raise Invalid(f"URL looks like {detected}, not {kind}")
    return detected, ref


class ImportService:
    def __init__(self, db: Database, users: UserService, images: ImageService, wardrobe: WardrobeService,
                 catalog: CatalogService, social: SocialSource, stylist: Stylist):
        self._db, self._users, self._images, self._wardrobe, self._catalog, self._social, self._stylist = (
            db, users, images, wardrobe, catalog, social, stylist)

    def prepare(self, uid: str, ref: str, kind: str = "auto") -> tuple[str, str]:
        """Validated eagerly, before a job is queued."""
        self._users.get(uid)
        return resolve(ref, kind)

    # ---------- retailer / any product page (owned item; liking a product makes a wanted one) ----------
    def product(self, uid: str, url: str) -> Row:
        product = self._catalog.from_url(url)
        item = self._wardrobe.add_product(uid, product, OWNED)
        return {"kind": "product", "item": item, "product": {k: product.get(k) for k in PRODUCT_FIELDS}}

    # ---------- Instagram ----------
    def instagram(self, uid: str, url: str, max_posts: int, import_items: bool) -> Row:
        posts = self._social.posts(url, max_posts)
        if not posts:
            raise Invalid(f"No public posts found at {url} (private, empty or blocked profile?)")
        added: list[Row] = []
        analysed = [a for post in posts if (a := self._analyse(uid, post, import_items, added))]
        outfits = [a for a in analysed if a["analysis"].get("has_outfit")]
        if not outfits:
            raise Invalid("No outfits recognised in the posts")
        style = self._stylist.instagram_style([{k: a["analysis"].get(k) for k in ("items", "style_tags", "colors",
                                                "setting", "vibe")} for a in outfits])
        row = self._db.insert("social_imports", {
            "user_id": uid, "platform": "instagram", "url": url, "posts": analysed, "style_profile": style,
            "item_ids": [i["id"] for i in added]})
        self._db.update("users", {"id": uid}, {"style_profile": style})
        return {"kind": "instagram", "import_id": row["id"], "posts_analysed": len(analysed),
                "outfits": len(outfits), "style_profile": style, "items_added": added}

    def _analyse(self, uid: str, post, import_items: bool, added: list[Row]) -> Row | None:
        try:
            image = self._images.from_url(post.image_urls[0])   # IG CDN links expire → keep our own copy
        except Invalid:
            log.warning("skipping post %s: image fetch failed", post.url)
            return None
        stored = self._images.save(uid, "instagram", image)
        analysis = self._stylist.analyse_post(image.data_url, post.caption)
        if import_items and analysis.get("has_outfit") and analysis.get("items"):
            source = {"source_type": "instagram", "source_url": post.url}
            added += self._wardrobe.add_detected(uid, stored["id"], analysis["items"], source)
        return {"post_url": post.url, "image_id": stored["id"], "timestamp": post.timestamp, "analysis": analysis}

    def list(self, uid: str) -> list[Row]:
        return self._db.select("social_imports", {"user_id": uid}, order_by="created_at", desc=True)

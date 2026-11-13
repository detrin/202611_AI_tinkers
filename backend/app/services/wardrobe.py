"""Single garments the user owns or wants (wishlist). Same tagging and storage for both."""
from __future__ import annotations

from ..domain import ImageInput
from ..errors import Invalid
from ..ports import Database, Row
from .base import get_one
from .images import ImageService
from .stylist import Stylist
from .users import UserService

OWNED, WANTED = "owned", "wanted"
STATUSES = (OWNED, WANTED)
SUMMARY_FIELDS = ("id", "category", "subtype", "colors", "pattern", "material", "fit", "formality", "warmth",
                  "style_tags", "availability")
UPLOAD: Row = {"source_type": "upload"}
PRODUCT_CONTEXT = ("name", "description", "price", "currency", "marketplace")
PRODUCT_RAW_CONTEXT = ("brand", "material", "color", "category")  # small, useful bits of the scraped payload


def item_row(uid: str, image_id: str, tags: dict, status: str = OWNED, product_id: str | None = None,
             source: Row = UPLOAD) -> Row:
    """`source`: source_type (upload|product_url|instagram|pin) and source_url."""
    return {"user_id": uid, "image_id": image_id, "status": status, "product_id": product_id,
            "category": tags.get("category"), "subtype": tags.get("subtype"), "colors": tags.get("colors") or [],
            "pattern": tags.get("pattern"), "material": tags.get("material"), "fit": tags.get("fit"),
            "formality": tags.get("formality_1to5"), "warmth": tags.get("warmth_1to5"),
            "style_tags": tags.get("style_tags") or [], "raw": tags, **source}


def summarise(items: list[Row]) -> list[Row]:
    """Compact view of items for LLM prompts."""
    return [{k: i.get(k) for k in SUMMARY_FIELDS} for i in items]


def check_status(status: str | None) -> None:
    if status is not None and status not in STATUSES:
        raise Invalid(f"status must be one of {STATUSES}")


class WardrobeService:
    def __init__(self, db: Database, users: UserService, images: ImageService, stylist: Stylist):
        self._db, self._users, self._images, self._stylist = db, users, images, stylist

    def add(self, uid: str, images: list[ImageInput], status: str = OWNED, product_id: str | None = None,
            context: Row | None = None, source: Row = UPLOAD) -> list[Row]:
        """Store + vision-tag each image. `context` (e.g. product page text) is shown to the tagger."""
        check_status(status)
        self._users.get(uid)
        rows = []
        for image in images:
            stored = self._images.save(uid, "wardrobe", image)
            tags = self._stylist.tag_item(image.data_url, context)
            rows.append(self._db.insert("wardrobe_items", item_row(uid, stored["id"], tags, status, product_id, source)))
        return self._images.with_urls(rows)

    def add_product(self, uid: str, product: Row, status: str) -> Row:
        """Turn a scraped product into an item, tagged once from its photo + the product page text."""
        if not product.get("image_url"):
            raise Invalid("Product has no image to tag")
        raw = product.get("raw") or {}
        context = {k: product.get(k) for k in PRODUCT_CONTEXT} | {k: raw[k] for k in PRODUCT_RAW_CONTEXT if raw.get(k)}
        source = {"source_type": "product_url", "source_url": product.get("url")}
        return self.add(uid, [self._images.from_url(product["image_url"])], status, product["id"], context, source)[0]

    def add_detected(self, uid: str, image_id: str, detected: list[Row], source: Row) -> list[Row]:
        """Garments already tagged elsewhere (e.g. several found in one Instagram photo), sharing one image."""
        self._users.get(uid)
        rows = [self._db.insert("wardrobe_items", item_row(uid, image_id, tags, OWNED, None, source)) for tags in detected]
        return self._images.with_urls(rows)

    def items(self, uid: str, status: str | None = OWNED, category: str | None = None,
              color: str | None = None) -> list[Row]:
        """status=None returns owned and wanted."""
        check_status(status)
        where = {"user_id": uid} | ({"status": status} if status else {}) | ({"category": category} if category else {})
        return self._db.select("wardrobe_items", where, contains={"colors": [color]} if color else None,
                               order_by="created_at")

    def list(self, uid: str, status: str | None = OWNED, category: str | None = None,
             color: str | None = None) -> list[Row]:
        return self._images.with_urls(self.items(uid, status, category, color))

    def for_product(self, uid: str, product_id: str) -> Row | None:
        rows = self._db.select("wardrobe_items", {"user_id": uid, "product_id": product_id}, limit=1)
        return rows[0] if rows else None

    def get(self, uid: str, item_id: str) -> Row:
        return self._images.with_urls([get_one(self._db, "wardrobe_items", id=item_id, user_id=uid)])[0]

    def update(self, uid: str, item_id: str, patch: Row) -> Row:
        check_status(patch.get("status"))
        self.get(uid, item_id)
        if patch:
            self._db.update("wardrobe_items", {"id": item_id, "user_id": uid}, patch)
        return self.get(uid, item_id)

    def mark_owned(self, uid: str, item_id: str) -> Row:
        return self.update(uid, item_id, {"status": OWNED})

    def delete(self, uid: str, item_id: str) -> None:
        self.get(uid, item_id)
        self._db.delete("wardrobe_items", {"id": item_id, "user_id": uid})

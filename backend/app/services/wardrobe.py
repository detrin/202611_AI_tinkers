from __future__ import annotations

from ..domain import ImageInput
from ..ports import Database, Row
from .base import get_one
from .images import ImageService
from .stylist import Stylist
from .users import UserService

SUMMARY_FIELDS = ("id", "category", "subtype", "colors", "pattern", "material", "formality", "warmth", "style_tags")


def item_row(uid: str, image_id: str, tags: dict) -> Row:
    return {"user_id": uid, "image_id": image_id, "category": tags.get("category"), "subtype": tags.get("subtype"),
            "colors": tags.get("colors") or [], "pattern": tags.get("pattern"), "material": tags.get("material"),
            "formality": tags.get("formality_1to5"), "warmth": tags.get("warmth_1to5"),
            "style_tags": tags.get("style_tags") or [], "raw": tags}


def summarise(items: list[Row]) -> list[Row]:
    """Compact view of items for LLM prompts."""
    return [{k: i.get(k) for k in SUMMARY_FIELDS} for i in items]


class WardrobeService:
    def __init__(self, db: Database, users: UserService, images: ImageService, stylist: Stylist):
        self._db, self._users, self._images, self._stylist = db, users, images, stylist

    def add(self, uid: str, images: list[ImageInput]) -> list[Row]:
        self._users.get(uid)
        rows = []
        for image in images:
            stored = self._images.save(uid, "wardrobe", image)
            rows.append(self._db.insert("wardrobe_items", item_row(uid, stored["id"], self._stylist.tag_item(image.data_url))))
        return self._images.with_urls(rows)

    def items(self, uid: str, category: str | None = None, color: str | None = None) -> list[Row]:
        where = {"user_id": uid} | ({"category": category} if category else {})
        return self._db.select("wardrobe_items", where, contains={"colors": [color]} if color else None,
                               order_by="created_at")

    def list(self, uid: str, category: str | None = None, color: str | None = None) -> list[Row]:
        return self._images.with_urls(self.items(uid, category, color))

    def get(self, uid: str, item_id: str) -> Row:
        return self._images.with_urls([get_one(self._db, "wardrobe_items", id=item_id, user_id=uid)])[0]

    def update(self, uid: str, item_id: str, patch: Row) -> Row:
        self.get(uid, item_id)
        if patch:
            self._db.update("wardrobe_items", {"id": item_id, "user_id": uid}, patch)
        return self.get(uid, item_id)

    def delete(self, uid: str, item_id: str) -> None:
        self.get(uid, item_id)
        self._db.delete("wardrobe_items", {"id": item_id, "user_id": uid})

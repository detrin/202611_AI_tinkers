"""Inspiration = a whole look (upload, URL or saved Pinterest pin), tagged as a look, not a garment."""
from __future__ import annotations

from ..domain import ImageInput
from ..ports import Database, Row
from .base import get_one
from .images import ImageService
from .preferences import PreferenceService
from .stylist import Stylist
from .users import UserService

SUMMARY_FIELDS = ("style_tags", "palette", "formality", "vibe", "pieces")


def look_row(uid: str, look: dict, *, image_id: str | None = None, pin_id: str | None = None,
             source_url: str | None = None) -> Row:
    return {"user_id": uid, "image_id": image_id, "pin_id": pin_id, "source_url": source_url,
            "style_tags": look.get("style_tags") or [], "palette": look.get("palette") or [],
            "formality": look.get("formality_1to5"), "vibe": look.get("vibe"), "pieces": look.get("pieces") or [],
            "raw": look}


def summarise_looks(rows: list[Row]) -> list[Row]:
    return [{k: r.get(k) for k in SUMMARY_FIELDS} for r in rows]


class InspirationService:
    def __init__(self, db: Database, users: UserService, images: ImageService, prefs: PreferenceService,
                 stylist: Stylist):
        self._db, self._users, self._images, self._prefs, self._stylist = db, users, images, prefs, stylist

    def add(self, uid: str, images: list[ImageInput]) -> list[Row]:
        self._users.get(uid)
        rows = []
        for image in images:
            stored = self._images.save(uid, "inspiration", image)
            look = self._stylist.tag_look(image.data_url)
            rows.append(self._db.insert("inspirations", look_row(uid, look, image_id=stored["id"],
                                                                 source_url=image.source_url)))
        return self._images.with_urls(rows)

    def from_pin(self, uid: str, pin_id: str) -> Row:
        """Promote a swipe-deck pin to inspiration (one call; also records it as a like). Idempotent."""
        self._users.get(uid)
        pin = get_one(self._db, "style_pins", id=pin_id)
        self._prefs.record(uid, [{"pin_id": pin_id, "liked": True}])
        if existing := self._db.select("inspirations", {"user_id": uid, "pin_id": pin_id}, limit=1):
            return self._images.with_urls(existing)[0]
        look = self._stylist.tag_look(pin["image_url"])
        row = self._db.insert("inspirations", look_row(uid, look, pin_id=pin_id, source_url=pin["image_url"]))
        return self._images.with_urls([row])[0]

    def items(self, uid: str) -> list[Row]:
        return self._db.select("inspirations", {"user_id": uid}, order_by="created_at", desc=True)

    def list(self, uid: str) -> list[Row]:
        return self._images.with_urls(self.items(uid))

    def get(self, uid: str, inspiration_id: str) -> Row:
        return self._images.with_urls([get_one(self._db, "inspirations", id=inspiration_id, user_id=uid)])[0]

    def delete(self, uid: str, inspiration_id: str) -> None:
        self.get(uid, inspiration_id)
        self._db.delete("inspirations", {"id": inspiration_id, "user_id": uid})

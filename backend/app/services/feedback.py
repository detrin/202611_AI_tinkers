"""Product feedback drives the wishlist: liked → wanted item, bought → owned (status flip, no re-tagging)."""
from ..ports import Database, Row
from .base import get_one
from .wardrobe import OWNED, WANTED, WardrobeService


class ProductFeedbackService:
    def __init__(self, db: Database, wardrobe: WardrobeService):
        self._db, self._wardrobe = db, wardrobe

    def record(self, uid: str, product_id: str, liked: bool | None, bought: bool) -> Row:
        product = get_one(self._db, "products", id=product_id)
        self._db.upsert("product_feedback", [{"user_id": uid, "product_id": product_id, "liked": liked,
                                              "bought": bought}], "user_id,product_id")
        item = self._wardrobe.for_product(uid, product_id)
        if bought:
            item = self._wardrobe.mark_owned(uid, item["id"]) if item else self._wardrobe.add_product(uid, product, OWNED)
        elif liked and not item:
            item = self._wardrobe.add_product(uid, product, WANTED)
        return {"ok": True, "item_id": item and item["id"], "status": item and item["status"]}

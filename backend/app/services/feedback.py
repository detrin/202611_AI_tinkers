"""Product feedback. A bought product becomes a wardrobe item."""
from ..ports import Database, Row
from .base import get_one
from .images import ImageService
from .wardrobe import WardrobeService


class ProductFeedbackService:
    def __init__(self, db: Database, images: ImageService, wardrobe: WardrobeService):
        self._db, self._images, self._wardrobe = db, images, wardrobe

    def record(self, uid: str, product_id: str, liked: bool | None, bought: bool) -> Row:
        product = get_one(self._db, "products", id=product_id)
        self._db.upsert("product_feedback", [{"user_id": uid, "product_id": product_id, "liked": liked,
                                              "bought": bought}], "user_id,product_id")
        added = self._wardrobe.add(uid, [self._images.from_url(product["image_url"])]) if bought and product.get("image_url") else []
        return {"ok": True, "added_to_wardrobe": [i["id"] for i in added]}

from ..domain import ImageInput
from ..ports import Database, Row
from .base import get_one
from .images import ImageService
from .stylist import Stylist


class UserService:
    def __init__(self, db: Database, images: ImageService, stylist: Stylist):
        self._db, self._images, self._stylist = db, images, stylist

    def create(self, data: Row) -> Row:
        return self._db.insert("users", data)

    def get(self, uid: str) -> Row:
        return get_one(self._db, "users", id=uid)

    def update(self, uid: str, patch: Row) -> Row:
        self.get(uid)
        return self._db.update("users", {"id": uid}, patch)[0] if patch else self.get(uid)

    def analyse_selfie(self, uid: str, image: ImageInput) -> dict:
        self.get(uid)
        self._images.save(uid, "selfie", image)
        profile = self._stylist.color_analysis(image.data_url)
        self._db.update("users", {"id": uid}, {"color_profile": profile})
        return profile

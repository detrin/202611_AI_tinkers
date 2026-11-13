"""Daily outfit: weather + event + wardrobe → outfit from owned items only."""
from __future__ import annotations

from datetime import date

from ..errors import Conflict, Invalid
from ..ports import Database, Row, WeatherProvider
from .base import get_one
from .images import ImageService
from .stylist import Stylist
from .users import UserService
from .wardrobe import WardrobeService, summarise

RECENT_OUTFITS = 3


class OutfitService:
    def __init__(self, db: Database, users: UserService, wardrobe: WardrobeService, images: ImageService,
                 weather: WeatherProvider, stylist: Stylist):
        self._db, self._users, self._wardrobe, self._images, self._weather, self._stylist = (
            db, users, wardrobe, images, weather, stylist)

    def daily(self, uid: str, event: str, city: str | None = None, day: date | None = None) -> Row:
        user = self._users.get(uid)
        if not (city := city or user.get("city")):
            raise Invalid("city missing (set it on the user or in the request)")
        if not (items := self._wardrobe.items(uid)):
            raise Conflict("Wardrobe is empty")
        weather = self._weather.daily(city, day)
        outfit = self._stylist.daily_outfit(weather, event, summarise(items), user.get("color_profile"), self._recent(uid))
        owned = {i["id"] for i in items}
        saved = self._db.insert("outfits", {
            "user_id": uid, "date": (day or date.today()).isoformat(), "event": event, "city": city, "weather": weather,
            "item_ids": [i for i in outfit.get("item_ids", []) if i in owned],
            "explanation": outfit.get("explanation"), "missing_item_tip": outfit.get("missing_item_tip")})
        return saved | {"items": self._images.with_urls([i for i in items if i["id"] in saved["item_ids"]])}

    def _recent(self, uid: str) -> list[str]:
        outfits = self._db.select("outfits", {"user_id": uid}, order_by="created_at", desc=True, limit=RECENT_OUTFITS)
        return [i for o in outfits for i in o.get("item_ids") or []]

    def list(self, uid: str) -> list[Row]:
        return self._db.select("outfits", {"user_id": uid}, order_by="created_at", desc=True)

    def feedback(self, uid: str, outfit_id: str, feedback: Row) -> Row:
        get_one(self._db, "outfits", id=outfit_id, user_id=uid)
        return self._db.update("outfits", {"id": outfit_id, "user_id": uid}, {"feedback": feedback})[0]

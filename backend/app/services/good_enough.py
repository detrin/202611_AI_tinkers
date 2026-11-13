"""Is it good enough? A photo of the look you're wearing → "hell yeah" / "hell nah" + why.

Weather only when a location is attached (current coordinates, a city, or the user's saved city).
Wardrobe context is opt-in: by default the look is judged on its own."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..domain import ImageInput
from ..errors import Invalid
from ..ports import Row, WeatherProvider
from .stylist import Stylist
from .users import UserService
from .wardrobe import WardrobeService, summarise

log = logging.getLogger(__name__)
YEAH, NAH = "hell yeah", "hell nah"


@dataclass(frozen=True)
class Location:
    latitude: float | None = None
    longitude: float | None = None
    city: str | None = None

    @property
    def attached(self) -> bool:
        return self.has_coords or bool(self.city)

    @property
    def has_coords(self) -> bool:
        return self.latitude is not None and self.longitude is not None


class GoodEnoughService:
    def __init__(self, users: UserService, wardrobe: WardrobeService, weather: WeatherProvider, stylist: Stylist):
        self._users, self._wardrobe, self._weather, self._stylist = users, wardrobe, weather, stylist

    def check(self, uid: str, image: ImageInput, location: Location, use_saved_city: bool = False,
              include_wardrobe: bool = False, occasion: str | None = None) -> Row:
        user = self._users.get(uid)
        if (location.latitude is None) != (location.longitude is None):
            raise Invalid("Send both latitude and longitude, or neither")
        if not location.attached and use_saved_city:
            location = Location(city=user.get("city"))
        weather, location_source = self._weather_for(location), self._source(location)
        wardrobe = self._wardrobe.available(uid) if include_wardrobe else []
        context = {"occasion": occasion, "weather": weather, "colour_profile": user.get("color_profile"),
                   **({"wardrobe": summarise(wardrobe)} if include_wardrobe else {})}
        judged = self._stylist.good_enough(image.data_url, context)
        good = _as_bool(judged.get("good_enough"))
        owned = {i["id"] for i in wardrobe}
        return {
            "verdict": YEAH if good else NAH, "good_enough": good, "score_1to10": judged.get("score_1to10"),
            "explanation": judged.get("explanation") or "", "highlights": _points(judged.get("highlights")),
            "fixes": _points(judged.get("fixes")), "weather_note": (judged.get("weather_note") or None) if weather else None,
            "swap_item_ids": [i for i in judged.get("swap_item_ids") or [] if i in owned],
            "weather": weather, "location_source": location_source, "used_wardrobe": include_wardrobe,
        }

    def _weather_for(self, location: Location) -> Row | None:
        if not location.attached:
            return None
        try:
            if location.has_coords:
                return self._weather.now(latitude=location.latitude, longitude=location.longitude)
            return self._weather.now(city=location.city)
        except Exception as e:  # noqa: BLE001 — weather is a nice-to-have; the verdict still works without it
            log.warning("good-enough weather lookup failed: %s", e)
            return None

    @staticmethod
    def _source(location: Location) -> str | None:
        return "coordinates" if location.has_coords else "city" if location.city else None


def _points(value, limit: int = 3) -> list[Row]:
    """[{title, detail}], at most `limit`. Models sometimes answer with plain strings: those become titles."""
    out = []
    for p in value if isinstance(value, list) else []:
        if isinstance(p, dict) and (p.get("title") or "").strip():
            out.append({"title": p["title"].strip(), "detail": (p.get("detail") or "").strip()})
        elif isinstance(p, str) and p.strip():
            out.append({"title": p.strip(), "detail": ""})
    return out[:limit]


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "hell yeah"}
    return bool(value)

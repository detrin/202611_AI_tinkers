import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

import anyio

from ..errors import Conflict, Invalid, Unavailable
from ..outfit_mcp import outfit_mcp, read_outfit_tools
from ..ports import CalendarProvider, HourlyWeatherProvider, Row, VenueProvider
from .outfits import OutfitService
from .stylist import Stylist
from .users import UserService
from .wardrobe import summarise

log = logging.getLogger(__name__)
TOOL_STEPS = {
    "get_wardrobe": ("items", "available wardrobe items"),
    "get_calendar_events": ("events", "calendar events"),
    "get_weather": ("hourly", "hourly forecast entries"),
    "get_recent_outfits": ("item_ids", "item IDs from recent outfits"),
}


def weather_for_day(forecast: Row, events: list[Row]) -> Row:
    hours = forecast.get("hourly") or []
    if not hours:
        return {}
    by_time = [(datetime.fromisoformat(hour["time"]), hour) for hour in hours]
    for event in events:
        start = datetime.fromisoformat(event["start_time"]).timestamp()
        # Open-Meteo's probability describes the hour ending at the timestamp.
        event["weather"] = next(
            (hour for time, hour in by_time if start <= time.timestamp() < start + 3600),
            None,
        )
    daytime = [hour for time, hour in by_time if 8 <= time.hour <= 20]
    selected = next((event["weather"] for event in events if event["weather"]), None)
    if selected is None:
        selected = next((hour for time, hour in by_time if time.hour == 12), hours[0])
    return {
        "city": forecast["city"], **selected,
        "daytime": [hour for hour in daytime if datetime.fromisoformat(hour["time"]).hour in (8, 12, 17, 20)],
    }


def outcome_ids(answer: object, items: list[Row]) -> list[str]:
    ids = answer.get("item_ids") if isinstance(answer, dict) else None
    if not isinstance(ids, list):
        return []
    allowed = {item["id"] for item in items}
    return list(dict.fromkeys(i for i in ids if isinstance(i, str) and i in allowed))


class TodayService:
    def __init__(self, users: UserService, outfits: OutfitService, stylist: Stylist,
                 calendar: CalendarProvider | None, weather: HourlyWeatherProvider | None,
                 venue: VenueProvider | None, timezone: str):
        self._users, self._outfits, self._stylist = users, outfits, stylist
        self._calendar, self._weather, self._venue = calendar, weather, venue
        self._zone = ZoneInfo(timezone)

    async def _read_context(self, uid: str, user: Row, day: date) -> tuple[Row, list[Row]]:
        server = outfit_mcp(self._outfits, uid, user, day, self._zone.key, self._calendar, self._weather)
        try:
            with anyio.fail_after(13):
                results = await read_outfit_tools(server)
        except Exception:
            log.warning("Internal outfit MCP session unavailable")
            results = {}

        steps = []
        for name, (field, label) in TOOL_STEPS.items():
            value = results.get(name, {}).get(field)
            steps.append({"tool": name, "summary": f"{len(value)} {label}" if value is not None else "Unavailable"})
        mode = results.get("get_commute", {}).get("mode")
        steps.append({"tool": "get_commute", "summary": f"Usual transport: {mode}" if mode else "No transport set"})
        return results, steps

    async def _pick(self, inputs: Row, events: list[Row], city: str, steps: list[Row]) -> Row:
        can_lookup = self._venue is not None and any(event.get("location") for event in events)
        with anyio.fail_after(10):
            draft = await anyio.to_thread.run_sync(
                self._stylist.today_outfit, inputs, can_lookup, abandon_on_cancel=True,
            )
        index = draft.get("venue_event_index") if isinstance(draft, dict) else None
        if not can_lookup or type(index) is not int or not 0 <= index < len(events):
            return draft
        event = events[index]
        if not event.get("location"):
            return draft

        try:
            with anyio.fail_after(23):
                category = await self._venue.category(event["location"], city)
        except Exception:
            log.warning("Apify venue lookup unavailable")
            category = None
        steps.append({"tool": "compass/crawler-google-places", "summary": f"Venue type: {category}" if category else "Venue type unavailable"})
        if category:
            event["place_category"] = category
        if not category and outcome_ids(draft, inputs["wardrobe"]):
            return draft
        # The first answer may only contain the lookup request.
        try:
            with anyio.fail_after(6):
                return await anyio.to_thread.run_sync(self._stylist.today_outfit, inputs, False, abandon_on_cancel=True)
        except Exception:
            if outcome_ids(draft, inputs["wardrobe"]):
                return draft
            raise

    async def today(self, uid: str, day: date | None = None, note: str | None = None) -> Row:
        user = await anyio.to_thread.run_sync(self._users.get, uid, abandon_on_cancel=True)
        city = user.get("city")
        if not city:
            raise Invalid("city missing (set it on the user)")
        day = day or datetime.now(self._zone).date()
        tools, steps = await self._read_context(uid, user, day)
        wardrobe = tools.get("get_wardrobe", {}).get("items")
        mcp_wardrobe_unavailable = wardrobe is None
        if wardrobe is None:
            try:
                with anyio.fail_after(4):
                    wardrobe = summarise(await anyio.to_thread.run_sync(
                        self._outfits.available, uid, abandon_on_cancel=True,
                    ))
            except Exception:
                raise Unavailable("Wardrobe is temporarily unavailable") from None
        if not wardrobe:
            raise Conflict("No owned clothes are currently available")
        events = tools.get("get_calendar_events", {}).get("events") or []
        forecast = tools.get("get_weather", {})
        weather = weather_for_day(forecast, events)
        commute = tools.get("get_commute", {})
        recent = tools.get("get_recent_outfits", {}).get("item_ids") or []
        context = {"events": events, "weather": weather, "commute": commute}
        inputs = context | {"note": note, "wardrobe": wardrobe, "recent_item_ids": recent,
                            "style_profile": user.get("style_profile"), "color_profile": user.get("color_profile")}
        event_summary = events[0]["title"] if events else "casual day"
        outfit = None
        if not mcp_wardrobe_unavailable:
            try:
                with anyio.fail_after(36):
                    outfit = await self._pick(inputs, events, city, steps)
            except Exception:
                log.warning("Today picker unavailable")

        from_fallback = not outcome_ids(outfit, wardrobe)
        if from_fallback:
            log.warning("Today picker fell back to the daily stylist")
            occasion = f"{event_summary}. User note: {note}" if note else event_summary
            try:
                with anyio.fail_after(8):
                    outfit = await anyio.to_thread.run_sync(
                        self._stylist.daily_outfit, weather, occasion, wardrobe,
                        user.get("color_profile"), recent, abandon_on_cancel=True,
                    )
            except Exception:
                raise Unavailable("An outfit could not be generated. Try again.") from None

        # Recheck availability after the model runs. A garment may have moved to the laundry meanwhile.
        current = await anyio.to_thread.run_sync(self._outfits.available, uid, abandon_on_cancel=True)
        still_available = {item["id"] for item in current}
        ids = [item_id for item_id in outcome_ids(outfit, wardrobe) if item_id in still_available]
        if not ids:
            raise Conflict("No recommended items are still available. Try again.")
        saved = await anyio.to_thread.run_sync(
            self._outfits.save, uid, event_summary, city, day, weather, current, outfit | {"item_ids": ids},
        )
        return saved | {"context": context, "steps": steps, "from_fallback": from_fallback}

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import recurring_ical_events
import requests
from icalendar import Calendar as ICalendar


def events_on_day(content: bytes, day: date, timezone: str) -> list[dict]:
    zone = ZoneInfo(timezone)
    start = datetime.combine(day, time.min, zone)
    end = start + timedelta(days=1)
    calendar = ICalendar.from_ical(content)
    events = []
    for event in recurring_ical_events.of(calendar).between(start, end):
        begins = event.decoded("DTSTART", None)
        if not isinstance(begins, datetime) or str(event.get("STATUS", "")).upper() == "CANCELLED":
            continue
        begins = begins.replace(tzinfo=zone) if begins.tzinfo is None else begins.astimezone(zone)
        if not start <= begins < end:
            continue
        ends = event.decoded("DTEND", None)
        if isinstance(ends, datetime):
            ends = ends.replace(tzinfo=zone) if ends.tzinfo is None else ends.astimezone(zone)
        events.append({
            "title": str(event.get("SUMMARY") or "Calendar event"),
            "start_time": begins.isoformat(),
            "end_time": ends.isoformat() if isinstance(ends, datetime) else None,
            "location": str(event["LOCATION"]) if event.get("LOCATION") else None,
        })
    return sorted(events, key=lambda event: datetime.fromisoformat(event["start_time"]).timestamp())


class ICalCalendar:
    def __init__(self, url: str, demo_user_id: str, session: requests.Session | None = None):
        self._url, self._user_id, self._session = url, demo_user_id, session or requests.Session()

    def events(self, uid: str, day: date, timezone: str) -> list[dict] | None:
        if uid != self._user_id:
            return None
        try:
            response = self._session.get(self._url, timeout=5, allow_redirects=False)
            if response.status_code != 200:
                raise ValueError("Calendar feed did not return HTTP 200")
            return events_on_day(response.content, day, timezone)
        except Exception:
            # HTTP and parser errors can include the private URL or calendar contents.
            raise RuntimeError("Calendar feed unavailable") from None

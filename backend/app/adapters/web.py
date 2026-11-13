"""HTTP adapters: image fetching and Open-Meteo weather."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests

UA = {"User-Agent": "wardrobe-stylist/0.1"}


class HttpImageFetcher:
    def __init__(self, session: requests.Session | None = None, timeout: int = 30):
        self._s, self._timeout = session or requests.Session(), timeout

    def fetch(self, url: str) -> bytes:
        r = self._s.get(url, headers=UA, timeout=self._timeout)
        r.raise_for_status()
        return r.content


class OpenMeteoWeather:
    GEO = "https://geocoding-api.open-meteo.com/v1/search"
    FORECAST = "https://api.open-meteo.com/v1/forecast"
    DAILY = "temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max,weather_code"
    HOURLY = "temperature_2m,apparent_temperature,precipitation_probability"

    def __init__(self, session: requests.Session | None = None):
        self._s = session or requests.Session()

    def daily(self, city: str, day: date | None = None) -> dict:
        hits = self._s.get(self.GEO, params={"name": city, "count": 1}, timeout=15).json().get("results")
        if not hits:
            raise ValueError(f"Unknown city: {city}")
        g = hits[0]
        params = {"latitude": g["latitude"], "longitude": g["longitude"], "timezone": "auto", "daily": self.DAILY}
        params |= {"start_date": day.isoformat(), "end_date": day.isoformat()} if day else {"forecast_days": 1}
        d = self._s.get(self.FORECAST, params=params, timeout=15).json()["daily"]
        return {"city": g["name"], "country": g.get("country"), **{k: v[0] for k, v in d.items()}}

    def hourly(self, city: str, day: date, timezone: str) -> dict:
        response = self._s.get(self.GEO, params={"name": city, "count": 1}, timeout=5)
        response.raise_for_status()
        hits = response.json().get("results")
        if not hits:
            raise ValueError("Unknown city")
        location = hits[0]
        params = {
            "latitude": location["latitude"], "longitude": location["longitude"], "timezone": timezone,
            "start_date": day.isoformat(), "end_date": day.isoformat(), "hourly": self.HOURLY,
            "timeformat": "unixtime",
        }
        response = self._s.get(self.FORECAST, params=params, timeout=5)
        response.raise_for_status()
        forecast = response.json()["hourly"]
        zone = ZoneInfo(timezone)
        hours = [
            {"time": datetime.fromtimestamp(time, zone).isoformat(),
             "temperature_c": temperature, "feels_like_c": apparent,
             "rain_probability": probability / 100 if probability is not None else None}
            for time, temperature, apparent, probability in zip(
                forecast["time"], forecast["temperature_2m"], forecast["apparent_temperature"],
                forecast["precipitation_probability"], strict=True,
            )
        ]
        return {"city": location["name"], "timezone": timezone, "hourly": hours}

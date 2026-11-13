"""Abstractions the services depend on (dependency inversion). Adapters implement them; tests fake them."""
from collections.abc import Callable, Sequence
from datetime import date
from typing import Protocol

from .domain import AestheticPage, Pin, Product, SocialPost, TrendSeries

Row = dict


class Database(Protocol):
    def insert(self, table: str, row: Row) -> Row: ...
    def upsert(self, table: str, rows: list[Row], on_conflict: str) -> list[Row]: ...
    def update(self, table: str, where: Row, patch: Row) -> list[Row]: ...
    def delete(self, table: str, where: Row) -> None: ...
    def select(self, table: str, where: Row | None = None, *, contains: Row | None = None,
               in_: dict[str, list] | None = None, order_by: str | None = None, desc: bool = False,
               limit: int | None = None) -> list[Row]: ...


class ChatModel(Protocol):
    def complete(self, prompt: str, images: Sequence[str] = ()) -> str: ...


class ImageStore(Protocol):
    def put(self, path: str, content: bytes, mime: str) -> None: ...
    def signed_url(self, path: str) -> str | None: ...


class ImageFetcher(Protocol):
    def fetch(self, url: str) -> bytes: ...


class PinSource(Protocol):
    def search(self, query: str, limit: int) -> list[Pin]: ...


class ProductSource(Protocol):
    def search(self, query: str, marketplaces: list[str], limit: int) -> list[Product]: ...
    def details(self, url: str) -> list[Product]: ...


class SocialSource(Protocol):
    def posts(self, url: str, limit: int) -> list[SocialPost]: ...


class AestheticSource(Protocol):
    def pages(self, titles: list[str]) -> list[AestheticPage]: ...


class TrendSource(Protocol):
    def interest(self, terms: list[str], geo: str = "") -> list[TrendSeries]: ...


class WeatherProvider(Protocol):
    def daily(self, city: str, day: date | None = None) -> dict: ...
    def now(self, city: str | None = None, latitude: float | None = None, longitude: float | None = None) -> dict: ...


class StructuredModel(Protocol):
    """A strong reasoning model that returns JSON matching `schema` (e.g. Claude Opus via the CLI)."""
    model: str

    def generate(self, prompt: str, schema: dict) -> dict: ...


class HourlyWeatherProvider(Protocol):
    def hourly(self, city: str, day: date, timezone: str) -> Row: ...


class CalendarProvider(Protocol):
    def events(self, uid: str, day: date, timezone: str) -> list[Row] | None: ...


class VenueProvider(Protocol):
    async def category(self, location: str, city: str) -> str | None: ...


class Executor(Protocol):
    def submit(self, fn: Callable[[], None]) -> None: ...

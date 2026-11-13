"""Abstractions the services depend on (dependency inversion). Adapters implement them; tests fake them."""
from collections.abc import Callable, Sequence
from datetime import date
from typing import Protocol

from .domain import Pin, Product

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


class WeatherProvider(Protocol):
    def daily(self, city: str, day: date | None = None) -> dict: ...


class Executor(Protocol):
    def submit(self, fn: Callable[[], None]) -> None: ...

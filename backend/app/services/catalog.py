"""Product catalog: scrape via ProductSource, persist (deduplicated by URL) in `products`."""
from dataclasses import asdict

from ..domain import Product
from ..errors import Invalid
from ..ports import Database, ProductSource, Row


class CatalogService:
    def __init__(self, db: Database, source: ProductSource):
        self._db, self._source = db, source

    def _save(self, products: list[Product], query: str | None = None) -> list[Row]:
        rows = {p.url: asdict(p) | {"query": query} for p in products}   # dedupe by url
        return self._db.upsert("products", list(rows.values()), "url")

    def search(self, query: str, marketplaces: list[str], limit: int) -> list[Row]:
        return self._save(self._source.search(query, marketplaces, limit), query)

    def from_url(self, url: str) -> Row:
        rows = self._save(self._source.details(url))
        if not rows:
            raise Invalid(f"Could not scrape a product from {url}")
        return rows[0]

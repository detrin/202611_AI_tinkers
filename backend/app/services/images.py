"""Image ingestion (upload/URL → storage + images row) and signed-URL decoration."""
import uuid

from ..domain import ImageInput, sniff_mime
from ..errors import Invalid
from ..ports import Database, ImageFetcher, ImageStore, Row


class ImageService:
    def __init__(self, db: Database, store: ImageStore, fetcher: ImageFetcher):
        self._db, self._store, self._fetcher = db, store, fetcher

    def from_url(self, url: str) -> ImageInput:
        try:
            content = self._fetcher.fetch(url)
            return ImageInput(content, sniff_mime(content), source_url=url)
        except Exception as e:  # noqa: BLE001 — any fetch failure is a client input problem
            raise Invalid(f"Could not fetch image {url}: {e}") from e

    def save(self, user_id: str | None, kind: str, image: ImageInput) -> Row:
        path = f"{user_id or 'shared'}/{kind}/{uuid.uuid4()}.{image.extension}"
        self._store.put(path, image.content, image.mime)
        return self._db.insert("images", {"user_id": user_id, "kind": kind, "bucket_path": path,
                                          "source_url": image.source_url})

    def with_urls(self, rows: list[Row]) -> list[Row]:
        ids = [r["image_id"] for r in rows if r.get("image_id")]
        paths = {i["id"]: i["bucket_path"] for i in self._db.select("images", in_={"id": ids})} if ids else {}
        urls = self._sign_all([p for p in dict.fromkeys(paths.values()) if p])
        return [{**r, "image_url": urls.get(paths.get(r.get("image_id"))) or r.get("source_url")} for r in rows]

    def _sign_all(self, paths: list[str]) -> dict[str, str | None]:
        """Batch-sign when the store supports it (one request), else one by one."""
        if batch := getattr(self._store, "signed_urls", None):
            return batch(paths)
        return {p: self._store.signed_url(p) for p in paths}

    def _signed(self, path: str | None) -> str | None:
        return self._store.signed_url(path) if path else None

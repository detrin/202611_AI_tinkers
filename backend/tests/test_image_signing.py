"""Signed image URLs: one batch request when the store supports it, and a retry on dropped connections."""
import httpx
import pytest

from backend.app.adapters.supabase import SupabaseImageStore, _retry
from backend.app.domain import ImageInput
from backend.app.services.images import ImageService

from .fakes import FakeFetcher, FakeStore, InMemoryDatabase


class BatchStore(FakeStore):
    def __init__(self):
        super().__init__()
        self.batches, self.singles = [], 0

    def signed_url(self, path):
        self.singles += 1
        return super().signed_url(path)

    def signed_urls(self, paths):
        self.batches.append(list(paths))
        return {p: f"https://batch/{p}" for p in paths}


def _rows(service, n):
    return [{"id": i, "image_id": service.save("u", "wardrobe", ImageInput(b"x"))["id"]} for i in range(n)]


def test_with_urls_signs_everything_in_one_batch():
    store = BatchStore()
    images = ImageService(InMemoryDatabase(), store, FakeFetcher())
    rows = _rows(images, 5) + [{"id": "no-image", "source_url": "https://shop/x.jpg"}]
    out = images.with_urls(rows)
    assert len(store.batches) == 1 and len(store.batches[0]) == 5 and store.singles == 0
    assert all(r["image_url"].startswith("https://batch/") for r in out[:5])
    assert out[5]["image_url"] == "https://shop/x.jpg"


def test_with_urls_falls_back_to_one_by_one():
    store = FakeStore()
    images = ImageService(InMemoryDatabase(), store, FakeFetcher())
    out = images.with_urls(_rows(images, 2))
    assert all(r["image_url"].startswith("https://signed/") for r in out)


def test_retry_recovers_from_one_dropped_connection_then_gives_up():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise httpx.RemoteProtocolError("Server disconnected")
        return "ok"
    assert _retry(flaky) == "ok" and len(calls) == 2

    def dead():
        raise httpx.RemoteProtocolError("Server disconnected")
    with pytest.raises(httpx.RemoteProtocolError):
        _retry(dead)


def test_supabase_store_maps_batch_response():
    class Bucket:
        def create_signed_urls(self, paths, ttl):
            return [{"path": "a", "signedURL": "https://s/a", "error": None}, {"path": "b", "signedURL": None, "error": "nope"}]

    class Client:
        storage = type("S", (), {"from_": staticmethod(lambda _b: Bucket())})

    assert SupabaseImageStore(Client(), "images", 60).signed_urls(["a", "b"]) == {"a": "https://s/a", "b": None}
    assert SupabaseImageStore(Client(), "images", 60).signed_urls([]) == {}

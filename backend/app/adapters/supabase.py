"""Supabase implementations of Database and ImageStore."""
import httpx
from supabase import Client

from ..ports import Row


class SupabaseDatabase:
    def __init__(self, client: Client):
        self._c = client

    @staticmethod
    def _filter(q, where: Row | None):
        for k, v in (where or {}).items():
            q = q.eq(k, v)
        return q

    def insert(self, table: str, row: Row) -> Row:
        return self._c.table(table).insert(row).execute().data[0]

    def upsert(self, table: str, rows: list[Row], on_conflict: str) -> list[Row]:
        return self._c.table(table).upsert(rows, on_conflict=on_conflict).execute().data if rows else []

    def update(self, table: str, where: Row, patch: Row) -> list[Row]:
        return self._filter(self._c.table(table).update(patch), where).execute().data

    def delete(self, table: str, where: Row) -> None:
        self._filter(self._c.table(table).delete(), where).execute()

    def select(self, table, where=None, *, contains=None, in_=None, order_by=None, desc=False, limit=None):
        q = self._filter(self._c.table(table).select("*"), where)
        for k, v in (contains or {}).items():
            q = q.contains(k, v)
        for k, v in (in_ or {}).items():
            q = q.in_(k, v)
        if order_by:
            q = q.order(order_by, desc=desc)
        if limit:
            q = q.limit(limit)
        return q.execute().data


class SupabaseImageStore:
    def __init__(self, client: Client, bucket: str, ttl: int):
        self._bucket = client.storage.from_(bucket)
        self._ttl = ttl

    def put(self, path: str, content: bytes, mime: str) -> None:
        self._bucket.upload(path, content, {"content-type": mime})

    def signed_url(self, path: str) -> str | None:
        r = _retry(lambda: self._bucket.create_signed_url(path, self._ttl))
        return r.get("signedURL") or r.get("signedUrl") or r.get("signed_url")

    def signed_urls(self, paths: list[str]) -> dict[str, str | None]:
        """One Storage request for many paths (a 74-item closet was 74 sequential requests, ~17 s)."""
        if not paths:
            return {}
        rows = _retry(lambda: self._bucket.create_signed_urls(paths, self._ttl))
        return {r["path"]: (None if r.get("error") else r.get("signedURL") or r.get("signedUrl")) for r in rows}


def _retry(call, attempts: int = 2):
    """Storage keeps idle keep-alive connections that the server sometimes drops ("Server disconnected");
    the next attempt opens a fresh one."""
    for i in range(attempts):
        try:
            return call()
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError):
            if i == attempts - 1:
                raise

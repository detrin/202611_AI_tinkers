"""Async jobs persisted in `jobs`; execution strategy is injected (thread pool in prod, inline in tests)."""
import logging
from collections.abc import Callable
from datetime import datetime, timezone

from ..ports import Database, Executor, Row
from .base import get_one

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobService:
    def __init__(self, db: Database, executor: Executor):
        self._db, self._executor = db, executor

    def submit(self, kind: str, user_id: str | None, payload: dict, work: Callable[[], dict]) -> Row:
        job = self._db.insert("jobs", {"kind": kind, "user_id": user_id, "input": payload, "status": "queued"})
        self._executor.submit(lambda: self._run(job["id"], work))
        return {"job_id": job["id"], "status": "queued"}

    def _run(self, job_id: str, work: Callable[[], dict]) -> None:
        self._set(job_id, status="running")
        try:
            self._set(job_id, status="done", result=work())
        except Exception as e:  # noqa: BLE001 — job failures are recorded, not raised
            log.exception("job %s failed", job_id)
            self._set(job_id, status="failed", error=repr(e)[:2000])

    def _set(self, job_id: str, **fields) -> None:
        self._db.update("jobs", {"id": job_id}, fields | {"updated_at": _now()})

    def get(self, job_id: str) -> Row:
        return get_one(self._db, "jobs", id=job_id)

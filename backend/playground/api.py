"""Thin HTTP client for the playground: every call is logged so the UI can show what was sent and received."""
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

TEST_USER_FILE = Path(__file__).resolve().parents[1] / "scripts" / "test_user.json"


def test_user_id() -> str:
    try:
        return json.loads(TEST_USER_FILE.read_text())["user_id"]
    except (OSError, KeyError, ValueError):
        return ""


@dataclass
class Call:
    method: str
    path: str
    status: int | None
    ms: int
    request: dict
    response: object


@dataclass
class Api:
    base: str
    timeout: float = 300
    log: list[Call] = field(default_factory=list)

    def request(self, method: str, path: str, **kw) -> tuple[int | None, object]:
        t0 = time.monotonic()
        try:
            r = requests.request(method, self.base.rstrip("/") + path, timeout=self.timeout, **kw)
            try:
                body = r.json()
            except ValueError:
                body = r.text
            status = r.status_code
        except requests.RequestException as e:
            status, body = None, f"{type(e).__name__}: {e}"
        sent = {k: v for k, v in kw.items() if k != "files"}
        if kw.get("files"):
            sent["files"] = [f[1][0] for f in kw["files"]]
        if path == "/health":
            return status, body
        self.log.insert(0, Call(method, path, status, int((time.monotonic() - t0) * 1000), sent, body))
        del self.log[50:]
        return status, body

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def patch(self, path, **kw):
        return self.request("PATCH", path, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    def wait_job(self, job_id: str, on_tick=None, every: float = 3, max_s: float = 600) -> dict:
        t0 = time.monotonic()
        while True:
            _, job = self.get(f"/jobs/{job_id}")
            if not isinstance(job, dict) or job.get("status") not in ("queued", "running"):
                return job
            if on_tick:
                on_tick(job, time.monotonic() - t0)
            if time.monotonic() - t0 > max_s:
                return job
            time.sleep(every)

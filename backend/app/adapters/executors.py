"""Executors for background jobs."""
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor


class ThreadExecutor:
    def __init__(self, workers: int = 4):
        self._pool = ThreadPoolExecutor(workers)

    def submit(self, fn: Callable[[], None]) -> None:
        self._pool.submit(fn)


class InlineExecutor:
    """Runs jobs synchronously — handy for tests and notebooks."""

    def submit(self, fn: Callable[[], None]) -> None:
        fn()

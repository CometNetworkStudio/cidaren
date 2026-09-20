"""平台级并发与请求间隔限流。

- 平台并发默认 2（全可配），同一账号串行。
- Agent 以线程池运行，故用 threading。
"""

from __future__ import annotations

import contextlib
import random
import threading
import time


class RateLimiter:
    def __init__(
        self,
        concurrency: int = 2,
        min_interval: float = 0.8,
        max_interval: float = 2.5,
    ) -> None:
        self._concurrency = max(1, concurrency)
        self._min_interval = max(0.0, min_interval)
        self._max_interval = max(self._min_interval, max_interval)
        self._guard = threading.Lock()
        self._semaphores: dict[str, threading.Semaphore] = {}
        self._account_locks: dict[tuple[str, str], threading.Lock] = {}
        self._last_request: dict[str, float] = {}

    def _semaphore(self, platform: str) -> threading.Semaphore:
        with self._guard:
            if platform not in self._semaphores:
                self._semaphores[platform] = threading.Semaphore(self._concurrency)
            return self._semaphores[platform]

    def account_lock(self, platform: str, account: str) -> threading.Lock:
        with self._guard:
            key = (platform, account)
            if key not in self._account_locks:
                self._account_locks[key] = threading.Lock()
            return self._account_locks[key]

    def _pace(self, platform: str) -> None:
        with self._guard:
            last = self._last_request.get(platform)
            now = time.monotonic()
            wait = 0.0
            if last is not None:
                wait = random.uniform(self._min_interval, self._max_interval) - (now - last)
            self._last_request[platform] = now + max(0.0, wait)
        if wait > 0:
            time.sleep(wait)

    @contextlib.contextmanager
    def platform_slot(self, platform: str):
        """占用平台并发额度，并按随机间隔节流。"""
        sem = self._semaphore(platform)
        sem.acquire()
        try:
            self._pace(platform)
            yield
        finally:
            sem.release()

    @contextlib.contextmanager
    def account_slot(self, platform: str, account: str):
        """同一账号串行 + 平台并发 + 节流。"""
        with self.account_lock(platform, account):
            with self.platform_slot(platform):
                yield

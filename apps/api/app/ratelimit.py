"""Limitatore semplice in memoria per i tentativi di login e 2FA.

Sufficiente per un'istanza singola (pilota). Con più istanze va spostato su Postgres o Redis.
"""

import threading
import time
from collections import deque


class RateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] > self.window:
            hits.popleft()
        return hits

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key, time.monotonic())) >= self.max_attempts

    def hit(self, key: str) -> None:
        with self._lock:
            self._prune(key, time.monotonic()).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


login_limiter = RateLimiter(max_attempts=5, window_seconds=15 * 60)
mfa_limiter = RateLimiter(max_attempts=5, window_seconds=15 * 60)

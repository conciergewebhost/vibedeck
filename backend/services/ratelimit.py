"""In-memory sliding-window rate limiter.

Process-local (a dict of timestamps guarded by a lock), which is sufficient
for the single-worker uvicorn deployment: every request shares the one
process, so the counts are consistent. Counters reset on restart, but an
attacker can't force restarts and the windows are short, so that's
acceptable. If the backend ever runs multiple workers or hosts, swap this
for a shared store (e.g. Redis) behind the same interface.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

# Drop a key entirely once its newest hit is older than this, so the table
# doesn't grow without bound as distinct client IPs come and go.
_MAX_AGE_SECONDS = 3600.0
_SWEEP_EVERY_SECONDS = 600.0


def client_ip(request) -> str:
    """Best-effort real client IP for rate-limiting.

    The backend binds to localhost and is only reachable through Caddy, which
    appends the connecting client's IP as the LAST X-Forwarded-For entry. We
    use the rightmost entry because earlier entries are client-supplied and
    therefore spoofable. With no XFF (a direct loopback caller, e.g. the SSR
    server) we fall back to the socket peer.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


class SlidingWindowLimiter:
    """Counts attempts per key within a trailing time window."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_sweep = 0.0

    def hit(
        self,
        key: str,
        limit: int,
        window_seconds: float,
        *,
        now: float | None = None,
    ) -> tuple[bool, int]:
        """Record an attempt for ``key``; return ``(allowed, retry_after)``.

        If the trailing ``window_seconds`` already holds ``limit`` attempts,
        the attempt is rejected (and NOT recorded) and ``retry_after`` is the
        whole seconds until the oldest attempt ages out. Otherwise the attempt
        is recorded and ``retry_after`` is 0.
        """
        now = time.monotonic() if now is None else now
        cutoff = now - window_seconds
        with self._lock:
            self._sweep(now)
            dq = self._hits[key]
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= limit:
                retry_after = int(dq[0] + window_seconds - now) + 1
                return False, max(retry_after, 1)
            dq.append(now)
            return True, 0

    def clear(self) -> None:
        """Forget all counts (used by tests)."""
        with self._lock:
            self._hits.clear()
            self._last_sweep = 0.0

    def _sweep(self, now: float) -> None:
        """Drop keys with no recent activity. Caller holds the lock."""
        if now - self._last_sweep < _SWEEP_EVERY_SECONDS:
            return
        self._last_sweep = now
        stale = [k for k, dq in self._hits.items() if not dq or dq[-1] <= now - _MAX_AGE_SECONDS]
        for k in stale:
            del self._hits[k]

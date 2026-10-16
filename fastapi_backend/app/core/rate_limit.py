"""
Request limits for sign-in, sign-up, password reset, public lookups and the
paid face checks, so nobody can guess passwords, list accounts or run up the
AWS bill by repeating a request.

Counts live in this process's memory: each server worker counts on its own
and counts reset on restart. For one shared, stricter limit, also rate-limit
these paths at the proxy or load balancer. Limits keyed by IP address need
the real client address: run uvicorn with --proxy-headers and set
FORWARDED_ALLOW_IPS to the proxy's address.
"""
import math
import threading
import time
from collections import deque

from fastapi import Request

from app.core.config import settings
from app.core.errors import ApiError


MAX_KEYS = 50_000

_hits: dict[str, deque[float]] = {}
_lock = threading.Lock()


def _prune(now: float) -> None:
    # Called with the lock held, only when the table is large: drops keys
    # with no recent requests (the longest window used is a day).
    for key in [k for k, q in _hits.items() if not q or now - q[-1] > 86_400]:
        del _hits[key]


def limit(key: str, max_requests: int, window_seconds: int) -> None:
    """Counts one request for `key`; refuses it (429) past `max_requests` per window."""
    if not settings.rate_limit_enabled:
        return

    now = time.monotonic()
    with _lock:
        if len(_hits) > MAX_KEYS:
            _prune(now)
        recent = _hits.setdefault(key, deque())
        while recent and now - recent[0] >= window_seconds:
            recent.popleft()
        if len(recent) >= max_requests:
            retry_after = math.ceil(window_seconds - (now - recent[0]))
            raise ApiError(
                429,
                "too_many_requests",
                "Too many attempts. Please wait a few minutes and try again.",
                headers={"Retry-After": str(max(retry_after, 1))},
            )
        recent.append(now)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def reset() -> None:
    """Forget all counts (tests)."""
    with _lock:
        _hits.clear()

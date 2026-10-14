"""
Address search for office locations, through OpenStreetMap's Nominatim.

Nominatim's usage policy (operations.osmfoundation.org/policies/nominatim):
at most one request per second for the whole application, a User-Agent
that names the app, no search-as-you-type, and caching where possible.
So every phone's search goes through here: one upstream request at a time,
at least a second apart, and answers are kept for a week.
"""

import threading
import time
from collections import OrderedDict

import httpx
from fastapi import HTTPException, status

from app.core.config import settings


MIN_INTERVAL_SECONDS = 1.1
CACHE_SECONDS = 7 * 24 * 3600
CACHE_SIZE = 500
MAX_RESULTS = 5

_lock = threading.Lock()
_last_request = 0.0
_cache: "OrderedDict[str, tuple[float, list[dict]]]" = OrderedDict()


def _cached(key: str) -> list[dict] | None:
    hit = _cache.get(key)
    if hit is None:
        return None
    stored_at, results = hit
    if time.monotonic() - stored_at > CACHE_SECONDS:
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)
    return results


def _remember(key: str, results: list[dict]) -> None:
    _cache[key] = (time.monotonic(), results)
    _cache.move_to_end(key)
    while len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)


def search_places(query: str) -> list[dict]:
    """Up to 5 places for an address or place name: name, latitude, longitude."""
    if not settings.geocoding_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Address search is switched off. Tap the map to place the office instead.",
        )

    key = " ".join(query.lower().split())

    global _last_request
    # One upstream request at a time, spaced out, for every user together.
    with _lock:
        cached = _cached(key)
        if cached is not None:
            return cached

        wait = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            response = httpx.get(
                settings.geocoding_url,
                params={"format": "jsonv2", "q": query, "limit": MAX_RESULTS},
                headers={"User-Agent": settings.geocoding_user_agent},
                timeout=10,
            )
            response.raise_for_status()
            rows = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Address search isn't answering right now. Try again, or tap the map.",
            ) from exc
        finally:
            _last_request = time.monotonic()

        results = [
            {
                "name": row.get("display_name", ""),
                "latitude": float(row["lat"]),
                "longitude": float(row["lon"]),
            }
            for row in rows
            if "lat" in row and "lon" in row
        ]
        _remember(key, results)
        return results

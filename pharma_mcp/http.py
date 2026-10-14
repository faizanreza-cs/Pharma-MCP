"""Shared async HTTP client: TTL cache, polite rate limiting and retries.

Public health APIs throttle aggressively (openFDA: 240 requests/minute and 1,000/day without a
key). Caching identical requests and spacing calls keeps an assistant that asks many follow-up
questions inside those limits.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

MAX_RETRY_AFTER_S = 30.0
MAX_CACHE_ENTRIES = 1024


class NotFound(Exception):
    """The API answered 'no matching records'. Callers turn this into an empty result."""


class UpstreamError(Exception):
    pass


class ApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        min_interval_s: float = 0.25,
        ttl_s: float = 3600,
        retries: int = 3,
        timeout_s: float = 20.0,
        default_params: dict | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.min_interval_s = min_interval_s
        self.ttl_s = ttl_s
        self.retries = retries
        self.default_params = default_params or {}
        self._client = httpx.AsyncClient(
            timeout=timeout_s, transport=transport, headers={"User-Agent": "pharma-mcp/0.1"}
        )
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()
        self._last = 0.0

    def _key(self, path: str, params: dict[str, Any]) -> str:
        return path + "?" + json.dumps(params, sort_keys=True)

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        params = {**self.default_params, **(params or {})}
        params = {k: v for k, v in params.items() if v not in (None, "")}
        key = self._key(path, params)
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < self.ttl_s:
            return hit[1]

        delay = 1.0
        for attempt in range(self.retries + 1):
            async with self._lock:  # space requests out
                wait = self.min_interval_s - (time.monotonic() - self._last)
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last = time.monotonic()
            try:
                r = await self._client.get(f"{self.base_url}{path}", params=params)
            except httpx.TransportError as e:
                if attempt == self.retries:
                    raise UpstreamError(f"network error: {e}") from e
                await asyncio.sleep(delay)
                delay *= 2
                continue
            if r.status_code == 404:
                raise NotFound(path)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                try:  # Retry-After may also be an HTTP date; cap long waits
                    wait = min(float(r.headers["retry-after"]), MAX_RETRY_AFTER_S)
                except (KeyError, ValueError):
                    wait = delay
                await asyncio.sleep(wait)
                delay *= 2
                continue
            if r.status_code >= 400:
                raise UpstreamError(f"HTTP {r.status_code}: {r.text[:200]}")
            data = r.json()
            self._cache.pop(key, None)
            if len(self._cache) >= MAX_CACHE_ENTRIES:  # dicts keep insertion order: drop oldest
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (time.monotonic(), data)
            return data
        raise UpstreamError("retries exhausted")

    async def aclose(self) -> None:
        await self._client.aclose()

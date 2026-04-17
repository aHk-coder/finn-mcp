from __future__ import annotations

import asyncio
import random
from typing import Any

import httpx

from . import config


class RateLimitedError(Exception):
    def __init__(self, retry_after: int = 60):
        super().__init__(f"finn.no rate-limited (retry after {retry_after}s)")
        self.retry_after = retry_after


class NotFoundError(Exception):
    pass


_client: httpx.AsyncClient | None = None
_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(1)
    return _semaphore


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            http2=True,
            timeout=config.HTTP_TIMEOUT_SECONDS,
            headers={
                "User-Agent": config.USER_AGENT,
                "Accept-Language": "nb-NO,nb;q=0.9,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            follow_redirects=True,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def fetch(url: str, *, params: dict[str, Any] | None = None, polite: bool = True) -> str:
    client = await get_client()
    sem = _get_semaphore()
    async with sem:
        if polite:
            await asyncio.sleep(
                random.uniform(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX)
            )
        for attempt in (1, 2):
            try:
                response = await client.get(url, params=params)
            except (httpx.TimeoutException, httpx.RemoteProtocolError):
                if attempt == 2:
                    raise
                await asyncio.sleep(2.0 + random.uniform(0, 3.0))
                continue

            if response.status_code == 404:
                raise NotFoundError(url)
            if response.status_code == 429:
                if attempt == 1:
                    await asyncio.sleep(30.0)
                    continue
                raise RateLimitedError(retry_after=60)
            if 500 <= response.status_code < 600 and attempt == 1:
                await asyncio.sleep(2.0 + random.uniform(0, 3.0))
                continue
            response.raise_for_status()
            return response.text

        raise RuntimeError(f"unreachable: exhausted retries for {url}")

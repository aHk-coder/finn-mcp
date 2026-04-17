from __future__ import annotations

import logging

from .. import http_client
from ..cache import Cache
from ..models import ALL_VERTICALS, Listing, SearchResult, Vertical
from ..scraper import get_scraper
from .base import FinnBackend, ListingNotFound

log = logging.getLogger(__name__)

# Probe order when the caller hasn't supplied a vertical. Roughly by popularity.
_VERTICAL_PROBE_ORDER: tuple[Vertical, ...] = (
    "cars_used",
    "bap",
    "homes",
    "lettings",
    "jobs",
)


class ScraperBackend(FinnBackend):
    name = "scraper"

    def __init__(self, cache: Cache | None = None):
        self.cache = cache or Cache()

    async def search(
        self,
        vertical: Vertical,
        query: str,
        page: int = 1,
        filters: dict[str, str] | None = None,
    ) -> list[SearchResult]:
        if vertical not in ALL_VERTICALS:
            raise ValueError(f"unknown vertical: {vertical}")
        scraper = get_scraper(vertical)
        return await scraper.search(query=query, page=page, filters=filters)

    async def get_listing(
        self,
        finnkode: str,
        vertical: Vertical | None = None,
    ) -> Listing:
        if not finnkode or not finnkode.isdigit():
            raise ValueError(f"invalid finnkode: {finnkode!r}")

        if vertical is None:
            vertical = await self.cache.vertical_hint(finnkode)

        cached = await self.cache.get_listing(finnkode)
        if cached is not None and (vertical is None or cached.vertical == vertical):
            return cached

        if vertical is not None:
            return await self._fetch_and_cache(finnkode, vertical)

        # No hint, no cache — probe each vertical until one returns 200.
        last_exc: Exception | None = None
        for candidate in _VERTICAL_PROBE_ORDER:
            try:
                return await self._fetch_and_cache(finnkode, candidate)
            except http_client.NotFoundError:
                continue
            except Exception as exc:  # network, parse, etc.
                log.warning("probe %s failed for %s: %s", candidate, finnkode, exc)
                last_exc = exc
                continue
        if last_exc is not None:
            raise last_exc
        raise ListingNotFound(finnkode)

    async def _fetch_and_cache(self, finnkode: str, vertical: Vertical) -> Listing:
        scraper = get_scraper(vertical)
        try:
            html, listing = await scraper.fetch_detail(finnkode)
        except http_client.NotFoundError:
            raise
        await self.cache.put_listing(listing, html)
        return listing

    async def aclose(self) -> None:
        await http_client.close_client()

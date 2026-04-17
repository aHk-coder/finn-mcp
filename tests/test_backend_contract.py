"""Contract tests shared across all FinnBackend implementations.

The scraper backend is exercised with local HTML fixtures served by a
stub HTTP fetch. The official API backend is skipped until it's wired up.
"""

from __future__ import annotations

import pytest

from finn_mcp import http_client
from finn_mcp.backend.api_backend import OfficialApiBackend
from finn_mcp.backend.scraper_backend import ScraperBackend
from finn_mcp.cache import Cache
from .conftest import read_fixture

SCRAPER_FIXTURE_MAP = {
    "https://www.finn.no/recommerce/forsale/search": "bap_search.html",
    "https://www.finn.no/recommerce/forsale/item/460211124": "bap_item.html",
    "https://www.finn.no/realestate/homes/search.html": "homes_search.html",
    "https://www.finn.no/realestate/homes/ad.html": "homes_ad.html",
    "https://www.finn.no/mobility/item/460212366": "mobility_item.html",
    "https://www.finn.no/job/search": "jobs_search.html",
    "https://www.finn.no/job/ad/459777164": "jobs_ad.html",
}


@pytest.fixture
def stub_http(monkeypatch):
    async def fake_fetch(url, params=None, polite=True):
        # Normalise ?finnkode=... into the base URL so the homes detail matches.
        for key, fixture in SCRAPER_FIXTURE_MAP.items():
            if url.startswith(key):
                return read_fixture(fixture)
        raise http_client.NotFoundError(url)

    monkeypatch.setattr(http_client, "fetch", fake_fetch)
    return fake_fetch


@pytest.fixture
def backends(tmp_path, stub_http):
    return [
        ScraperBackend(cache=Cache(db_path=tmp_path / "c.sqlite")),
        # OfficialApiBackend is a stub — included for future coverage,
        # currently expected to raise NotImplementedError in every test.
    ]


async def test_backend_search_bap(backends):
    for backend in backends:
        results = await backend.search("bap", query="iphone")
        assert results, f"{backend.name}: empty search"
        assert results[0].vertical == "bap"
        assert results[0].finnkode.isdigit()


async def test_backend_get_listing_bap(backends):
    for backend in backends:
        listing = await backend.get_listing("460211124", vertical="bap")
        assert listing.vertical == "bap"
        assert listing.title
        assert listing.price is not None


async def test_backend_get_listing_cached(backends):
    for backend in backends:
        first = await backend.get_listing("460211124", vertical="bap")
        # Second call should come from cache — same object shape.
        second = await backend.get_listing("460211124", vertical="bap")
        assert first.finnkode == second.finnkode
        assert first.title == second.title


async def test_backend_get_listing_probes_vertical_when_unknown(backends):
    for backend in backends:
        # 460211124 is a BAP item; vertical should be inferred.
        listing = await backend.get_listing("460211124", vertical=None)
        assert listing.vertical == "bap"


async def test_official_backend_raises_until_implemented():
    backend = OfficialApiBackend()
    with pytest.raises(NotImplementedError):
        await backend.search("bap", query="anything")
    with pytest.raises(NotImplementedError):
        await backend.get_listing("123", vertical="bap")

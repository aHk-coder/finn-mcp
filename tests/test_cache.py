from __future__ import annotations

from datetime import datetime, timezone

import pytest

from finn_mcp.cache import Cache
from finn_mcp.models import Listing, SavedSearch


@pytest.fixture
def cache(tmp_path):
    return Cache(db_path=tmp_path / "cache.sqlite")


def _make_listing(finnkode: str, vertical: str = "bap") -> Listing:
    return Listing(
        finnkode=finnkode,
        vertical=vertical,
        url=f"https://www.finn.no/recommerce/forsale/item/{finnkode}",
        title=f"Fixture listing {finnkode}",
        description="Test description",
        price=1000,
        currency="NOK",
        location="Oslo",
        images=[],
        attributes={"brand": "Test"},
        seller=None,
        published_at=None,
        fetched_at=datetime.now(tz=timezone.utc),
    )


async def test_put_and_get_listing(cache):
    listing = _make_listing("100000001")
    await cache.put_listing(listing, raw_html="<html></html>")

    recovered = await cache.get_listing("100000001")
    assert recovered is not None
    assert recovered.finnkode == "100000001"
    assert recovered.attributes["brand"] == "Test"


async def test_get_listing_respects_ttl(cache):
    listing = _make_listing("100000002")
    await cache.put_listing(listing, raw_html="")
    # A zero-second TTL forces a cache miss.
    assert await cache.get_listing("100000002", max_age_seconds=0) is None


async def test_vertical_hint_returned_independent_of_ttl(cache):
    listing = _make_listing("100000003", vertical="cars_used")
    await cache.put_listing(listing, raw_html="")
    assert await cache.vertical_hint("100000003") == "cars_used"
    assert await cache.vertical_hint("999") is None


async def test_saved_search_round_trip(cache):
    saved = SavedSearch(
        name="v90",
        vertical="cars_used",
        query="Volvo V90",
        filters={"price_to": "300000"},
    )
    await cache.save_search(saved)

    assert await cache.get_search("v90") is not None
    assert [s.name for s in await cache.list_searches()] == ["v90"]


async def test_saved_search_state_update_and_diff(cache):
    saved = SavedSearch(name="watch", vertical="bap", query="iphone")
    await cache.save_search(saved)

    now = datetime.now(tz=timezone.utc)
    await cache.update_search_state("watch", now, ["1", "2", "3"])

    reloaded = await cache.get_search("watch")
    assert reloaded is not None
    assert reloaded.last_checked_at is not None
    assert reloaded.last_finnkodes == ["1", "2", "3"]


async def test_delete_saved_search(cache):
    await cache.save_search(SavedSearch(name="x", vertical="bap", query="q"))
    assert await cache.delete_search("x") is True
    assert await cache.delete_search("x") is False

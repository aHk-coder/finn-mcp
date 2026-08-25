from __future__ import annotations

import pytest

from finn_mcp.scraper import get_scraper
from finn_mcp.scraper.base import parse_price_nok
from finn_mcp.scraper.jsonld import extract_jsonld, find_by_type
from .conftest import read_fixture


@pytest.mark.parametrize(
    "vertical,fixture,expected_first",
    [
        ("bap", "bap_search.html", "460054796"),
        ("homes", "homes_search.html", "459322772"),
        ("lettings", "lettings_search.html", "448510748"),
        ("cars_used", "cars_used_search.html", "459820662"),
        ("jobs", "jobs_search.html", "459777164"),
    ],
)
def test_search_cards_have_finnkode_and_title(vertical, fixture, expected_first):
    html = read_fixture(fixture)
    results = get_scraper(vertical).parse_search_cards(html)
    assert len(results) > 0, f"{vertical}: expected at least one search result"
    assert results[0].finnkode == expected_first
    assert results[0].vertical == vertical
    for r in results[:5]:
        assert r.finnkode and r.finnkode.isdigit()
        assert r.title
        assert r.url.startswith("http")


def test_bap_search_extracts_price_and_url():
    html = read_fixture("bap_search.html")
    results = get_scraper("bap").parse_search_cards(html)
    with_price = [r for r in results if r.price is not None]
    assert len(with_price) >= len(results) // 2
    assert any(r.url.startswith("https://www.finn.no/recommerce/forsale/item/") for r in results)


def test_cars_search_price_handles_pipe_separators():
    html = read_fixture("cars_used_search.html")
    results = get_scraper("cars_used").parse_search_cards(html)
    prices = [r.price for r in results if r.price]
    assert prices, "expected at least one car listing to yield a price"
    assert any(p > 50_000 for p in prices)


def test_cars_search_card_extras_include_year_and_mileage():
    html = read_fixture("cars_used_search.html")
    results = get_scraper("cars_used").parse_search_cards(html)
    with_year = [r for r in results if "year" in r.extra]
    assert len(with_year) >= 3
    assert any("mileage_km" in r.extra for r in results)


def test_homes_search_card_extras_include_area_and_rooms():
    html = read_fixture("homes_search.html")
    results = get_scraper("homes").parse_search_cards(html)
    with_area = [r for r in results if "area_m2" in r.extra]
    assert len(with_area) >= 5


def test_lettings_search_extracts_rent():
    html = read_fixture("lettings_search.html")
    results = get_scraper("lettings").parse_search_cards(html)
    rents = [r.price for r in results if r.price]
    assert rents, "expected at least one rental with a price"
    assert all(500 <= p <= 200_000 for p in rents)


# ---------- detail parsers ----------

def test_bap_detail_from_jsonld():
    html = read_fixture("bap_item.html")
    listing = get_scraper("bap").parse_detail("460211124", html)
    assert listing.title
    assert listing.price is not None
    assert listing.vertical == "bap"
    assert any("finncdn" in img for img in listing.images)
    assert "brand" in listing.attributes or "category" in listing.attributes


def test_homes_detail_pulls_asking_price():
    html = read_fixture("homes_ad.html")
    listing = get_scraper("homes").parse_detail("459322772", html)
    assert listing.price == 4_200_000
    assert listing.location and "Dælenenggata" in listing.location
    assert listing.attributes.get("property_type") == "Leilighet"
    assert listing.attributes.get("construction_year") == 1938
    assert listing.images


def test_lettings_detail_pulls_monthly_rent():
    html = read_fixture("lettings_ad.html")
    listing = get_scraper("lettings").parse_detail("448510748", html)
    assert listing.price == 23_000
    assert listing.location and "," in listing.location
    assert listing.images


def test_cars_detail_extracts_product_fields():
    html = read_fixture("mobility_item.html")
    listing = get_scraper("cars_used").parse_detail("460212366", html)
    assert listing.title
    assert listing.price is not None and listing.price > 10_000
    assert listing.attributes.get("brand") == "Tesla"
    assert all(isinstance(img, str) and img.startswith("http") for img in listing.images)


def test_jobs_detail_extracts_posting_fields():
    html = read_fixture("jobs_ad.html")
    listing = get_scraper("jobs").parse_detail("459777164", html)
    assert listing.title == "Dynamics 365 CRM-utvikler"
    assert listing.seller and listing.seller.get("name") == "Kreftforeningen"
    assert listing.location and "Oslo" in listing.location
    assert listing.attributes.get("deadline") == "2026-04-30"
    assert listing.published_at is not None


def test_jobs_detail_reads_dom_when_jsonld_is_gone():
    """August 2026: finn.no stopped shipping JobPosting on job ads.

    The fixture is the real page as served then — only BreadcrumbList is left,
    so everything asserted below comes from the DOM. Without this path every
    job listing came back with description=None while the text sat in the
    markup, and callers could not tell an empty ad from a failed read.
    """
    html = read_fixture("jobs_ad_no_jsonld.html")
    assert find_by_type(extract_jsonld(html), "JobPosting") is None

    listing = get_scraper("jobs").parse_detail("472381832", html)
    assert listing.description and len(listing.description) > 1000
    # Lists carry the requirements — they have to survive as markup.
    assert "<li" in listing.description
    assert listing.title == "KI - Utviklar"
    assert listing.seller and listing.seller.get("name") == "Nordea Liv"
    assert listing.location == "Bergen"
    assert listing.attributes.get("deadline") == "15.8.2026"


# ---------- jsonld helpers ----------

def test_jsonld_unwraps_wrapped_jobs_blocks():
    html = read_fixture("jobs_ad.html")
    blocks = extract_jsonld(html)
    assert find_by_type(blocks, "JobPosting") is not None
    assert find_by_type(blocks, "BreadcrumbList") is not None


def test_parse_price_nok_variants():
    assert parse_price_nok("4 200 000 kr") == 4_200_000
    assert parse_price_nok("kr 17 500") == 17_500
    assert parse_price_nok("Totalpris 4\xa0221\xa0894 kr") == 4_221_894
    assert parse_price_nok("400 000 |  | kr") == 400_000
    assert parse_price_nok("no price here") is None
    assert parse_price_nok(None) is None

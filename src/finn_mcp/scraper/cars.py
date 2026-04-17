from __future__ import annotations

import re
from typing import Any

from selectolax.parser import HTMLParser, Node

from ..models import Listing
from .base import VerticalScraper, _clean, now_utc, parse_price_nok
from .jsonld import extract_jsonld, find_by_type


_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_KM_RE = re.compile(r"(\d[\d\s]*)\s*km\b")


def _extract_images(value: Any) -> list[str]:
    """schema.org image fields may be a string, list, or list of ImageObject dicts."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        url = value.get("contentUrl") or value.get("url")
        return [str(url)] if url else []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            out.extend(_extract_images(item))
        return out
    return []


class _CarsBase(VerticalScraper):
    link_pattern = "/mobility/item/"
    finnkode_re = re.compile(r"/mobility/item/(\d+)")

    def detail_url(self, finnkode: str) -> str:
        return f"https://www.finn.no/mobility/item/{finnkode}"

    def _card_extras(self, article: Node, text: str) -> dict[str, Any]:
        extras: dict[str, Any] = {}
        t = text.replace("\xa0", " ")
        m = _YEAR_RE.search(t)
        if m:
            extras["year"] = int(m.group(0))
        m = _KM_RE.search(t)
        if m:
            extras["mileage_km"] = int(re.sub(r"\s+", "", m.group(1)))
        for fuel in ("El", "Bensin", "Diesel", "Hybrid"):
            if re.search(rf"\b{fuel}\b", t):
                extras["fuel"] = fuel
                break
        return extras

    def parse_detail(self, finnkode: str, html: str) -> Listing:
        blocks = extract_jsonld(html)
        product = find_by_type(blocks, "Product", "Car", "Vehicle")

        title: str | None = None
        description: str | None = None
        price: int | None = None
        currency = "NOK"
        images: list[str] = []
        attributes: dict[str, Any] = {}
        location: str | None = None

        if product:
            title = _clean(product.get("name"))
            description = _clean(product.get("description"))
            images = _extract_images(product.get("image"))
            brand = product.get("brand")
            if isinstance(brand, dict):
                attributes["brand"] = brand.get("name")
            elif isinstance(brand, str):
                attributes["brand"] = brand
            if product.get("model"):
                attributes["model"] = product["model"]
            offers = product.get("offers")
            if isinstance(offers, dict):
                try:
                    raw = offers.get("price")
                    price = int(float(raw)) if raw is not None else None
                except (TypeError, ValueError):
                    price = None
                currency = offers.get("priceCurrency") or currency

        # Supplement from DOM
        tree = HTMLParser(html)
        if title is None:
            h1 = tree.css_first("h1")
            if h1:
                title = _clean(h1.text(strip=True))

        # Pull any labelled attribute rows (year, mileage, fuel, transmission, etc.)
        for tid, key in (
            ("year", "year"),
            ("mileage", "mileage_km"),
            ("fuel", "fuel"),
            ("transmission", "transmission"),
            ("power", "power_hp"),
            ("color", "color"),
        ):
            node = tree.css_first(f'[data-testid="info-{tid}"]')
            if node is None:
                continue
            val = _clean(node.text(separator=" ", strip=True))
            if val:
                attributes.setdefault(key, val)

        if price is None:
            price = parse_price_nok(html)

        return Listing(
            finnkode=finnkode,
            vertical=self.vertical,
            url=self.detail_url(finnkode),
            title=title or f"Car listing {finnkode}",
            description=description,
            price=price,
            currency=currency,
            location=location,
            images=images,
            attributes=attributes,
            seller=None,
            published_at=None,
            fetched_at=now_utc(),
        )


class CarsUsedScraper(_CarsBase):
    vertical = "cars_used"

    def search_url(
        self, query: str, page: int, filters: dict[str, str] | None
    ) -> tuple[str, dict[str, str]]:
        params: dict[str, str] = {"q": query} if query else {}
        if page > 1:
            params["page"] = str(page)
        if filters:
            params.update(filters)
        return "https://www.finn.no/car/used/search.html", params


class CarsNewScraper(_CarsBase):
    vertical = "cars_new"

    def search_url(
        self, query: str, page: int, filters: dict[str, str] | None
    ) -> tuple[str, dict[str, str]]:
        # finn.no's /car/new/search.html is a JavaScript-rendered page and
        # does not expose listings in its initial HTML response. Scraping it
        # would require a real browser (Playwright) or the official API.
        raise NotImplementedError(
            "cars_new search is not supported by the scraper backend — "
            "the new-cars page is rendered client-side. Use cars_used or "
            "the official API backend once credentials are in place."
        )

    async def search(self, query, page=1, filters=None):  # type: ignore[override]
        raise NotImplementedError(
            "cars_new search is not supported by the scraper backend."
        )

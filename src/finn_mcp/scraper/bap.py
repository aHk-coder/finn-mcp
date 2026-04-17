from __future__ import annotations

import re
from typing import Any

from selectolax.parser import HTMLParser, Node

from ..models import Listing
from .base import VerticalScraper, _clean, now_utc, parse_price_nok
from .jsonld import extract_jsonld, find_by_type


class BapScraper(VerticalScraper):
    vertical = "bap"
    link_pattern = "/recommerce/forsale/item/"
    finnkode_re = re.compile(r"/recommerce/forsale/item/(\d+)")

    def search_url(
        self, query: str, page: int, filters: dict[str, str] | None
    ) -> tuple[str, dict[str, str]]:
        params: dict[str, str] = {"q": query}
        if page > 1:
            params["page"] = str(page)
        if filters:
            params.update(filters)
        return "https://www.finn.no/recommerce/forsale/search", params

    def detail_url(self, finnkode: str) -> str:
        return f"https://www.finn.no/recommerce/forsale/item/{finnkode}"

    def _guess_location(self, article: Node, text: str) -> str | None:
        # BAP cards typically include a location token between pipes; no stable DOM hook.
        # Best-effort: return None; JSON-LD on detail pages has better location info.
        return None

    def _card_extras(self, article: Node, text: str) -> dict[str, Any]:
        extras: dict[str, Any] = {}
        if "Fri frakt" in text:
            extras["free_shipping"] = True
        m = re.search(r"(\d+)\s*GB\b", text)
        if m:
            extras["storage_gb"] = int(m.group(1))
        return extras

    def parse_detail(self, finnkode: str, html: str) -> Listing:
        blocks = extract_jsonld(html)
        product = find_by_type(blocks, "Product")

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
            from .cars import _extract_images as _extract_images_helper
            images = _extract_images_helper(product.get("image"))
            brand = product.get("brand")
            if isinstance(brand, dict):
                attributes["brand"] = brand.get("name")
            elif isinstance(brand, str):
                attributes["brand"] = brand
            condition = product.get("itemCondition")
            if condition:
                attributes["condition"] = str(condition).rsplit("/", 1)[-1]
            offers = product.get("offers")
            if isinstance(offers, dict):
                price_raw = offers.get("price")
                try:
                    price = int(float(price_raw)) if price_raw is not None else None
                except (TypeError, ValueError):
                    price = None
                currency = offers.get("priceCurrency") or currency
                area = offers.get("areaServed")
                if isinstance(area, dict):
                    location = _clean(area.get("name"))
                elif isinstance(area, str):
                    location = _clean(area)
            for prop in product.get("additionalProperty") or []:
                if not isinstance(prop, dict):
                    continue
                name = prop.get("name")
                value = prop.get("value")
                if name:
                    attributes[str(name).lower()] = value

        if title is None:
            tree = HTMLParser(html)
            h1 = tree.css_first("h1")
            if h1:
                title = _clean(h1.text(strip=True))
        if price is None:
            price = parse_price_nok(html)

        return Listing(
            finnkode=finnkode,
            vertical=self.vertical,
            url=self.detail_url(finnkode),
            title=title or f"BAP listing {finnkode}",
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

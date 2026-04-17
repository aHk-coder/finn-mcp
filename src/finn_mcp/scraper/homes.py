from __future__ import annotations

import re
from typing import Any

from selectolax.parser import HTMLParser, Node

from ..models import Listing, Vertical
from .base import VerticalScraper, _clean, now_utc, parse_price_nok


# Map Norwegian attribute labels seen on real-estate detail pages to stable keys.
# Matched as the leading word(s) of the data-testid container text.
_HOMES_LABELS = {
    "Boligtype": "property_type",
    "Eieform": "ownership_type",
    "Soverom": "bedrooms",
    "Internt bruksareal": "internal_bra_m2",
    "Bruksareal": "usable_area_m2",
    "Eksternt bruksareal": "external_bra_m2",
    "Primærrom": "primary_room_m2",
    "Etasje": "floor",
    "Byggeår": "construction_year",
    "Energimerking": "energy_label",
    "Tomteareal": "plot_area",
    "Felleskost/mnd.": "common_cost_monthly_nok",
    "Totalpris": "total_price_nok",
    "Fellesgjeld": "shared_debt_nok",
    "Kommunale avg.": "municipal_fees_nok",
    "Formuesverdi": "asset_value_nok",
    "Tilbudsfrist": "offer_deadline",
    "Visning": "viewing",
}


_NUM_RE = re.compile(r"(\d[\d\s]*)")


def _strip_label(value: str, label: str) -> str:
    stripped = value
    if stripped.startswith(label):
        stripped = stripped[len(label):]
    return stripped.strip(" :\xa0")


def _extract_num(text: str) -> int | None:
    m = _NUM_RE.search(text)
    if not m:
        return None
    try:
        return int(re.sub(r"\s+", "", m.group(1)))
    except ValueError:
        return None


class _RealEstateBase(VerticalScraper):
    vertical: Vertical  # set by subclass

    finnkode_re = re.compile(r"finnkode=(\d+)")
    link_pattern = "finnkode="

    def _guess_location(self, article: Node, text: str) -> str | None:
        # Real-estate cards usually include the street address, often like
        # "Dælenenggata 14A, Oslo". The address is visible in the card text
        # but there is no stable data-testid on the result card. Pick a
        # segment that looks like "... , <word>" with no "kr" in it.
        for part in text.split(" | "):
            cleaned = _clean(part)
            if not cleaned or "kr" in cleaned.lower() or "m²" in cleaned:
                continue
            if "," in cleaned and any(ch.isdigit() for ch in cleaned):
                return cleaned
        return None

    def _card_extras(self, article: Node, text: str) -> dict[str, Any]:
        extras: dict[str, Any] = {}
        m = re.search(r"(\d[\d\s]*)\s*m²", text)
        if m:
            extras["area_m2"] = int(re.sub(r"\s+", "", m.group(1)))
        m = re.search(r"(\d+)\s*soverom", text)
        if m:
            extras["bedrooms"] = int(m.group(1))
        m = re.search(
            r"(Leilighet|Enebolig|Rekkehus|Tomannsbolig|Hytte|Gårdsbruk|Annet)",
            text,
        )
        if m:
            extras["property_type"] = m.group(1)
        return extras

    def parse_detail(self, finnkode: str, html: str) -> Listing:
        tree = HTMLParser(html)

        # Title: the <h1> is the clean listing title.
        title: str | None = None
        h1 = tree.css_first("h1")
        if h1:
            title = _clean(h1.text(separator=" ", strip=True))

        # Address
        location: str | None = None
        addr_node = tree.css_first('[data-testid="object-address"]')
        if addr_node:
            location = _clean(addr_node.text(separator=" ", strip=True))

        # Attributes via data-testid buckets
        attributes: dict[str, Any] = {}
        for data_testid_prefix in (
            "info-",
            "pricing-",
            "common-",
            "energy-",
        ):
            for node in tree.css(f'[data-testid^="{data_testid_prefix}"]'):
                value = _clean(node.text(separator=" ", strip=True))
                if not value:
                    continue
                for label, key in _HOMES_LABELS.items():
                    if value.startswith(label):
                        raw = _strip_label(value, label)
                        if key.endswith("_nok") or key.endswith("_m2") or key in {
                            "bedrooms",
                            "construction_year",
                            "floor",
                        }:
                            n = _extract_num(raw)
                            if n is not None:
                                attributes.setdefault(key, n)
                            else:
                                attributes.setdefault(key, raw)
                        else:
                            attributes.setdefault(key, raw)
                        break

        # Price: prefer the asking price ("Prisantydning"). Note: finn.no
        # spells the testid "pricing-incicative-price" (sic, typo upstream).
        # For lettings, "Månedsleie" lives under pricing-common-monthly-cost.
        price: int | None = None
        for tid in (
            "pricing-incicative-price",
            "pricing-indicative-price",
            "pricing-common-monthly-cost",
            "pricing-details",
            "pricing-total-price",
        ):
            node = tree.css_first(f'[data-testid="{tid}"]')
            if node:
                price = parse_price_nok(node.text(separator=" ", strip=True))
                if price:
                    break

        # Description
        description: str | None = None
        desc_node = tree.css_first('[data-testid="about-property"]') or tree.css_first(
            '[data-testid="beskrivelse"]'
        )
        if desc_node:
            description = _clean(desc_node.text(separator=" ", strip=True))

        # Images: og:image + finncdn urls in HTML.
        images: list[str] = []
        og = tree.css_first('meta[property="og:image"]')
        if og:
            src = og.attributes.get("content")
            if src:
                images.append(src)
        for m in re.finditer(
            r'https://images\.finncdn\.no/dynamic/\d+w/[^"\'<> )]+',
            html,
        ):
            img = m.group(0)
            if img not in images:
                images.append(img)
            if len(images) >= 20:
                break

        # Broker / seller
        seller: dict[str, Any] | None = None
        broker_name = None
        broker_node = tree.css_first('[data-testid="broker-name"]')
        if broker_node:
            broker_name = _clean(broker_node.text(strip=True))
        if broker_name:
            seller = {"name": broker_name}

        return Listing(
            finnkode=finnkode,
            vertical=self.vertical,
            url=self.detail_url(finnkode),
            title=title or f"Real-estate listing {finnkode}",
            description=description,
            price=price,
            currency="NOK",
            location=location,
            images=images,
            attributes=attributes,
            seller=seller,
            published_at=None,
            fetched_at=now_utc(),
        )


class HomesScraper(_RealEstateBase):
    vertical = "homes"

    def search_url(
        self, query: str, page: int, filters: dict[str, str] | None
    ) -> tuple[str, dict[str, str]]:
        params: dict[str, str] = {}
        if query:
            params["q"] = query
        if page > 1:
            params["page"] = str(page)
        if filters:
            params.update(filters)
        return "https://www.finn.no/realestate/homes/search.html", params

    def detail_url(self, finnkode: str) -> str:
        return f"https://www.finn.no/realestate/homes/ad.html?finnkode={finnkode}"


class LettingsScraper(_RealEstateBase):
    vertical = "lettings"

    def search_url(
        self, query: str, page: int, filters: dict[str, str] | None
    ) -> tuple[str, dict[str, str]]:
        params: dict[str, str] = {}
        if query:
            params["q"] = query
        if page > 1:
            params["page"] = str(page)
        if filters:
            params.update(filters)
        return "https://www.finn.no/realestate/lettings/search.html", params

    def detail_url(self, finnkode: str) -> str:
        return f"https://www.finn.no/realestate/lettings/ad.html?finnkode={finnkode}"

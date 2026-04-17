from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from selectolax.parser import HTMLParser, Node

from .. import http_client
from ..models import Listing, SearchResult, Vertical

_WHITESPACE_RE = re.compile(r"\s+")


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text or None


def parse_price_nok(text: str | None) -> int | None:
    """Extract an NOK price from text like '4 200 000 kr' or 'kr 17 500'.

    Tolerates pipes/other separators between the amount and the 'kr' token —
    search-result cards sometimes render them as ``'400 000 |  | kr'``.
    Returns int number of NOK, or None if no price found.
    """
    if not text:
        return None
    compact = text.replace("\xa0", " ").replace(",", "")
    # Allow arbitrary non-digit junk (including pipes) between amount and "kr".
    m = re.search(r"(\d[\d\s]{2,})\s*[^\d]{0,6}\s*(?:kr|NOK)\b", compact, flags=re.IGNORECASE)
    if not m:
        m = re.search(r"(?:kr|NOK)\b\s*[^\d]{0,6}(\d[\d\s]{2,})", compact, flags=re.IGNORECASE)
    if not m:
        return None
    digits = re.sub(r"\s+", "", m.group(1))
    try:
        return int(digits)
    except ValueError:
        return None


def walk_to_article(node: Node, max_steps: int = 12) -> Node | None:
    cur = node
    for _ in range(max_steps):
        if cur is None:
            return None
        if cur.tag == "article":
            return cur
        cur = cur.parent
    return None


def first_image_src(article: Node) -> str | None:
    img = article.css_first("img")
    if not img:
        return None
    attrs = img.attributes
    src = attrs.get("src") or ""
    if src and not src.startswith("data:"):
        return src
    srcset = attrs.get("srcset") or ""
    if srcset:
        first = srcset.split(",")[0].strip().split(" ")[0]
        if first:
            return first
    return None


class VerticalScraper(ABC):
    vertical: Vertical
    link_pattern: str  # substring that distinguishes this vertical's detail links
    finnkode_re: re.Pattern[str]

    @abstractmethod
    def search_url(self, query: str, page: int, filters: dict[str, str] | None) -> tuple[str, dict[str, str]]:
        """Return (base_url, query_params) for a search request."""

    @abstractmethod
    def detail_url(self, finnkode: str) -> str:
        ...

    @abstractmethod
    def parse_detail(self, finnkode: str, html: str) -> Listing:
        ...

    async def search(
        self, query: str, page: int = 1, filters: dict[str, str] | None = None
    ) -> list[SearchResult]:
        url, params = self.search_url(query, page, filters)
        html = await http_client.fetch(url, params=params)
        return self.parse_search_cards(html)

    async def fetch_detail(self, finnkode: str) -> tuple[str, Listing]:
        url = self.detail_url(finnkode)
        html = await http_client.fetch(url)
        listing = self.parse_detail(finnkode, html)
        return html, listing

    def parse_search_cards(self, html: str) -> list[SearchResult]:
        tree = HTMLParser(html)
        seen_finnkodes: set[str] = set()
        seen_articles: set[int] = set()
        results: list[SearchResult] = []
        for a in tree.css(f'a[href*="{self.link_pattern}"]'):
            href = a.attributes.get("href") or ""
            m = self.finnkode_re.search(href)
            if not m:
                continue
            finnkode = m.group(1)
            if finnkode in seen_finnkodes:
                continue
            article = walk_to_article(a)
            if article is None or id(article) in seen_articles:
                continue
            seen_finnkodes.add(finnkode)
            seen_articles.add(id(article))
            result = self._parse_card(finnkode, href, article)
            if result is not None:
                results.append(result)
        return results

    def _parse_card(self, finnkode: str, href: str, article: Node) -> SearchResult | None:
        text = article.text(separator=" | ", strip=True)
        text = text.replace("\xa0", " ") if text else ""
        title = self._guess_title(article, text)
        if not title:
            return None
        price = parse_price_nok(text)
        location = self._guess_location(article, text)
        thumbnail = first_image_src(article)
        url = href if href.startswith("http") else f"https://www.finn.no{href}"
        extra = self._card_extras(article, text)
        return SearchResult(
            finnkode=finnkode,
            vertical=self.vertical,
            title=title,
            price=price,
            location=location,
            thumbnail_url=thumbnail,
            url=url,
            extra=extra,
        )

    # ----- hooks subclasses can override for card quirks -----

    def _guess_title(self, article: Node, text: str) -> str | None:
        h = article.css_first("h2") or article.css_first("h3")
        if h:
            t = _clean(h.text(separator=" ", strip=True))
            if t:
                return t
        # Fallback: first non-trivial text segment
        for part in text.split(" | "):
            cleaned = _clean(part)
            if cleaned and len(cleaned) > 5 and "kr" not in cleaned.lower():
                return cleaned
        return None

    def _guess_location(self, article: Node, text: str) -> str | None:
        return None

    def _card_extras(self, article: Node, text: str) -> dict[str, Any]:
        return {}


def now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)

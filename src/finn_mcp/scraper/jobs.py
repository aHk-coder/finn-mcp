from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from selectolax.parser import HTMLParser

from ..models import Listing
from .base import VerticalScraper, _clean, now_utc
from .jsonld import extract_jsonld, find_by_type


class JobsScraper(VerticalScraper):
    vertical = "jobs"
    link_pattern = "/job/ad/"
    finnkode_re = re.compile(r"/job/ad/(\d+)")

    def search_url(
        self, query: str, page: int, filters: dict[str, str] | None
    ) -> tuple[str, dict[str, str]]:
        params: dict[str, str] = {"q": query} if query else {}
        if page > 1:
            params["page"] = str(page)
        if filters:
            params.update(filters)
        return "https://www.finn.no/job/search", params

    def detail_url(self, finnkode: str) -> str:
        return f"https://www.finn.no/job/ad/{finnkode}"

    def _guess_title(self, article, text):  # type: ignore[override]
        # Jobs cards put the job title in the <a> anchor text (not h2/h3).
        # h3 in the card is the "hook" sub-line; avoid picking it.
        a = article.css_first(f'a[href*="{self.link_pattern}"]')
        if a:
            title = _clean(a.text(separator=" ", strip=True))
            if title and len(title) > 2:
                return title
        return super()._guess_title(article, text)

    def parse_detail(self, finnkode: str, html: str) -> Listing:
        blocks = extract_jsonld(html)
        posting = find_by_type(blocks, "JobPosting")

        title: str | None = None
        description: str | None = None
        location: str | None = None
        attributes: dict[str, Any] = {}
        seller: dict[str, Any] | None = None
        published_at: datetime | None = None

        if posting:
            title = _clean(posting.get("title"))
            description = _clean(posting.get("description"))
            emp_type = posting.get("employmentType")
            if emp_type:
                attributes["employment_type"] = emp_type
            valid_through = posting.get("validThrough")
            if valid_through:
                attributes["deadline"] = valid_through
            date_posted = posting.get("datePosted")
            if date_posted:
                try:
                    published_at = datetime.fromisoformat(str(date_posted))
                except ValueError:
                    attributes["date_posted"] = date_posted
            hiring = posting.get("hiringOrganization")
            if isinstance(hiring, dict):
                seller = {
                    "name": hiring.get("name"),
                    "url": hiring.get("sameAs") or hiring.get("url"),
                }
            elif isinstance(hiring, str):
                seller = {"name": hiring}
            job_loc = posting.get("jobLocation")
            if isinstance(job_loc, list) and job_loc:
                job_loc = job_loc[0]
            if isinstance(job_loc, dict):
                addr = job_loc.get("address")
                if isinstance(addr, dict):
                    parts = [
                        addr.get("addressLocality"),
                        addr.get("addressRegion"),
                        addr.get("addressCountry"),
                    ]
                    location = _clean(
                        ", ".join(str(p) for p in parts if p)
                    )

        if title is None:
            tree = HTMLParser(html)
            h1 = tree.css_first("h1")
            if h1:
                title = _clean(h1.text(strip=True))

        return Listing(
            finnkode=finnkode,
            vertical=self.vertical,
            url=self.detail_url(finnkode),
            title=title or f"Job listing {finnkode}",
            description=description,
            price=None,
            currency="NOK",
            location=location,
            images=[],
            attributes=attributes,
            seller=seller,
            published_at=published_at,
            fetched_at=now_utc(),
        )

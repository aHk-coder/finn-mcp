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

    # finn wraps an imported ad body in .import-decoration; the data-testid is
    # kept as a second guess because it survived earlier redesigns.
    _DESCRIPTION_SELECTORS = (
        "div.import-decoration",
        "[data-testid='job-description']",
    )
    _DEADLINE_LABELS = ("Søknadsfrist", "Soknadsfrist", "Application deadline")

    @staticmethod
    def _description_from_dom(tree: HTMLParser) -> str | None:
        """Read the ad body from the page itself.

        The wrapper's inner HTML is returned rather than its text: in job ads
        the <li> lists carry the requirements, and flattening them to a single
        paragraph loses the part a reader needs most.

        Last resort is every sufficiently long <p> on the page. Navigation and
        chrome rarely produce 80-character paragraphs, so the noise stays out
        without depending on a single class name that finn can rename.
        """
        for selector in JobsScraper._DESCRIPTION_SELECTORS:
            node = tree.css_first(selector)
            if node and len(node.text(strip=True)) > 200:
                return _clean(node.html)

        paragraphs = [
            _clean(p.text(separator=" ", strip=True))
            for p in tree.css("p")
            if len(p.text(strip=True)) >= 80
        ]
        text = "\n\n".join(p for p in paragraphs if p)
        return text if len(text) > 200 else None

    @staticmethod
    def _parts_from_og_title(
        tree: HTMLParser,
    ) -> tuple[str | None, str | None, str | None]:
        """Split og:title, which reads 'Title · Location · Employer | FINN Jobb'.

        Employer and location also vanished with the JSON-LD block. This meta
        tag is written for link previews, so it is the last thing finn breaks.
        """
        meta = tree.css_first('meta[property="og:title"]')
        content = _clean(meta.attributes.get("content")) if meta else None
        if not content:
            return None, None, None

        content = content.split(" | ")[0]
        parts = [p.strip() for p in content.split("·") if p.strip()]
        if len(parts) >= 3:
            return parts[0], parts[1], parts[-1]
        if len(parts) == 2:
            return parts[0], None, parts[1]
        return (parts[0] if parts else None), None, None

    @staticmethod
    def _deadline_from_dom(tree: HTMLParser) -> str | None:
        """Deadline sits in a label/value pair, keyed by the label's own text.

        Matching on the visible label rather than on a utility class survives
        the styling churn that broke everything else here.
        """
        for item in tree.css("li"):
            text = item.text(separator=" ", strip=True)
            if not text:
                continue
            if any(text.startswith(label) for label in JobsScraper._DEADLINE_LABELS):
                value = item.css_first("span")
                if value:
                    return _clean(value.text(strip=True))
        return None

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

        tree = HTMLParser(html)

        # In August 2026 finn.no stopped shipping the JobPosting JSON-LD block
        # on job ads — only BreadcrumbList is left. Reading the description
        # solely from JSON-LD meant every job listing came back with
        # description=None while the text sat right there in the markup, and
        # callers could not tell "this ad has no body" from "we failed to read
        # it". The DOM is the fallback, not the primary source: JSON-LD stays
        # first because it is structured and unambiguous when finn ships it.
        if description is None:
            description = self._description_from_dom(tree)

        og_title, og_location, og_employer = self._parts_from_og_title(tree)

        if title is None:
            h1 = tree.css_first("h1")
            if h1:
                title = _clean(h1.text(strip=True))
            if title is None:
                title = og_title

        if location is None:
            location = og_location

        if seller is None and og_employer:
            seller = {"name": og_employer}

        if "deadline" not in attributes:
            deadline = self._deadline_from_dom(tree)
            if deadline:
                attributes["deadline"] = deadline

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

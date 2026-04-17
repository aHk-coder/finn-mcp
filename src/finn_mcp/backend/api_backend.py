from __future__ import annotations

from ..models import Listing, SearchResult, Vertical
from .base import FinnBackend


class OfficialApiBackend(FinnBackend):
    """Stub for the official FINN partner API at ``cache.api.finn.no/iad/``.

    Not yet implemented. When partner credentials are in place, this backend
    will translate ``search`` / ``get_listing`` calls into calls to:

    - Service document  (https://cache.api.finn.no/iad/)
    - Search            (https://cache.api.finn.no/iad/search/<vertical>)
    - Ad                (https://cache.api.finn.no/iad/ad/<finnkode>)
    - Image sizes       (https://cache.api.finn.no/iad/image/sizes)

    Responses are a mix of Atom Syndication XML and JSON; the backend maps
    them into ``SearchResult`` / ``Listing`` so the MCP tool surface does
    not change.
    """

    name = "official"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    async def search(
        self,
        vertical: Vertical,
        query: str,
        page: int = 1,
        filters: dict[str, str] | None = None,
    ) -> list[SearchResult]:
        raise NotImplementedError(
            "OfficialApiBackend is a stub — partner credentials and endpoint "
            "wiring are required. Set FINN_BACKEND=scraper to use the scraper."
        )

    async def get_listing(
        self,
        finnkode: str,
        vertical: Vertical | None = None,
    ) -> Listing:
        raise NotImplementedError(
            "OfficialApiBackend is a stub — partner credentials and endpoint "
            "wiring are required. Set FINN_BACKEND=scraper to use the scraper."
        )

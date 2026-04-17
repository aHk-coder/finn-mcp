from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Listing, SearchResult, Vertical


class ListingNotFound(Exception):
    def __init__(self, finnkode: str):
        super().__init__(f"listing not found: {finnkode}")
        self.finnkode = finnkode


class FinnBackend(ABC):
    """Stable interface between MCP tools and the underlying finn.no data source.

    v1 ships with ``ScraperBackend``. An ``OfficialApiBackend`` will implement
    this same interface once partner credentials are in place.
    """

    name: str

    @abstractmethod
    async def search(
        self,
        vertical: Vertical,
        query: str,
        page: int = 1,
        filters: dict[str, str] | None = None,
    ) -> list[SearchResult]:
        ...

    @abstractmethod
    async def get_listing(
        self,
        finnkode: str,
        vertical: Vertical | None = None,
    ) -> Listing:
        ...

    async def aclose(self) -> None:
        """Release any resources held by the backend."""
        return None

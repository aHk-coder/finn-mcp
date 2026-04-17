from __future__ import annotations

import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import config, http_client
from .backend.base import ListingNotFound
from .cache import Cache
from .models import Listing, SavedSearch, SearchResult, Vertical
from .scraper.base import now_utc

log = logging.getLogger("finn_mcp")

mcp = FastMCP("finn-mcp")


def _backend():
    return config.get_backend()


_cache = Cache()


@mcp.tool()
async def search_finn(
    vertical: Vertical,
    query: str,
    page: int = 1,
    filters: dict[str, str] | None = None,
) -> list[SearchResult] | dict[str, Any]:
    """Search finn.no within a vertical.

    ``vertical`` is one of: ``bap`` (Torget / used goods), ``homes`` (real
    estate for sale), ``lettings`` (real estate for rent), ``cars_used``,
    ``cars_new`` (not yet supported by the scraper backend), ``jobs``.

    ``query`` is a free-text keyword. ``filters`` is a dict of extra
    URL-query parameters understood by finn.no (e.g. ``{"price_to":"300000"}``
    for cars, ``{"location":"1.20001.20061"}`` for Oslo).

    Returns up to ~50 ``SearchResult`` entries. Fewer if finn.no returned
    fewer matches; an empty list is a valid result.
    """
    try:
        return await _backend().search(vertical, query, page=page, filters=filters)
    except NotImplementedError as exc:
        return {"error": "not_supported", "message": str(exc)}
    except http_client.RateLimitedError as exc:
        return {"error": "rate_limited", "retry_after": exc.retry_after}
    except Exception as exc:
        log.exception("search_finn failed")
        return {"error": "parse_failed", "message": str(exc)}


@mcp.tool()
async def get_listing(
    finnkode: str,
    vertical: Vertical | None = None,
) -> Listing | dict[str, Any]:
    """Fetch a full listing by its ``finnkode``.

    If ``vertical`` is omitted the server tries a cache hint first, then
    probes each vertical until one returns a valid page. Results are cached
    for 24 hours in a local SQLite database.
    """
    try:
        return await _backend().get_listing(finnkode, vertical=vertical)
    except http_client.NotFoundError:
        return {"error": "not_found", "finnkode": finnkode}
    except ListingNotFound:
        return {"error": "not_found", "finnkode": finnkode}
    except http_client.RateLimitedError as exc:
        return {"error": "rate_limited", "retry_after": exc.retry_after}
    except NotImplementedError as exc:
        return {"error": "not_supported", "message": str(exc)}
    except Exception as exc:
        log.exception("get_listing failed for %s", finnkode)
        return {
            "error": "parse_failed",
            "finnkode": finnkode,
            "vertical": vertical,
            "message": str(exc),
        }


@mcp.tool()
async def save_search(
    name: str,
    vertical: Vertical,
    query: str,
    filters: dict[str, str] | None = None,
) -> SavedSearch:
    """Persist a named search for repeated monitoring via ``check_saved_search``."""
    saved = SavedSearch(
        name=name,
        vertical=vertical,
        query=query,
        filters=filters or {},
        last_checked_at=None,
        last_finnkodes=[],
    )
    await _cache.save_search(saved)
    return saved


@mcp.tool()
async def list_saved_searches() -> list[SavedSearch]:
    """Return every saved search in the local store, ordered by name."""
    return await _cache.list_searches()


@mcp.tool()
async def delete_saved_search(name: str) -> bool:
    """Delete a saved search by name. Returns True if it existed."""
    return await _cache.delete_search(name)


@mcp.tool()
async def check_saved_search(name: str) -> list[SearchResult] | dict[str, Any]:
    """Run a saved search, return only listings that are new since the last check.

    Updates the saved search's ``last_checked_at`` and ``last_finnkodes``.
    On the first call all current results are "new".
    """
    saved = await _cache.get_search(name)
    if saved is None:
        return {"error": "not_found", "name": name}

    try:
        results = await _backend().search(
            saved.vertical, saved.query, page=1, filters=saved.filters
        )
    except NotImplementedError as exc:
        return {"error": "not_supported", "message": str(exc)}
    except http_client.RateLimitedError as exc:
        return {"error": "rate_limited", "retry_after": exc.retry_after}
    except Exception as exc:
        log.exception("check_saved_search failed for %s", name)
        return {"error": "parse_failed", "message": str(exc)}

    previous = set(saved.last_finnkodes)
    new = [r for r in results if r.finnkode not in previous]
    union = sorted({r.finnkode for r in results} | previous)
    await _cache.update_search_state(name, now_utc(), union)
    return new


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()

from __future__ import annotations

import os
from pathlib import Path

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
)

LISTING_TTL_SECONDS = 24 * 60 * 60

REQUEST_DELAY_MIN = 0.3
REQUEST_DELAY_MAX = 1.2

HTTP_TIMEOUT_SECONDS = 15.0


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    path = Path(base) / "finn-mcp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_db_path() -> Path:
    override = os.environ.get("FINN_CACHE_DB")
    if override:
        return Path(override)
    return data_dir() / "cache.sqlite"


def backend_name() -> str:
    return os.environ.get("FINN_BACKEND", "scraper").strip().lower()


def get_backend():
    """Return a fresh FinnBackend instance selected by the FINN_BACKEND env var.

    Deferred import so the scraper dependencies aren't loaded when the
    official backend is active (and vice-versa).
    """
    name = backend_name()
    if name == "scraper":
        from .backend.scraper_backend import ScraperBackend

        return ScraperBackend()
    if name == "official":
        from .backend.api_backend import OfficialApiBackend

        return OfficialApiBackend(api_key=os.environ.get("FINN_API_KEY"))
    raise ValueError(
        f"unknown FINN_BACKEND={name!r}; expected 'scraper' or 'official'"
    )

from .base import VerticalScraper
from .bap import BapScraper
from .cars import CarsNewScraper, CarsUsedScraper
from .homes import HomesScraper, LettingsScraper
from .jobs import JobsScraper
from ..models import Vertical

SCRAPERS: dict[Vertical, VerticalScraper] = {
    "bap": BapScraper(),
    "homes": HomesScraper(),
    "lettings": LettingsScraper(),
    "cars_used": CarsUsedScraper(),
    "cars_new": CarsNewScraper(),
    "jobs": JobsScraper(),
}


def get_scraper(vertical: Vertical) -> VerticalScraper:
    try:
        return SCRAPERS[vertical]
    except KeyError as e:
        raise ValueError(f"unknown vertical: {vertical}") from e


__all__ = ["SCRAPERS", "VerticalScraper", "get_scraper"]

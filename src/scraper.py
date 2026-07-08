"""
Hot Wheels wiki scraper.

Scrapes the Hot Wheels Fandom Wiki for yearly car lists.
Handles Cloudflare protection via cloudscraper.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import cloudscraper
from bs4 import BeautifulSoup, Tag

from .models import HotWheelsCar, ScrapeResult

logger = logging.getLogger(__name__)

# Hot Wheels started in 1968
FIRST_YEAR = 1968

# Base URL for yearly lists
WIKI_BASE = "https://hotwheels.fandom.com/wiki/List_of_{year}_Hot_Wheels"

# User-Agent to mimic a real browser
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def create_scraper() -> cloudscraper.CloudScraper:
    """Create a cloudscraper session that bypasses Cloudflare."""
    scraper = cloudscraper.create_scraper(
        browser={
            "browser": "chrome",
            "platform": "windows",
            "mobile": False,
        },
        interpreter="js2py",  # lightweight JS interpreter for Cloudflare challenges
    )
    scraper.headers.update({"User-Agent": USER_AGENT})
    return scraper


def fetch_page(scraper: cloudscraper.CloudScraper, url: str) -> Optional[str]:
    """Fetch a wiki page, returning HTML content or None on failure."""
    try:
        resp = scraper.get(url, timeout=30)
        if resp.status_code == 200:
            return resp.text
        elif resp.status_code == 404:
            logger.warning(f"Page not found: {url}")
            return None
        else:
            logger.warning(f"HTTP {resp.status_code} for {url}")
            return None
    except Exception as e:
        logger.error(f"Error fetching {url}: {e}")
        return None


def parse_car_table(
    html: str, year: int
) -> list[HotWheelsCar]:
    """
    Parse a wikitable from a yearly Hot Wheels list page.

    Returns a list of HotWheelsCar objects found in the table(s).
    """
    soup = BeautifulSoup(html, "html.parser")
    cars: list[HotWheelsCar] = []

    # Find all wikitable elements
    tables = soup.find_all("table", class_="wikitable")

    if not tables:
        logger.warning(f"No wikitable found for year {year}")
        return cars

    for table_idx, table in enumerate(tables):
        rows = table.find_all("tr")

        # Skip header row(s) - look for <th> elements
        data_rows = []
        for row in rows:
            cells = row.find_all(["td", "th"])
            if cells and all(cell.name == "td" for cell in cells):
                data_rows.append(row)

        if not data_rows:
            # Try harder: maybe the first row is data despite having <th>
            continue

        for row in data_rows:
            cells = row.find_all("td")
            if not cells:
                continue

            # Determine cell structure
            # Typical layout: Toy# | Col | Model Name | Series | Series# | Photo
            car = HotWheelsCar(year=year)

            # Try to extract from known column patterns
            parsed = _parse_cells(cells, year, table_idx)
            if parsed:
                car.toy_num = parsed.get("toy_num")
                car.model_name = parsed.get("model_name", "")
                car.series = parsed.get("series")
                car.series_num = parsed.get("series_num")
                car.col_num = parsed.get("col_num")
                car.image_url = parsed.get("image_url")

            # Also try extracting image from the row
            if not car.image_url:
                car.image_url = _extract_image_url(row)

            car.clean()

            if car.is_valid:
                car.raw_data = {
                    "table_idx": table_idx,
                    "raw_cells": [str(cell.get_text(strip=True)) for cell in cells],
                }
                cars.append(car)

    return cars


def _parse_cells(
    cells: list[Tag], year: int, table_idx: int
) -> Optional[dict]:
    """
    Extract car data from table cells based on column count and patterns.
    Different years have slightly different table layouts.
    """
    num_cells = len(cells)
    result: dict = {}

    # Extract text from each cell
    texts = []
    for cell in cells:
        text = cell.get_text(separator=" ", strip=True)
        texts.append(text)

    if num_cells >= 6:
        # Standard layout: Toy# | Col# | Model | Series | Series# | Image
        result["toy_num"] = texts[0]
        result["col_num"] = texts[1]
        result["model_name"] = texts[2]
        result["series"] = texts[3]
        result["series_num"] = texts[4]
    elif num_cells == 5:
        # Layout without column number
        result["toy_num"] = texts[0]
        result["model_name"] = texts[1]
        result["series"] = texts[2]
        result["series_num"] = texts[3]
    elif num_cells == 4:
        # Compact layout: Toy# | Model | Series | Photo
        result["toy_num"] = texts[0]
        result["model_name"] = texts[1]
        result["series"] = texts[2]
    elif num_cells == 3:
        # Minimal layout: Toy# | Model | Series
        result["toy_num"] = texts[0]
        result["model_name"] = texts[1]
        result["series"] = texts[2]
    else:
        # Unknown layout - try to at least get something
        if num_cells >= 2:
            result["toy_num"] = texts[0]
            result["model_name"] = texts[1]
        elif num_cells == 1:
            result["model_name"] = texts[0]

    return result


def _extract_image_url(row: Tag) -> Optional[str]:
    """Extract image URL from a table row."""
    # Look for <a> tag with class "image" containing an <img>
    img_link = row.find("a", class_="image")
    if img_link and img_link.get("href"):
        href = img_link["href"]
        if isinstance(href, str) and href.startswith("http"):
            return href

    # Fallback: look for any image in the row
    img = row.find("img")
    if img:
        # Try srcset first (higher resolution)
        srcset = img.get("srcset")
        if srcset:
            # srcset format: "url width, url width, ..."
            first_url = srcset.split(",")[0].strip().split(" ")[0]
            if first_url.startswith("http"):
                return first_url
        # Fall back to src
        src = img.get("src")
        if src and isinstance(src, str) and src.startswith("http"):
            return src

    return None


def get_available_years() -> list[int]:
    """Return the list of years to scrape (1968 to current year)."""
    import datetime
    current_year = datetime.date.today().year
    return list(range(FIRST_YEAR, current_year + 1))


def scrape_years(
    years: list[int],
    scraper: Optional[cloudscraper.CloudScraper] = None,
    delay: float = 1.0,
) -> ScrapeResult:
    """
    Scrape multiple years from the Hot Wheels wiki.

    Args:
        years: List of years to scrape.
        scraper: Optional cloudscraper instance (creates one if not provided).
        delay: Delay in seconds between requests to be polite.

    Returns:
        ScrapeResult with all collected cars.
    """
    if scraper is None:
        scraper = create_scraper()

    result = ScrapeResult()
    all_cars: list[HotWheelsCar] = []

    for year in years:
        url = WIKI_BASE.format(year=year)
        logger.info(f"Scraping {year}...")

        html = fetch_page(scraper, url)
        if html is None:
            result.skipped_years.append(year)
            continue

        cars = parse_car_table(html, year)
        all_cars.extend(cars)

        result.years_scraped.append(year)
        result.total_cars_found += len(cars)

        logger.info(f"  → {len(cars)} cars found for {year}")

        # Polite delay between requests
        if len(years) > 1:
            time.sleep(delay)

    result.total_cars_found = len(all_cars)
    return result, all_cars

"""
Hot Wheels wiki scraper.

Uses the Fandom API (api.php) instead of scraping HTML pages directly,
which avoids Cloudflare blocks on GitHub Actions.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag

from .models import HotWheelsCar, ScrapeResult

logger = logging.getLogger(__name__)

# Hot Wheels started in 1968
FIRST_YEAR = 1968

# Fandom API base URL
API_BASE = "https://hotwheels.fandom.com/api.php"

# User-Agent
USER_AGENT = (
    "HotWheelsScraper/1.0 "
    "(https://github.com/holamellamoyago/hotwheels-scraper; "
    "contact@example.com)"
)


def _api_get(params: dict, timeout: int = 30) -> Optional[dict]:
    """Call the Fandom API and return the JSON response, or None on failure."""
    try:
        resp = requests.get(
            API_BASE,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 404:
            logger.warning(f"API 404 for params: {params}")
            return None
        else:
            logger.warning(f"API HTTP {resp.status_code} for params: {params}")
            return None
    except Exception as e:
        logger.error(f"API error: {e}")
        return None


def fetch_page_html(year: int) -> Optional[str]:
    """
    Fetch the HTML table for a given year via the Fandom parse API.
    Returns the HTML string from parse.text.* or None.
    """
    data = _api_get({
        "action": "parse",
        "page": f"List_of_{year}_Hot_Wheels",
        "prop": "text",
        "format": "json",
    })
    if data and "parse" in data and "text" in data["parse"]:
        return data["parse"]["text"]["*"]
    return None


def parse_car_table(html: str, year: int) -> list[HotWheelsCar]:
    """
    Parse a wikitable from the Fandom API HTML output.

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
            continue

        for row in data_rows:
            cells = row.find_all("td")
            if not cells:
                continue

            car = HotWheelsCar(year=year)

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
        result["toy_num"] = texts[0]
        result["col_num"] = texts[1]
        result["model_name"] = texts[2]
        result["series"] = texts[3]
        result["series_num"] = texts[4]
    elif num_cells == 5:
        result["toy_num"] = texts[0]
        result["model_name"] = texts[1]
        result["series"] = texts[2]
        result["series_num"] = texts[3]
    elif num_cells == 4:
        result["toy_num"] = texts[0]
        result["model_name"] = texts[1]
        result["series"] = texts[2]
    elif num_cells == 3:
        result["toy_num"] = texts[0]
        result["model_name"] = texts[1]
        result["series"] = texts[2]
    else:
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
    delay: float = 1.0,
) -> tuple[ScrapeResult, list[HotWheelsCar]]:
    """
    Scrape multiple years from the Hot Wheels Fandom wiki via the API.

    Args:
        years: List of years to scrape.
        delay: Delay in seconds between requests to be polite.

    Returns:
        Tuple of (ScrapeResult, list of all cars).
    """
    result = ScrapeResult()
    all_cars: list[HotWheelsCar] = []

    for year in years:
        logger.info(f"Scraping {year}...")

        html = fetch_page_html(year)
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

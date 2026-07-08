"""
Hot Wheels Scraper - CLI entry point.

Usage:
    # Scrape all years (full refresh)
    python -m src.main --all

    # Scrape only the current year (daily update)
    python -m src.main --daily

    # Scrape a specific range
    python -m src.main --years 2024 2025 2026

    # Dry run (don't push to Supabase, just print stats)
    python -m src.main --daily --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date

from .scraper import (
    FIRST_YEAR,
    get_available_years,
    scrape_years,
)
from .supabase_client import SupabaseClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hot Wheels wiki scraper → Supabase"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--all",
        action="store_true",
        help="Scrape all years (1968 to current)",
    )
    group.add_argument(
        "--daily",
        action="store_true",
        help="Scrape only the current year",
    )
    group.add_argument(
        "--years",
        nargs="+",
        type=int,
        help="Specific years to scrape (e.g. 2024 2025)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't push to Supabase, just print stats",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Delay in seconds between page requests (default: 1.5)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Determine which years to scrape
    if args.all:
        years = get_available_years()
        logger.info(f"🎯 Full scrape: {len(years)} years ({years[0]}-{years[-1]})")
    elif args.daily:
        current_year = date.today().year
        years = [current_year]
        logger.info(f"🎯 Daily scrape: current year ({current_year})")
    elif args.years:
        years = sorted(args.years)
        logger.info(f"🎯 Custom years: {years}")
    else:
        # Default: current year only
        current_year = date.today().year
        years = [current_year]
        logger.info(f"🎯 Default: current year ({current_year})")

    # Scrape
    logger.info("🕷️  Starting scraper...")
    result, all_cars = scrape_years(years, delay=args.delay)

    print()  # blank line for readability
    print("=" * 50)
    print(result.summary())
    print("=" * 50)

    if not all_cars:
        logger.warning("⚠️  No cars found in any scraped year!")
        sys.exit(1)

    # Push to Supabase (unless dry run)
    if args.dry_run:
        logger.info(f"🏁 Dry run complete. Would push {len(all_cars)} cars.")
        return

    supabase = SupabaseClient()
    if not supabase.is_configured:
        logger.error(
            "❌ Supabase not configured! Set SUPABASE_URL and "
            "SUPABASE_SERVICE_KEY in environment or .env file."
        )
        logger.info(
            "   Run with --dry-run to test scraping without pushing."
        )
        sys.exit(1)

    logger.info(f"📤 Pushing {len(all_cars)} cars to Supabase...")
    inserted, updated = supabase.upsert_cars(all_cars)

    print()
    print("=" * 50)
    print(f"📦 Supabase result:")
    print(f"   Inserted: {inserted}")
    print(f"   Updated: {updated}")
    print(f"   Total in DB: {supabase.get_car_count()}")
    print("=" * 50)

    errors = [y for y in years if y not in result.years_scraped and y not in result.skipped_years]
    if errors:
        logger.warning(f"⚠️  Years with issues: {errors}")
        sys.exit(1)

    logger.info("✅ Done!")


if __name__ == "__main__":
    main()

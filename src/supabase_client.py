"""
Supabase client for inserting Hot Wheels data.

Uses the Supabase REST API directly for simplicity (no extra SDK dependency
in the scraper - it just runs in GitHub Actions).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from .models import HotWheelsCar

logger = logging.getLogger(__name__)


class SupabaseClient:
    """Minimal Supabase client for bulk upserting car data."""

    def __init__(
        self,
        url: Optional[str] = None,
        anon_key: Optional[str] = None,
        service_key: Optional[str] = None,
    ):
        self.url = (url or os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.anon_key = anon_key or os.getenv("SUPABASE_ANON_KEY", "")
        self.service_key = service_key or os.getenv("SUPABASE_SERVICE_KEY", "")

        # Use service key for writes (bypasses RLS)
        self.headers = {
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        if self.service_key:
            self.headers["apikey"] = self.service_key
            self.headers["Authorization"] = f"Bearer {self.service_key}"
        elif self.anon_key:
            self.headers["apikey"] = self.anon_key
            self.headers["Authorization"] = f"Bearer {self.anon_key}"

    @property
    def is_configured(self) -> bool:
        """Check if the client has enough config to connect."""
        return bool(self.url and (self.service_key or self.anon_key))

    def upsert_cars(self, cars: list[HotWheelsCar]) -> tuple[int, int]:
        """
        Upsert cars into Supabase.

        Deduplicates by (year, toy_num, model_name) within the batch to avoid
        "ON CONFLICT DO UPDATE command cannot affect row a second time" errors.
        Ensures all records in a batch have identical keys to avoid PGRST102.

        Returns:
            Tuple of (inserted_count, updated_count).
        """
        if not cars:
            return 0, 0

        if not self.is_configured:
            logger.error("Supabase not configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY.")
            return 0, 0

        # Deduplicate: keep first occurrence of each (year, toy_num, model_name)
        seen: set[tuple] = set()
        deduped: list[HotWheelsCar] = []
        for car in cars:
            key = (car.year, car.toy_num, car.model_name)
            if key not in seen:
                seen.add(key)
                deduped.append(car)

        skipped = len(cars) - len(deduped)
        if skipped:
            logger.info(f"  Deduplicated {skipped} cars within batch")

        # Convert to dicts with ALL keys present (None for missing, Supabase ignores them)
        all_keys = ["toy_num", "model_name", "series", "series_num", "year", "image_url", "raw_data"]
        records = []
        for car in deduped:
            base = car.to_supabase_dict()
            record = {k: base.get(k) for k in all_keys}
            records.append(record)

        # Split into batches of 100 (Supabase limit)
        batch_size = 100
        total_inserted = 0
        total_updated = 0

        with httpx.Client(timeout=30) as client:
            for i in range(0, len(records), batch_size):
                batch = records[i : i + batch_size]
                inserted, updated = self._upsert_batch(client, batch)
                total_inserted += inserted
                total_updated += updated

                logger.info(f"  Batch {i//batch_size + 1}: {inserted} inserted, {updated} updated")

        return total_inserted, total_updated

    def _upsert_batch(
        self, client: httpx.Client, records: list[dict]
    ) -> tuple[int, int]:
        """Upsert a single batch of records."""
        endpoint = f"{self.url}/rest/v1/cars"

        # Supabase upsert: POST with on_conflict resolution
        response = client.post(
            endpoint,
            headers={
                **self.headers,
                "Prefer": (
                    "resolution=merge-duplicates"
                    ","  # merge on conflict
                    "return=representation"  # return the rows
                ),
            },
            params={
                "on_conflict": "year,toy_num,model_name",
            },
            json=records,
        )

        if response.status_code in (200, 201):
            data = response.json()
            return len(data), len(data)
        else:
            logger.error(
                f"Supabase upsert failed: {response.status_code} - {response.text[:500]}"
            )
            return 0, 0

    def get_car_count(self) -> int:
        """Get the total number of cars in the database."""
        endpoint = f"{self.url}/rest/v1/cars"

        with httpx.Client(timeout=10) as client:
            response = client.get(
                endpoint,
                headers={
                    "apikey": self.service_key or self.anon_key,
                    "Authorization": f"Bearer {self.service_key or self.anon_key}",
                    "Prefer": "count=exact",
                },
                params={"select": "id", "limit": 0},
            )

            if response.status_code in (200, 206):
                content_range = response.headers.get("content-range", "")
                # Format: "0-0/12345" or "*/12345"
                if "/" in content_range:
                    try:
                        return int(content_range.split("/")[1])
                    except (IndexError, ValueError):
                        pass

        return 0

"""Data models for Hot Wheels cars."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HotWheelsCar:
    """Represents a single Hot Wheels car entry from the wiki."""

    toy_num: Optional[str] = None
    model_name: str = ""
    series: Optional[str] = None
    series_num: Optional[str] = None
    year: int = 0
    image_url: Optional[str] = None
    col_num: Optional[str] = None
    raw_data: Optional[dict] = None

    def clean(self):
        """Clean and normalize all fields."""
        # Remove '[]' artifacts from wiki table cells
        self.model_name = self._clean_text(self.model_name)
        self.series = self._clean_text(self.series) if self.series else None
        self.toy_num = self._clean_text(self.toy_num) if self.toy_num else None
        self.series_num = self._clean_text(self.series_num) if self.series_num else None

        # Normalize image URL - ensure it's a full URL
        if self.image_url and not self.image_url.startswith("http"):
            self.image_url = None

        return self

    @staticmethod
    def _clean_text(text: str) -> str:
        """Remove wiki artifacts like [1], [2], etc. and trim whitespace."""
        text = re.sub(r'\[\d+\]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def to_supabase_dict(self) -> dict:
        """Convert to dict for Supabase upsert."""
        return {
            "toy_num": self.toy_num,
            "model_name": self.model_name,
            "series": self.series,
            "series_num": self.series_num,
            "year": self.year,
            "image_url": self.image_url,
            "raw_data": self.raw_data,
        }

    @property
    def is_valid(self) -> bool:
        """Check if the car has at least a model name and year."""
        return bool(self.model_name) and self.year > 0


@dataclass
class ScrapeResult:
    """Result of a scraping run."""

    years_scraped: list[int] = field(default_factory=list)
    total_cars_found: int = 0
    total_inserted: int = 0
    total_updated: int = 0
    errors: list[str] = field(default_factory=list)
    skipped_years: list[int] = field(default_factory=list)

    def summary(self) -> str:
        """Generate a human-readable summary."""
        lines = [
            f"📊 Scrape result:",
            f"   Years scraped: {len(self.years_scraped)}",
            f"   Cars found: {self.total_cars_found}",
            f"   Inserted: {self.total_inserted}",
            f"   Updated: {self.total_updated}",
        ]
        if self.skipped_years:
            lines.append(f"   Skipped years: {len(self.skipped_years)}")
        if self.errors:
            lines.append(f"   Errors: {len(self.errors)}")
            for err in self.errors[-5:]:  # Show last 5 errors
                lines.append(f"     ⚠ {err}")
        return "\n".join(lines)

"""Compatibility entry point for older workflows.

The original monitor command now runs the cloud scraping + dashboard pipeline.
It still writes CSV/JSON/XLSX files under output/ and never automates purchases.
"""

from __future__ import annotations

from src.run_cloud_pipeline import main


if __name__ == "__main__":
    raise SystemExit(main())

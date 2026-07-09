"""Cloud pipeline entry point: scrape Enoking, discover supplier candidates, build Pages site."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from src.enoking_scraper import DEFAULT_BASE_URL, crawl_enoking_products, product_to_dict, write_outputs
from src.site_builder import build_static_site
from src.supplier_discovery import generate_opportunities, write_opportunities

JST = timezone(timedelta(hours=9), "JST")


def run_pipeline() -> dict[str, object]:
    products = crawl_enoking_products(DEFAULT_BASE_URL)
    product_paths = write_outputs(products)
    product_rows = [product_to_dict(product) for product in products]
    opportunities = generate_opportunities(product_rows)
    opportunity_paths = write_opportunities(opportunities)
    site_metadata = build_static_site()
    return {
        "finished_at_jst": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "product_count": len(products),
        "opportunity_count": len(opportunities),
        "product_outputs": product_paths,
        "opportunity_outputs": opportunity_paths,
        "site_metadata": site_metadata,
        "top_opportunities": [asdict(row) for row in opportunities[:10]],
    }


def main() -> int:
    summary = run_pipeline()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

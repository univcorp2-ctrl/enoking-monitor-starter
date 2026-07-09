"""Low-cost supplier discovery and gross-margin opportunity generation.

Default mode does not scrape retail websites. It generates search links and reads
optional manually curated supplier candidates. If RAKUTEN_APPLICATION_ID is set,
it can also query the official Rakuten Ichiba Search API at a limited rate.
"""

from __future__ import annotations

import csv
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus

import requests

from src.product_matcher import triple_check_product

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "output"
JST = timezone(timedelta(hours=9), "JST")
REQUEST_TIMEOUT_SEC = int(os.getenv("REQUEST_TIMEOUT_SEC", "25"))
REQUEST_INTERVAL_SEC = float(os.getenv("SUPPLIER_REQUEST_INTERVAL_SEC", "1.0"))
RAKUTEN_MAX_PRODUCTS = int(os.getenv("RAKUTEN_MAX_PRODUCTS", "30"))
RAKUTEN_HITS = int(os.getenv("RAKUTEN_HITS", "5"))


@dataclass(frozen=True)
class SupplierOffer:
    jan: str
    supplier: str
    supplier_product_name: str
    url: str
    supplier_price_yen: int | None
    stock_status: str
    condition: str
    image_url: str
    source_type: str
    fetched_at_jst: str


@dataclass(frozen=True)
class Opportunity:
    jan: str
    product_name: str
    category: str
    enoking_buy_price_yen: int
    supplier: str
    supplier_product_name: str
    supplier_url: str
    supplier_price_yen: int | None
    gross_gap_yen: int | None
    stock_status: str
    condition: str
    match_status: str
    match_score: int
    triple_check_done: bool
    jan_exact: bool
    title_model_match: bool
    variant_safe: bool
    warning: str
    source_type: str
    search_links: dict[str, str]
    fetched_at_jst: str


def to_int(value: object) -> int | None:
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else None


def build_search_links(product: dict[str, object]) -> dict[str, str]:
    jan = str(product.get("jan") or "").strip()
    name = str(product.get("product_name") or "").strip()
    query = jan or name
    name_query = quote_plus(name)
    jan_query = quote_plus(query)
    return {
        "Google Shopping": f"https://www.google.com/search?tbm=shop&q={jan_query}",
        "Rakuten": f"https://search.rakuten.co.jp/search/mall/{jan_query}/",
        "Yahoo Shopping": f"https://shopping.yahoo.co.jp/search?p={jan_query}",
        "Amazon JP": f"https://www.amazon.co.jp/s?k={jan_query}",
        "Google Name": f"https://www.google.com/search?tbm=shop&q={name_query}",
    }


def read_supplier_candidates(path: Path = CONFIG_DIR / "supplier_candidates.csv") -> list[SupplierOffer]:
    if not path.exists():
        return []
    offers: list[SupplierOffer] = []
    fetched_at = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S %Z")
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if not row or not row.get("jan") or not row.get("url"):
                continue
            offers.append(
                SupplierOffer(
                    jan=str(row.get("jan", "")).strip(),
                    supplier=str(row.get("supplier", "manual")).strip() or "manual",
                    supplier_product_name=str(row.get("supplier_product_name") or row.get("product_name") or "").strip(),
                    url=str(row.get("url", "")).strip(),
                    supplier_price_yen=to_int(row.get("supplier_price_yen")),
                    stock_status=str(row.get("stock_status", "manual_check")).strip() or "manual_check",
                    condition=str(row.get("condition", "new")).strip() or "new",
                    image_url=str(row.get("image_url", "")).strip(),
                    source_type="manual_csv",
                    fetched_at_jst=fetched_at,
                )
            )
    return offers


def rakuten_api_offers(products: list[dict[str, object]]) -> list[SupplierOffer]:
    application_id = os.getenv("RAKUTEN_APPLICATION_ID", "").strip()
    if not application_id:
        return []
    offers: list[SupplierOffer] = []
    fetched_at = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S %Z")
    session = requests.Session()
    endpoint = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"
    for index, product in enumerate(products[:RAKUTEN_MAX_PRODUCTS]):
        keyword = str(product.get("jan") or product.get("product_name") or "").strip()
        if not keyword:
            continue
        response = session.get(
            endpoint,
            params={
                "format": "json",
                "applicationId": application_id,
                "keyword": keyword,
                "hits": RAKUTEN_HITS,
                "sort": "+itemPrice",
            },
            timeout=REQUEST_TIMEOUT_SEC,
        )
        if response.status_code >= 400:
            continue
        payload = response.json()
        for item_wrapper in payload.get("Items", []):
            item = item_wrapper.get("Item", {})
            images = item.get("mediumImageUrls") or []
            image_url = images[0].get("imageUrl", "") if images else ""
            offers.append(
                SupplierOffer(
                    jan=str(product.get("jan") or ""),
                    supplier="Rakuten Ichiba API",
                    supplier_product_name=str(item.get("itemName") or ""),
                    url=str(item.get("itemUrl") or ""),
                    supplier_price_yen=to_int(item.get("itemPrice")),
                    stock_status="api_result_manual_stock_check",
                    condition="new_or_unknown",
                    image_url=image_url,
                    source_type="rakuten_api",
                    fetched_at_jst=fetched_at,
                )
            )
        if REQUEST_INTERVAL_SEC > 0 and index < len(products) - 1:
            time.sleep(REQUEST_INTERVAL_SEC)
    return offers


def make_search_only_opportunity(product: dict[str, object]) -> Opportunity:
    fetched_at = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S %Z")
    return Opportunity(
        jan=str(product.get("jan") or ""),
        product_name=str(product.get("product_name") or ""),
        category=str(product.get("category") or ""),
        enoking_buy_price_yen=to_int(product.get("buy_price_yen")) or 0,
        supplier="検索リンク",
        supplier_product_name="",
        supplier_url="",
        supplier_price_yen=None,
        gross_gap_yen=None,
        stock_status="search_links_only",
        condition="manual_check_required",
        match_status="NOT_CHECKED_SEARCH_ONLY",
        match_score=0,
        triple_check_done=False,
        jan_exact=False,
        title_model_match=False,
        variant_safe=False,
        warning="仕入れ先候補URLを開き、JAN/名称/色/容量を確認してください。APIまたはCSV候補がある場合は自動トリプルチェックされます。",
        source_type="generated_search_links",
        search_links=build_search_links(product),
        fetched_at_jst=fetched_at,
    )


def offer_to_opportunity(product: dict[str, object], offer: SupplierOffer) -> Opportunity:
    check = triple_check_product(product, asdict(offer))
    buy_price = to_int(product.get("buy_price_yen")) or 0
    supplier_price = offer.supplier_price_yen
    gap = buy_price - supplier_price if supplier_price is not None else None
    return Opportunity(
        jan=str(product.get("jan") or ""),
        product_name=str(product.get("product_name") or ""),
        category=str(product.get("category") or ""),
        enoking_buy_price_yen=buy_price,
        supplier=offer.supplier,
        supplier_product_name=offer.supplier_product_name,
        supplier_url=offer.url,
        supplier_price_yen=supplier_price,
        gross_gap_yen=gap,
        stock_status=offer.stock_status,
        condition=offer.condition,
        match_status=check.status,
        match_score=check.score,
        triple_check_done=True,
        jan_exact=check.jan_exact,
        title_model_match=check.title_model_match,
        variant_safe=check.variant_safe,
        warning=check.warning,
        source_type=offer.source_type,
        search_links=build_search_links(product),
        fetched_at_jst=offer.fetched_at_jst,
    )


def generate_opportunities(products: list[dict[str, object]], offers: Iterable[SupplierOffer] | None = None) -> list[Opportunity]:
    product_by_jan = {str(product.get("jan") or ""): product for product in products if product.get("jan")}
    all_offers = list(offers or []) + read_supplier_candidates() + rakuten_api_offers(products)
    opportunities: list[Opportunity] = []
    used_jans: set[str] = set()
    for offer in all_offers:
        product = product_by_jan.get(offer.jan)
        if product is None:
            continue
        opportunities.append(offer_to_opportunity(product, offer))
        used_jans.add(offer.jan)
    for product in products:
        jan = str(product.get("jan") or "")
        if jan not in used_jans:
            opportunities.append(make_search_only_opportunity(product))
    return sorted(
        opportunities,
        key=lambda row: (
            row.gross_gap_yen is None,
            -(row.gross_gap_yen or -10**9),
            row.product_name,
        ),
    )


def write_opportunities(opportunities: list[Opportunity], output_dir: Path = OUTPUT_DIR) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    paths = {
        "json": output_dir / f"opportunities_{stamp}.json",
        "csv": output_dir / f"opportunities_{stamp}.csv",
        "latest_json": output_dir / "latest_opportunities.json",
        "latest_csv": output_dir / "latest_opportunities.csv",
    }
    rows = [asdict(opportunity) for opportunity in opportunities]
    for json_path in [paths["json"], paths["latest_json"]]:
        with json_path.open("w", encoding="utf-8") as file:
            json.dump(rows, file, ensure_ascii=False, indent=2)
    fieldnames = list(rows[0].keys()) if rows else ["message"]
    for csv_path in [paths["csv"], paths["latest_csv"]]:
        with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            if rows:
                writer.writerows(rows)
            else:
                writer.writerow({"message": "NO_OPPORTUNITIES"})
    return {key: str(path) for key, path in paths.items()}

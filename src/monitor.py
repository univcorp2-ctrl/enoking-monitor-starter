"""Enoking supplier monitor starter.

Fetches supplier pages, extracts rough price/stock signals, compares with
Enoking buyback prices, and writes a CSV report.

This script intentionally does not automate purchases, login, CAPTCHA, or
queue bypass. Use low-frequency scheduled runs and respect each site's terms.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "output"
NOTIFY_STATE_PATH = OUTPUT_DIR / "notify_state.json"
JST = timezone(timedelta(hours=9), "JST")
BUY_MARGIN_THRESHOLD_YEN = int(os.getenv("BUY_MARGIN_THRESHOLD_YEN", "2000"))
REQUEST_TIMEOUT_SEC = int(os.getenv("REQUEST_TIMEOUT_SEC", "20"))
USER_AGENT = os.getenv(
    "MONITOR_USER_AGENT",
    "Mozilla/5.0 (compatible; EnokingMonitorStarter/1.0; +https://github.com/)"
)

# Official marketplace APIs. When credentials are set, rakuten/yahoo suppliers
# are monitored via API instead of HTML scraping.
RAKUTEN_APP_ID = os.getenv("RAKUTEN_APP_ID", "")
RAKUTEN_ACCESS_KEY = os.getenv("RAKUTEN_ACCESS_KEY", "")
YAHOO_APP_ID = os.getenv("YAHOO_APP_ID", "")
RAKUTEN_API_URL = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"
YAHOO_API_URL = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"
USED_ITEM_SIGNALS = ["中古", "新古", "未使用品", "再生品", "リファービッシュ"]

NEGATIVE_STOCK_SIGNALS = [
    "在庫なし",
    "完売御礼",
    "完売",
    "販売終了",
    "ただいま購入できません",
    "売り切れ",
    "品切れ",
]
POSITIVE_STOCK_SIGNALS = [
    "カートに入れる",
    "購入手続き",
    "即納（在庫あり）",
    "在庫あり",
    "注文する",
]
JS_REQUIRED_SIGNALS = [
    "JavaScriptを有効にする必要があります",
    "このページではjavascriptを使用しています",
    "javascriptを使用しています",
]


@dataclass
class Product:
    jan: str
    product_name: str
    enoking_buy_price_yen: int
    required_condition: str


@dataclass
class Supplier:
    jan: str
    supplier: str
    url: str
    expected_price_yen: int | None
    shipping_included: bool
    condition_required: str
    enabled: bool
    parser_hint: str
    notes: str


@dataclass
class ParseResult:
    parsed_price_yen: int | None
    in_stock: bool | None
    raw_signals: str
    notes: str
    shipping_included: bool | None = None
    resolved_url: str | None = None
    shop: str = ""


@dataclass
class ApiItem:
    price_yen: int
    in_stock: bool
    shipping_included: bool | None
    url: str
    shop: str
    name: str
    jan: str = ""
    caption: str = ""


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    value = str(value).strip().replace(",", "")
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def load_products(path: Path = CONFIG_DIR / "products_sample.csv") -> dict[str, Product]:
    products: dict[str, Product] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            product = Product(
                jan=row["jan"].strip(),
                product_name=row["product_name"].strip(),
                enoking_buy_price_yen=int(row["enoking_buy_price_yen"]),
                required_condition=row.get("required_condition", "new").strip(),
            )
            products[product.jan] = product
    return products


def load_suppliers(path: Path = CONFIG_DIR / "supplier_urls.csv") -> list[Supplier]:
    suppliers: list[Supplier] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            suppliers.append(
                Supplier(
                    jan=row["jan"].strip(),
                    supplier=row["supplier"].strip(),
                    url=row["url"].strip(),
                    expected_price_yen=parse_int(row.get("expected_price_yen")),
                    shipping_included=parse_bool(row.get("shipping_included", "false")),
                    condition_required=row.get("condition_required", "new").strip(),
                    enabled=parse_bool(row.get("enabled", "true")),
                    parser_hint=row.get("parser_hint", "generic").strip(),
                    notes=row.get("notes", "").strip(),
                )
            )
    return suppliers


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u3000", " ")).strip()


def yen_to_int(value: str) -> int | None:
    return parse_int(value.replace("円", "").replace("税込", ""))


def extract_prices(text: str) -> list[int]:
    candidates: list[int] = []
    for match in re.finditer(r"(?:￥|価格[:：]?|税込|本体価格)?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,6})\s*円?", text):
        price = yen_to_int(match.group(1))
        if price and 10_000 <= price <= 200_000:
            candidates.append(price)
    return candidates


def first_price_after_label(text: str, label_pattern: str) -> int | None:
    match = re.search(label_pattern + r".{0,120}?([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,6})\s*円", text, re.DOTALL)
    if match:
        return yen_to_int(match.group(1))
    return None


def detect_stock(text: str) -> bool | None:
    if any(signal in text for signal in NEGATIVE_STOCK_SIGNALS):
        return False
    if any(signal in text for signal in POSITIVE_STOCK_SIGNALS):
        return True
    return None


def parse_yahoo(text: str) -> ParseResult:
    price = first_price_after_label(text, r"価格")
    in_stock = detect_stock(text)
    return ParseResult(price, in_stock, stock_signal_summary(text), "")


def parse_nojima(text: str) -> ParseResult:
    # Nojima pages can show a struck-through reference price before the actual one.
    price = None
    tax_prices = [
        yen_to_int(p)
        for p in re.findall(r"([0-9]{1,3}(?:,[0-9]{3})+)円\s*\(税込\)", text)
    ]
    tax_prices = [p for p in tax_prices if p is not None]
    ref_match = re.search(r"参考価格[:：][^0-9]{0,20}([0-9]{1,3}(?:,[0-9]{3})+)円", text)
    if ref_match and tax_prices:
        ref_price = yen_to_int(ref_match.group(1))
        tax_prices = [p for p in tax_prices if p != ref_price] or tax_prices
    if tax_prices:
        price = min(tax_prices)
    else:
        prices = extract_prices(text)
        if prices:
            price = min(prices)
    in_stock = detect_stock(text)
    return ParseResult(price, in_stock, stock_signal_summary(text), "")


def parse_aeon(text: str) -> ParseResult:
    price = first_price_after_label(text, r"税込") or first_price_after_label(text, r"本体価格")
    in_stock = detect_stock(text)
    return ParseResult(price, in_stock, stock_signal_summary(text), "")


def parse_yodobashi(text: str) -> ParseResult:
    price = None
    match = re.search(r"￥\s*([0-9]{1,3}(?:,[0-9]{3})+)", text)
    if match:
        price = yen_to_int(match.group(1))
    if price is None:
        price = first_price_after_label(text, r"価格")
    in_stock = detect_stock(text)
    return ParseResult(price, in_stock, stock_signal_summary(text), "")


def parse_generic(text: str) -> ParseResult:
    prices = extract_prices(text)
    price = min(prices) if prices else None
    return ParseResult(price, detect_stock(text), stock_signal_summary(text), "")


def parse_page(text: str, supplier: Supplier) -> ParseResult:
    normalized = normalize_text(text)
    if any(signal in normalized for signal in JS_REQUIRED_SIGNALS):
        return ParseResult(None, None, stock_signal_summary(normalized), "NEEDS_BROWSER_OR_MANUAL_CHECK")

    hint = supplier.parser_hint.lower()
    if hint == "yahoo":
        return parse_yahoo(normalized)
    if hint == "nojima":
        return parse_nojima(normalized)
    if hint == "aeon":
        return parse_aeon(normalized)
    if hint == "yodobashi":
        return parse_yodobashi(normalized)
    return parse_generic(normalized)


def stock_signal_summary(text: str) -> str:
    signals: list[str] = []
    for signal in NEGATIVE_STOCK_SIGNALS + POSITIVE_STOCK_SIGNALS + JS_REQUIRED_SIGNALS:
        if signal in text:
            signals.append(signal)
    return "|".join(dict.fromkeys(signals))


def looks_used(name: str) -> bool:
    return any(signal in name for signal in USED_ITEM_SIGNALS)


def parse_rakuten_api(payload: dict[str, Any]) -> list[ApiItem]:
    items: list[ApiItem] = []
    for entry in payload.get("Items", []):
        # formatVersion=1 nests under "Item"; formatVersion=2 is already flat.
        item = entry.get("Item", entry)
        price = parse_int(item.get("itemPrice"))
        if price is None:
            continue
        items.append(ApiItem(
            price_yen=price,
            in_stock=item.get("availability") == 1,
            shipping_included=item.get("postageFlag") == 0,
            url=item.get("itemUrl", ""),
            shop=item.get("shopName", ""),
            name=item.get("itemName", ""),
            jan="",  # Ichiba search has no JAN field; confirmed on the listing page.
            caption=item.get("itemCaption", ""),
        ))
    return items


def parse_yahoo_api(payload: dict[str, Any]) -> list[ApiItem]:
    items: list[ApiItem] = []
    for hit in payload.get("hits", []):
        price = parse_int(hit.get("price"))
        if price is None:
            continue
        if hit.get("condition", "new") != "new":
            continue
        # shipping.code: 1=設定なし, 2=条件付き送料無料, 3=送料無料
        shipping_code = (hit.get("shipping") or {}).get("code")
        if shipping_code == 3:
            shipping_included: bool | None = True
        elif shipping_code == 1:
            shipping_included = False
        else:
            shipping_included = None
        items.append(ApiItem(
            price_yen=price,
            in_stock=bool(hit.get("inStock", False)),
            shipping_included=shipping_included,
            url=hit.get("url", ""),
            shop=(hit.get("seller") or {}).get("name", ""),
            name=hit.get("name", ""),
            jan=str(hit.get("janCode") or ""),
            caption=hit.get("description", "") or "",
        ))
    return items


def rank_items(items: list[ApiItem]) -> list[ApiItem]:
    """New items first, then API-in-stock first, then cheapest."""
    fresh = [item for item in items if not looks_used(item.name)] or items
    return sorted(fresh, key=lambda item: (not item.in_stock, item.price_yen))


def verify_on_page(item: ApiItem, jan: str) -> tuple[str, bool | None, str]:
    """Fetch the listing page and confirm JAN + stock wording.

    Returns (jan_status, stock_confirmed, note) where jan_status is
    "match" / "mismatch" / "unknown" and stock_confirmed is True/False/None.
    """
    if item.jan:
        jan_status = "match" if item.jan == jan else "mismatch"
        if jan_status == "mismatch":
            return jan_status, None, f"JAN不一致(API:{item.jan})"
    else:
        jan_status = "unknown"

    status_code, html, error = fetch(item.url)
    if error:
        return jan_status, None, f"ページ検証不可:{error}"
    text = normalize_text(html)

    if jan_status != "match":
        jan_status = "match" if jan in html or jan in text else "unknown"

    if any(signal in text for signal in JS_REQUIRED_SIGNALS):
        return jan_status, None, "在庫:JSページのため未確認"

    stock = detect_stock(text)
    signals = stock_signal_summary(text)
    label = {True: "在庫あり", False: "品切れ", None: "在庫表記なし"}[stock]
    return jan_status, stock, f"在庫:{label}" + (f"({signals})" if signals else "")


RETRYABLE_STATUS = {403, 429, 500, 502, 503}


def api_get(url: str, params: dict[str, Any]) -> requests.Response:
    """GET with a short backoff retry on transient rate-limit responses."""
    response = None
    for attempt in range(3):
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SEC)
        if response.status_code in RETRYABLE_STATUS and attempt < 2:
            time.sleep(2 * (attempt + 1))
            continue
        break
    assert response is not None
    response.raise_for_status()
    return response


def fetch_rakuten_api(jan: str) -> tuple[list[ApiItem], str]:
    params: dict[str, Any] = {
        "applicationId": RAKUTEN_APP_ID,
        "keyword": jan,
        "hits": 30,
        "sort": "+itemPrice",
        "formatVersion": 2,
    }
    # accessKey is required for newer (UUID-style) applicationId credentials.
    if RAKUTEN_ACCESS_KEY:
        params["accessKey"] = RAKUTEN_ACCESS_KEY
    try:
        return parse_rakuten_api(api_get(RAKUTEN_API_URL, params).json()), ""
    except (requests.RequestException, ValueError) as exc:
        return [], f"RAKUTEN_API_ERROR: {exc.__class__.__name__}: {exc}"


def fetch_yahoo_api(jan: str) -> tuple[list[ApiItem], str]:
    params = {"appid": YAHOO_APP_ID, "jan_code": jan, "results": 30}
    try:
        return parse_yahoo_api(api_get(YAHOO_API_URL, params).json()), ""
    except (requests.RequestException, ValueError) as exc:
        return [], f"YAHOO_API_ERROR: {exc.__class__.__name__}: {exc}"


VERIFY_LIMIT = 8
TOP_OFFERS = 3

API_SOURCES = {"rakuten": "楽天市場", "yahoo": "Yahoo!ショッピング"}


def scan_marketplace(jan: str, source: str, limit: int = TOP_OFFERS) -> list[ParseResult]:
    """Search a whole marketplace for a JAN and return the cheapest offers.

    Rakuten/Yahoo cover thousands of shops each, so one scan diversifies
    suppliers automatically. Each candidate is confirmed on its listing
    page: an in-stock result requires a JAN match and positive stock
    wording. Returns an empty list when the API is not configured.
    """
    if source == "rakuten":
        if not RAKUTEN_APP_ID:
            return []
        items, error = fetch_rakuten_api(jan)
    elif source == "yahoo":
        if not YAHOO_APP_ID:
            return []
        items, error = fetch_yahoo_api(jan)
    else:
        return []
    if error:
        return [ParseResult(None, None, f"api:{source}", error)]

    ranked = rank_items(items)
    verified: list[ParseResult] = []
    fallback: list[ParseResult] = []
    for item in ranked[:VERIFY_LIMIT]:
        jan_status, stock, note = verify_on_page(item, jan)
        if jan_status == "mismatch":
            continue
        confirmed = jan_status == "match" and stock is True
        jan_text = "JAN一致" if jan_status == "match" else "JAN未確認"
        result = ParseResult(
            parsed_price_yen=item.price_yen,
            in_stock=True if confirmed else None,
            raw_signals=f"api:{source}|hits={len(items)}|{'verified' if confirmed else 'unverified'}",
            notes=f"{jan_text} / {note}" if confirmed else f"要手動確認 / {jan_text} / {note}",
            shipping_included=item.shipping_included,
            resolved_url=item.url or None,
            shop=item.shop,
        )
        (verified if confirmed else fallback).append(result)
        if len(verified) >= limit:
            break

    results = verified[:limit] or fallback[:limit]
    if results:
        return results
    return [ParseResult(
        None, None, f"api:{source}|hits={len(items)}",
        f"在庫ありの候補なし ({source})",
    )]


def fetch(url: str) -> tuple[int | None, str, str]:
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            },
            timeout=REQUEST_TIMEOUT_SEC,
        )
        response.encoding = response.apparent_encoding or response.encoding
        return response.status_code, response.text, ""
    except requests.RequestException as exc:
        return None, "", f"FETCH_ERROR: {exc.__class__.__name__}: {exc}"


def evaluate(product: Product, supplier: Supplier, result: ParseResult) -> dict[str, Any]:
    price = result.parsed_price_yen or supplier.expected_price_yen
    shipping_included = (
        result.shipping_included
        if result.shipping_included is not None
        else supplier.shipping_included
    )
    gross_profit = product.enoking_buy_price_yen - price if price else None
    buy_candidate = (
        price is not None
        and result.in_stock is True
        and shipping_included is True
        and supplier.condition_required == product.required_condition == "new"
        and gross_profit is not None
        and gross_profit >= BUY_MARGIN_THRESHOLD_YEN
    )
    return {
        "effective_price_yen": price,
        "gross_profit_yen": gross_profit,
        "shipping_included": shipping_included,
        "is_buy_candidate": buy_candidate,
    }


def candidate_key(row: dict[str, Any]) -> str:
    return f"{row['jan']}|{row['supplier']}"


def load_notify_state() -> dict[str, Any]:
    if NOTIFY_STATE_PATH.exists():
        try:
            return json.loads(NOTIFY_STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_notify_state(candidates: list[dict[str, Any]], checked_at: str) -> None:
    state = {
        "updated_at": checked_at,
        "notified": {candidate_key(row): row["effective_price_yen"] for row in candidates},
    }
    try:
        NOTIFY_STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"notify state save failed: {exc}", file=sys.stderr)


def fresh_candidates(
    candidates: list[dict[str, Any]], state: dict[str, Any]
) -> list[dict[str, Any]]:
    """Candidates newly available since the last run, or now cheaper.

    Suppresses repeat alerts while the same offer stays available so a
    frequent cron does not spam the same buy candidate.
    """
    notified = state.get("notified", {})
    fresh: list[dict[str, Any]] = []
    for row in candidates:
        key = candidate_key(row)
        price = row["effective_price_yen"]
        previous = notified.get(key)
        if previous is None or (price is not None and price < previous):
            fresh.append(row)
    return fresh


def notify(candidates: list[dict[str, Any]]) -> None:
    if not candidates:
        return

    lines = ["Enoking monitor: buy candidates found"]
    for row in candidates[:10]:
        lines.append(
            f"- {row['product_name']} / {row['supplier']} / "
            f"price={row['effective_price_yen']} / profit={row['gross_profit_yen']} / {row['url']}"
        )
    body = "\n".join(lines)
    print(f"::notice::{body}")

    slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
    discord_webhook = os.getenv("DISCORD_WEBHOOK_URL")
    try:
        if slack_webhook:
            requests.post(slack_webhook, json={"text": body}, timeout=10)
        if discord_webhook:
            requests.post(discord_webhook, json={"content": body}, timeout=10)
    except requests.RequestException as exc:
        print(f"notification failed: {exc}", file=sys.stderr)


def build_row(
    checked_at: str,
    product: Product,
    supplier: Supplier,
    result: ParseResult,
    status_code: int | None,
    fetch_ok: bool,
) -> dict[str, Any]:
    eval_result = evaluate(product, supplier, result)
    return {
        "checked_at_jst": checked_at,
        "jan": supplier.jan,
        "product_name": product.product_name,
        "supplier": supplier.supplier,
        "url": result.resolved_url or supplier.url,
        "http_status": status_code,
        "fetch_ok": fetch_ok,
        "parser_hint": supplier.parser_hint,
        "parsed_price_yen": result.parsed_price_yen,
        "expected_price_yen": supplier.expected_price_yen,
        "effective_price_yen": eval_result["effective_price_yen"],
        "enoking_buy_price_yen": product.enoking_buy_price_yen,
        "gross_profit_yen": eval_result["gross_profit_yen"],
        "in_stock": result.in_stock,
        "shipping_included": eval_result["shipping_included"],
        "condition_required": supplier.condition_required,
        "is_buy_candidate": eval_result["is_buy_candidate"],
        "raw_signals": result.raw_signals,
        "notes": "; ".join(part for part in [supplier.notes, result.notes] if part),
    }


def api_supplier(jan: str, label: str, result: ParseResult, source: str) -> Supplier:
    name = f"{label} / {result.shop}" if result.shop else label
    return Supplier(
        jan=jan,
        supplier=name,
        url=result.resolved_url or "",
        expected_price_yen=None,
        shipping_included=False,
        condition_required="new",
        enabled=True,
        parser_hint=source,
        notes="",
    )


def main() -> int:
    products = load_products()
    suppliers = [s for s in load_suppliers() if s.enabled]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    checked_at = datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S %Z")

    rows: list[dict[str, Any]] = []

    # Marketplace API scans: every shop on Rakuten / Yahoo, top offers per JAN.
    for jan, product in products.items():
        for source, label in API_SOURCES.items():
            for result in scan_marketplace(jan, source):
                supplier = api_supplier(jan, label, result, source)
                rows.append(build_row(checked_at, product, supplier, result, None, True))

    # Direct retailer pages from config (HTML scraping).
    for supplier in suppliers:
        product = products.get(supplier.jan)
        if not product:
            print(f"Skipping unknown JAN: {supplier.jan}", file=sys.stderr)
            continue
        status_code, html, fetch_error = fetch(supplier.url)
        if fetch_error:
            parsed = ParseResult(None, None, "", fetch_error)
        else:
            parsed = parse_page(html, supplier)
        rows.append(build_row(checked_at, product, supplier, parsed, status_code, not fetch_error))

    out_path = OUTPUT_DIR / f"monitor_result_{datetime.now(JST).strftime('%Y%m%d_%H%M%S')}.csv"
    fieldnames = list(rows[0].keys()) if rows else []
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    candidates = [row for row in rows if row["is_buy_candidate"]]
    state = load_notify_state()
    to_notify = fresh_candidates(candidates, state)
    notify(to_notify)
    save_notify_state(candidates, checked_at)

    print(json.dumps({
        "output": str(out_path),
        "checked": len(rows),
        "buy_candidates": len(candidates),
        "newly_notified": len(to_notify),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

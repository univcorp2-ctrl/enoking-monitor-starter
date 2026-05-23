"""Low-load supplier monitor for Enoking buyback checks.

The monitor fetches configured supplier pages, extracts conservative price and
stock signals, compares them with Enoking buyback prices, and writes CSV/XLSX
reports for human review.

It does not automate purchases, login, CAPTCHA handling, waiting-room bypass,
cart actions, or order actions.
"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
OUTPUT_DIR = ROOT / "output"
JST = timezone(timedelta(hours=9), "JST")

BUY_MARGIN_THRESHOLD_YEN = int(os.getenv("BUY_MARGIN_THRESHOLD_YEN", "2000"))
REQUEST_TIMEOUT_SEC = int(os.getenv("REQUEST_TIMEOUT_SEC", "15"))
REQUEST_INTERVAL_SEC = float(os.getenv("REQUEST_INTERVAL_SEC", "1.0"))
USER_AGENT = os.getenv(
    "MONITOR_USER_AGENT",
    "Mozilla/5.0 (compatible; EnokingMonitorStarter/1.5; +https://github.com/univcorp2-ctrl/enoking-monitor-starter)",
)

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
    "JavaScript",
]
DISCOVERY_HINTS = {"search_discovery", "manual", "manual_check"}


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


def parse_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_int(value: str | None) -> int | None:
    value = str(value or "").strip().replace(",", "")
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
            if not row or not row.get("jan"):
                continue
            product = Product(
                jan=row["jan"].strip(),
                product_name=row.get("product_name", "").strip(),
                enoking_buy_price_yen=int(row.get("enoking_buy_price_yen") or 0),
                required_condition=row.get("required_condition", "new").strip(),
            )
            products[product.jan] = product
    return products


def load_suppliers(path: Path = CONFIG_DIR / "supplier_urls.csv") -> list[Supplier]:
    suppliers: list[Supplier] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if not row or not row.get("jan") or not row.get("url"):
                continue
            suppliers.append(
                Supplier(
                    jan=row["jan"].strip(),
                    supplier=row.get("supplier", "").strip(),
                    url=row["url"].strip(),
                    expected_price_yen=parse_int(row.get("expected_price_yen")),
                    shipping_included=parse_bool(row.get("shipping_included")),
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
    prices: list[int] = []
    pattern = r"(?:￥|価格[:：]?|税込|本体価格)?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,6})\s*円?"
    for match in re.finditer(pattern, text):
        price = yen_to_int(match.group(1))
        if price and 10_000 <= price <= 200_000:
            prices.append(price)
    return prices


def first_price_after_label(text: str, label_pattern: str) -> int | None:
    match = re.search(
        label_pattern + r".{0,140}?([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,6})\s*円",
        text,
        re.DOTALL,
    )
    if match:
        return yen_to_int(match.group(1))
    return None


def stock_signal_summary(text: str) -> str:
    signals: list[str] = []
    for signal in NEGATIVE_STOCK_SIGNALS + POSITIVE_STOCK_SIGNALS + JS_REQUIRED_SIGNALS:
        if signal in text:
            signals.append(signal)
    return "|".join(dict.fromkeys(signals))


def detect_stock(text: str) -> bool | None:
    if any(signal in text for signal in NEGATIVE_STOCK_SIGNALS):
        return False
    if any(signal in text for signal in POSITIVE_STOCK_SIGNALS):
        return True
    return None


def parse_yahoo(text: str) -> ParseResult:
    return ParseResult(first_price_after_label(text, r"価格"), detect_stock(text), stock_signal_summary(text), "")


def parse_nojima(text: str) -> ParseResult:
    prices = extract_prices(text)
    price = min(prices) if prices else None
    return ParseResult(price, detect_stock(text), stock_signal_summary(text), "")


def parse_aeon(text: str) -> ParseResult:
    price = first_price_after_label(text, r"税込") or first_price_after_label(text, r"本体価格")
    return ParseResult(price, detect_stock(text), stock_signal_summary(text), "")


def parse_yodobashi(text: str) -> ParseResult:
    match = re.search(r"￥\s*([0-9]{1,3}(?:,[0-9]{3})+)", text)
    price = yen_to_int(match.group(1)) if match else None
    if price is None:
        price = first_price_after_label(text, r"価格")
    return ParseResult(price, detect_stock(text), stock_signal_summary(text), "")


def parse_search_discovery(text: str) -> ParseResult:
    normalized = normalize_text(text)
    notes = ["DISCOVERY_ONLY_SEARCH_PAGE", "NO_BUY_DECISION"]
    if any(signal in normalized for signal in JS_REQUIRED_SIGNALS):
        notes.append("NEEDS_BROWSER_OR_MANUAL_CHECK")
    return ParseResult(None, None, stock_signal_summary(normalized), "|".join(notes))


def parse_generic(text: str) -> ParseResult:
    prices = extract_prices(text)
    return ParseResult(min(prices) if prices else None, detect_stock(text), stock_signal_summary(text), "")


def parse_page(text: str, supplier: Supplier) -> ParseResult:
    normalized = normalize_text(text)
    hint = supplier.parser_hint.lower()
    if hint in DISCOVERY_HINTS:
        return parse_search_discovery(normalized)
    if any(signal in normalized for signal in JS_REQUIRED_SIGNALS):
        return ParseResult(None, None, stock_signal_summary(normalized), "NEEDS_BROWSER_OR_MANUAL_CHECK")
    if hint == "yahoo":
        return parse_yahoo(normalized)
    if hint == "nojima":
        return parse_nojima(normalized)
    if hint == "aeon":
        return parse_aeon(normalized)
    if hint == "yodobashi":
        return parse_yodobashi(normalized)
    return parse_generic(normalized)


def is_discovery_only(supplier: Supplier, parsed: ParseResult | None = None) -> bool:
    return supplier.parser_hint.lower() in DISCOVERY_HINTS or bool(parsed and "DISCOVERY_ONLY" in parsed.notes)


def fetch(url: str) -> tuple[int | None, str, str]:
    if not url.startswith(("http://", "https://")):
        return None, "", f"FETCH_SKIPPED: unsupported URL scheme: {url}"
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"},
            timeout=REQUEST_TIMEOUT_SEC,
        )
        response.encoding = response.apparent_encoding or response.encoding
        return response.status_code, response.text, ""
    except requests.RequestException as exc:
        return None, "", f"FETCH_ERROR: {exc.__class__.__name__}: {exc}"


def evaluate(product: Product, supplier: Supplier, result: ParseResult) -> dict[str, Any]:
    if is_discovery_only(supplier, result):
        return {
            "effective_price_yen": None,
            "gross_profit_yen": None,
            "is_buy_candidate": False,
            "decision_reason": "DISCOVERY_ONLY_NO_BUY_DECISION",
        }
    price = result.parsed_price_yen or supplier.expected_price_yen
    gross_profit = product.enoking_buy_price_yen - price if price else None
    buy_candidate = (
        price is not None
        and result.in_stock is True
        and supplier.shipping_included is True
        and supplier.condition_required == product.required_condition == "new"
        and gross_profit is not None
        and gross_profit >= BUY_MARGIN_THRESHOLD_YEN
    )
    reason = "BUY_CANDIDATE" if buy_candidate else "NOT_BUY_CANDIDATE"
    if price is None:
        reason = "NO_PRICE"
    elif result.in_stock is not True:
        reason = "NO_POSITIVE_STOCK_SIGNAL"
    elif gross_profit is not None and gross_profit < BUY_MARGIN_THRESHOLD_YEN:
        reason = "MARGIN_BELOW_THRESHOLD"
    return {
        "effective_price_yen": price,
        "gross_profit_yen": gross_profit,
        "is_buy_candidate": buy_candidate,
        "decision_reason": reason,
    }


def build_row(product: Product, supplier: Supplier, checked_at: str) -> dict[str, Any]:
    status_code, html, fetch_error = fetch(supplier.url)
    parsed = ParseResult(None, None, "", fetch_error) if fetch_error else parse_page(html, supplier)
    eval_result = evaluate(product, supplier, parsed)
    return {
        "checked_at_jst": checked_at,
        "jan": supplier.jan,
        "product_name": product.product_name,
        "supplier": supplier.supplier,
        "url": supplier.url,
        "http_status": status_code,
        "fetch_ok": not bool(fetch_error),
        "parser_hint": supplier.parser_hint,
        "parsed_price_yen": parsed.parsed_price_yen,
        "expected_price_yen": supplier.expected_price_yen,
        "effective_price_yen": eval_result["effective_price_yen"],
        "enoking_buy_price_yen": product.enoking_buy_price_yen,
        "gross_profit_yen": eval_result["gross_profit_yen"],
        "in_stock": parsed.in_stock,
        "shipping_included": supplier.shipping_included,
        "condition_required": supplier.condition_required,
        "is_buy_candidate": eval_result["is_buy_candidate"],
        "decision_reason": eval_result["decision_reason"],
        "raw_signals": parsed.raw_signals,
        "notes": "; ".join(part for part in [supplier.notes, parsed.notes] if part),
    }


def notify(candidates: list[dict[str, Any]]) -> None:
    if not candidates:
        return
    lines = ["Enoking monitor: buy candidates found"]
    for row in candidates[:10]:
        lines.append(
            f"- {row['product_name']} / {row['supplier']} / price={row['effective_price_yen']} / "
            f"profit={row['gross_profit_yen']} / {row['url']}"
        )
    body = "\n".join(lines)
    print(f"::notice::{body}")
    for env_name, payload_key in [("SLACK_WEBHOOK_URL", "text"), ("DISCORD_WEBHOOK_URL", "content")]:
        webhook = os.getenv(env_name)
        if webhook:
            try:
                requests.post(webhook, json={payload_key: body}, timeout=10)
            except requests.RequestException as exc:
                print(f"notification failed: {exc}", file=sys.stderr)


def autosize_worksheet(ws: Any) -> None:
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
    for column in ws.columns:
        col_letter = get_column_letter(column[0].column)
        max_len = max(len(str(cell.value or "")) for cell in column)
        ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 70)


def write_excel(rows: list[dict[str, Any]], summary: dict[str, Any], out_path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append(["metric", "value"])
    for key, value in summary.items():
        ws.append([key, value])
    autosize_worksheet(ws)

    fieldnames = list(rows[0].keys()) if rows else ["message"]
    result_sheets = {
        "Results": rows,
        "BuyCandidates": [row for row in rows if row.get("is_buy_candidate")],
        "DiscoveryOnly": [row for row in rows if row.get("decision_reason") == "DISCOVERY_ONLY_NO_BUY_DECISION"],
    }
    for sheet_name, sheet_rows in result_sheets.items():
        ws2 = wb.create_sheet(sheet_name)
        ws2.append(fieldnames)
        if sheet_rows:
            for row in sheet_rows:
                ws2.append([row.get(field) for field in fieldnames])
        elif sheet_name == "BuyCandidates":
            ws2.append(["NO_BUY_CANDIDATE"] + [None] * (len(fieldnames) - 1))
        autosize_worksheet(ws2)
    wb.save(out_path)


def write_outputs(rows: list[dict[str, Any]], summary: dict[str, Any], stamp: str) -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUTPUT_DIR / f"monitor_result_{stamp}.csv"
    out_xlsx = OUTPUT_DIR / f"monitor_result_{stamp}.xlsx"
    fieldnames = list(rows[0].keys()) if rows else ["message"]
    with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        if rows:
            writer.writerows(rows)
        else:
            writer.writerow({"message": "NO_ROWS"})
    write_excel(rows, summary, out_xlsx)
    latest_csv = OUTPUT_DIR / "latest.csv"
    latest_xlsx = OUTPUT_DIR / "latest.xlsx"
    shutil.copyfile(out_csv, latest_csv)
    shutil.copyfile(out_xlsx, latest_xlsx)
    return out_csv, out_xlsx


def main() -> int:
    now = datetime.now(JST)
    checked_at = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    stamp = now.strftime("%Y%m%d_%H%M%S")
    products = load_products()
    suppliers = [supplier for supplier in load_suppliers() if supplier.enabled]
    rows: list[dict[str, Any]] = []

    for idx, supplier in enumerate(suppliers):
        product = products.get(supplier.jan)
        if not product:
            print(f"Skipping unknown JAN: {supplier.jan}", file=sys.stderr)
            continue
        if idx > 0 and REQUEST_INTERVAL_SEC > 0:
            time.sleep(REQUEST_INTERVAL_SEC)
        rows.append(build_row(product, supplier, checked_at))

    candidates = [row for row in rows if row.get("is_buy_candidate")]
    summary: dict[str, Any] = {
        "checked_at_jst": checked_at,
        "checked": len(rows),
        "buy_candidates": len(candidates),
        "discovery_only": sum(1 for row in rows if row.get("decision_reason") == "DISCOVERY_ONLY_NO_BUY_DECISION"),
        "fetch_errors": sum(1 for row in rows if not row.get("fetch_ok")),
    }
    out_csv, out_xlsx = write_outputs(rows, summary, stamp)
    summary["output_csv"] = str(out_csv)
    summary["output_xlsx"] = str(out_xlsx)
    summary["latest_csv"] = str(OUTPUT_DIR / "latest.csv")
    summary["latest_xlsx"] = str(OUTPUT_DIR / "latest.xlsx")
    write_excel(rows, summary, out_xlsx)
    shutil.copyfile(out_xlsx, OUTPUT_DIR / "latest.xlsx")
    notify(candidates)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

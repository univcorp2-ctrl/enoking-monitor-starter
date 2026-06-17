"""Arbitrage engine: fetch buy-side pages, verify the product, compute the
real (実質) gap against the best sell destination, and rank candidates.

Pipeline per BuySource:
    fetch -> parse (price/stock, reuse monitor.py) -> JAN double-check
          -> effective cost (price - points + shipping)
          -> best sell destination net (買取/フリマ横断)
          -> gap = best_net - effective_cost
          -> buy candidate iff gap > 0 AND in stock AND new AND verified

"Any positive gap" is the threshold per the user's policy (c): points can flip a
marginal item into profit, so we keep the floor at >0 of the EFFECTIVE numbers.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import monitor  # noqa: E402  reuse fetch/parse/JST
from arb_models import (  # noqa: E402
    BuySource,
    Product,
    SellDest,
    best_sell_destination,
    load_buy_sources,
    load_products,
    load_sell_destinations,
)
from jan_verify import VerifyResult, verify  # noqa: E402

DISCOVERY_HINTS = monitor.DISCOVERY_HINTS


def _price_from(parsed_price: int | None, source: BuySource) -> int | None:
    return parsed_price if parsed_price is not None else source.list_price_yen


def evaluate_source(
    product: Product,
    source: BuySource,
    sell: SellDest | None,
    html: str,
    parsed: monitor.ParseResult,
) -> dict[str, Any]:
    is_discovery = source.parser_hint.lower() in DISCOVERY_HINTS
    vr: VerifyResult = verify(product, html, require=not is_discovery)

    price = _price_from(parsed.parsed_price_yen, source)
    eff_cost = source.effective_cost(price)
    sell_net = sell.net_yen if sell else None
    gap = (sell_net - eff_cost) if (sell_net is not None and eff_cost is not None) else None

    in_stock = parsed.in_stock
    new_ok = source.condition == product.required_condition == "new"

    if is_discovery:
        reason = "DISCOVERY_ONLY"
        is_candidate = False
    elif not vr.verified:
        reason = "UNVERIFIED_MATCH"
        is_candidate = False
    elif price is None:
        reason = "NO_PRICE"
        is_candidate = False
    elif sell_net is None:
        reason = "NO_SELL_DEST"
        is_candidate = False
    elif in_stock is not True:
        reason = "NO_STOCK"
        is_candidate = False
    elif not new_ok:
        reason = "CONDITION_MISMATCH"
        is_candidate = False
    elif gap is not None and gap > 0:
        reason = "BUY_CANDIDATE"
        is_candidate = True
    else:
        reason = "NO_POSITIVE_GAP"
        is_candidate = False

    return {
        "jan": product.jan,
        "product_name": product.product_name,
        "category": product.category,
        "buy_shop": source.shop,
        "buy_url": source.url,
        "parser_hint": source.parser_hint,
        "list_price_yen": price,
        "point_rate": source.point_rate,
        "point_value_yen": source.point_value(price) if price is not None else 0,
        "shipping_yen": source.shipping_yen,
        "effective_cost_yen": eff_cost,
        "in_stock": in_stock,
        "verified": vr.verified,
        "verify_method": vr.method,
        "verify_badge": vr.badge,
        "verify_detail": vr.detail,
        "sell_shop": sell.shop if sell else "",
        "sell_channel": sell.channel if sell else "",
        "sell_channel_label": sell.channel_label if sell else "",
        "sell_url": sell.url if sell else "",
        "sell_price_yen": sell.price_yen if sell else None,
        "sell_net_yen": sell_net,
        "gap_yen": gap,
        "is_buy_candidate": is_candidate,
        "decision_reason": reason,
        "raw_signals": parsed.raw_signals,
        "notes": "; ".join(p for p in [source.notes, parsed.notes] if p),
    }


def build_row(product: Product, source: BuySource, sell: SellDest | None) -> dict[str, Any]:
    is_discovery = source.parser_hint.lower() in DISCOVERY_HINTS
    timeout = 10 if is_discovery else monitor.REQUEST_TIMEOUT_SEC
    retries = 0 if is_discovery else monitor.MAX_FETCH_RETRIES
    status, html, fetch_error = monitor.fetch(source.url, timeout=timeout, retries=retries)
    if fetch_error:
        parsed = monitor.ParseResult(None, None, "", fetch_error)
        html = ""
    else:
        parsed = monitor.parse_page(html, _as_supplier(source))
    row = evaluate_source(product, source, sell, html, parsed)
    row["http_status"] = status
    row["fetch_ok"] = not bool(fetch_error)
    return row


def _as_supplier(source: BuySource) -> monitor.Supplier:
    """Adapt a BuySource to monitor.Supplier so we can reuse parse_page()."""
    return monitor.Supplier(
        jan=source.jan,
        supplier=source.shop,
        url=source.url,
        expected_price_yen=source.list_price_yen,
        shipping_included=(source.shipping_yen == 0),
        condition_required=source.condition,
        enabled=source.enabled,
        parser_hint=source.parser_hint,
        notes=source.notes,
    )


def collect_rows() -> list[dict[str, Any]]:
    now = datetime.now(monitor.JST)
    products = load_products()
    sell_dests = load_sell_destinations()
    sources = [s for s in load_buy_sources() if s.enabled]
    rows: list[dict[str, Any]] = []
    for idx, source in enumerate(sources):
        product = products.get(source.jan)
        if not product:
            print(f"skip unknown JAN: {source.jan}", file=sys.stderr)
            continue
        if idx > 0 and monitor.REQUEST_INTERVAL_SEC > 0:
            time.sleep(monitor.REQUEST_INTERVAL_SEC)
        sell = best_sell_destination(source.jan, sell_dests)
        row = build_row(product, source, sell)
        row["checked_at_jst"] = now.strftime("%Y-%m-%d %H:%M:%S %Z")
        rows.append(row)
    return rows


def best_row_per_product(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per JAN: prefer verified, then highest gap with a usable price."""
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("effective_cost_yen") is None or row.get("gap_yen") is None:
            continue
        cur = best.get(row["jan"])
        key = (1 if row.get("verified") else 0, row["gap_yen"])
        if cur is None or key > (1 if cur.get("verified") else 0, cur["gap_yen"]):
            best[row["jan"]] = row
    return sorted(
        best.values(),
        key=lambda r: (1 if r.get("verified") else 0, r["gap_yen"]),
        reverse=True,
    )

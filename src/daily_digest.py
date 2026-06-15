"""Daily Telegram digest for the Enoking resale monitor.

Unlike monitor.notify() (which only fires when a buy candidate exists), this
ALWAYS sends one Telegram message per run so the user gets a report every day,
even on days with zero buy candidates. It reuses monitor.py for fetching,
parsing and margin evaluation, then formats an HTML digest with hyperlinks for
both the 仕入れ先 (supplier) and 売り先 (buyback) and the explicit 価格差.

Run:  python src/daily_digest.py            (sends to Telegram)
      python src/daily_digest.py --dry-run  (prints, no send)
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import monitor  # noqa: E402  (local module, path injected above)

TOP_N = int(os.getenv("DIGEST_TOP_N", "8"))


def load_env(env_path: Path = ROOT / ".env") -> None:
    """Load KEY=VALUE pairs from .env into os.environ (no extra dependency)."""
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def link(label: str, url: str) -> str:
    if not url or not url.startswith(("http://", "https://")):
        return escape_html(label)
    return f'<a href="{escape_html(url)}">{escape_html(label)}</a>'


def yen(value: Any) -> str:
    return f"{value:,}円" if isinstance(value, int) else "—"


def gross_text(value: Any) -> str:
    if not isinstance(value, int):
        return "価格差 —"
    mark = "✅" if value >= monitor.BUY_MARGIN_THRESHOLD_YEN else ("➖" if value >= 0 else "❌")
    sign = "+" if value >= 0 else "−"
    return f"{mark} 価格差 {sign}{abs(value):,}円"


def collect_rows() -> list[dict[str, Any]]:
    now = datetime.now(monitor.JST)
    checked_at = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    products = monitor.load_products()
    suppliers = [s for s in monitor.load_suppliers() if s.enabled]
    rows: list[dict[str, Any]] = []
    for idx, supplier in enumerate(suppliers):
        product = products.get(supplier.jan)
        if not product:
            continue
        if idx > 0 and monitor.REQUEST_INTERVAL_SEC > 0:
            time.sleep(monitor.REQUEST_INTERVAL_SEC)
        rows.append(monitor.build_row(product, supplier, checked_at))
    return rows


def best_row_per_product(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per JAN: the highest 価格差 (gross profit) with a usable price."""
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("effective_price_yen") is None or row.get("gross_profit_yen") is None:
            continue
        current = best.get(row["jan"])
        if current is None or row["gross_profit_yen"] > current["gross_profit_yen"]:
            best[row["jan"]] = row
    return sorted(best.values(), key=lambda r: r["gross_profit_yen"], reverse=True)


def build_digest(rows: list[dict[str, Any]]) -> str:
    now = datetime.now(monitor.JST)
    candidates = [r for r in rows if r.get("is_buy_candidate")]
    restocks = monitor.detect_restocks(rows)
    ranked = best_row_per_product(rows)

    parts: list[str] = [f"📊 <b>転売デイリーダイジェスト</b>  {now.strftime('%Y-%m-%d (%a) %H:%M JST')}"]

    # --- Buy candidates (margin >= threshold, in stock, new, shipping incl.) ---
    if candidates:
        parts.append(f"🛒 <b>買い候補 {len(candidates)}件</b>（粗利≥{monitor.BUY_MARGIN_THRESHOLD_YEN:,}円）")
        for r in candidates[:TOP_N]:
            parts.append(
                f"📦 {escape_html(r['product_name'])}\n"
                f"  🏪 仕入: {link(r['supplier'], r['url'])}  💴 {yen(r['effective_price_yen'])}\n"
                f"  💰 売り先: {link(r.get('buyback_source') or 'エノキング', r.get('buyback_url', ''))} {yen(r['enoking_buy_price_yen'])}\n"
                f"  {gross_text(r['gross_profit_yen'])}"
            )
    else:
        parts.append("🛒 <b>本日の買い候補なし</b>（粗利が基準未満）。下に現在の価格差ランキングを掲載👇")

    # --- Restock alerts ---
    if restocks:
        parts.append(f"🔔 <b>入荷検知 {len(restocks)}件</b>（在庫切れ→在庫あり）")
        for r in restocks[:TOP_N]:
            parts.append(f"📦 {escape_html(r['product_name'])} — 🏪 {link(r['supplier'], r['url'])}")

    # --- Price-gap ranking (always shown, includes negatives) ---
    if ranked:
        parts.append("📈 <b>価格差ランキング（売り先買取 − 最安仕入れ）</b>")
        for r in ranked[:TOP_N]:
            stock = "在庫あり" if r.get("in_stock") is True else ("在庫なし" if r.get("in_stock") is False else "在庫不明")
            parts.append(
                f"・{escape_html(r['product_name'])}\n"
                f"  {gross_text(r['gross_profit_yen'])}｜{stock}\n"
                f"  🏪 仕入 {link(r['supplier'], r['url'])} {yen(r['effective_price_yen'])}"
                f" → 💰 売 {link(r.get('buyback_source') or 'エノキング', r.get('buyback_url', ''))} {yen(r['enoking_buy_price_yen'])}"
            )

    # --- Footer ---
    fetch_errors = sum(
        1 for r in rows
        if not r.get("fetch_ok") and r.get("parser_hint", "") not in monitor.DISCOVERY_HINTS
    )
    parts.append(
        f"———\n🔎 チェック {len(rows)}件 / 取得エラー {fetch_errors}件\n"
        f"※買取価格は設定値・要当日確認。仕入れ価格はJS描画/待機列で取得不可の場合あり"
    )
    return "\n\n".join(parts)


def send_telegram(html: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set", file=sys.stderr)
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": html,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=15,
        )
        data = resp.json()
        if not data.get("ok"):
            print(f"telegram error: {data.get('description')}", file=sys.stderr)
        return bool(data.get("ok"))
    except requests.RequestException as exc:
        print(f"telegram send failed: {exc}", file=sys.stderr)
        return False


def main() -> int:
    load_env()
    dry_run = "--dry-run" in sys.argv
    rows = collect_rows()
    digest = build_digest(rows)
    if dry_run:
        print(digest)
        return 0
    ok = send_telegram(digest)
    print("sent" if ok else "send failed")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(main())

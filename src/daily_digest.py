"""Daily Telegram digest for the expanded arbitrage monitor.

ALWAYS sends one Telegram message per run (even with zero buy candidates) so the
user gets a report every single day. It uses the arbitrage engine (arb_engine)
which:

  - fetches each 仕入れ先 (buy source) and parses price/stock,
  - DOUBLE-CHECKS the product identity via JAN/型番/名称 before trusting a row,
  - picks the best 売り先 (買取持込 or フリマ) per product by net proceeds,
  - computes the 実質 gap including ポイント還元 and フリマ手数料/送料.

The message shows, for every item, BOTH direct hyperlinks (仕入れ先 → 売り先)
and the price gap at a glance, with a verification badge (✅/🟡/⚠️).

Run:  python src/daily_digest.py            (sends to Telegram)
      python src/daily_digest.py --dry-run  (prints, no send)
"""
from __future__ import annotations

import html as html_lib
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import arb_engine  # noqa: E402
import monitor  # noqa: E402

TOP_N = int(os.getenv("DIGEST_TOP_N", "12"))


def load_env(env_path: Path = ROOT / ".env") -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def escape_html(text: str) -> str:
    return html_lib.escape(str(text), quote=True)


def link(label: str, url: str) -> str:
    if not url or not str(url).startswith(("http://", "https://")):
        return escape_html(label)
    return f'<a href="{escape_html(url)}">{escape_html(label)}</a>'


def yen(value: Any) -> str:
    return f"{value:,}円" if isinstance(value, int) else "—"


def gap_text(value: Any) -> str:
    if not isinstance(value, int):
        return "価格差 —"
    mark = "✅" if value > 0 else "❌"
    sign = "+" if value >= 0 else "−"
    return f"{mark} 価格差 {sign}{abs(value):,}円"


def buy_label(row: dict[str, Any]) -> str:
    """仕入れ先表示。ポイント還元があれば実質価格を併記。"""
    price = row.get("list_price_yen")
    eff = row.get("effective_cost_yen")
    pv = row.get("point_value_yen") or 0
    base = f"{link(row['buy_shop'], row['buy_url'])} {yen(price)}"
    if isinstance(eff, int) and isinstance(price, int) and pv > 0:
        base += f"（実質{eff:,}円/P{pv:,}）"
    return base


def sell_label(row: dict[str, Any]) -> str:
    ch = row.get("sell_channel_label") or "売"
    shop = row.get("sell_shop") or "—"
    net = row.get("sell_net_yen")
    price = row.get("sell_price_yen")
    base = f"{ch} {link(shop, row.get('sell_url', ''))} {yen(net)}"
    if isinstance(net, int) and isinstance(price, int) and net != price:
        base += f"（表示{price:,}/手数料引後）"
    return base


def stock_text(row: dict[str, Any]) -> str:
    v = row.get("in_stock")
    return "在庫あり" if v is True else ("在庫なし" if v is False else "在庫不明")


def build_digest(rows: list[dict[str, Any]]) -> str:
    now = datetime.now(monitor.JST)
    candidates = sorted(
        [r for r in rows if r.get("is_buy_candidate")],
        key=lambda r: r.get("gap_yen") or 0,
        reverse=True,
    )
    ranked = arb_engine.best_row_per_product(rows)

    parts: list[str] = [
        f"📊 <b>転売デイリーダイジェスト</b>  {now.strftime('%Y-%m-%d (%a) %H:%M JST')}"
    ]

    # --- Buy candidates: verified, in stock, any positive gap (incl. points) ---
    if candidates:
        parts.append(f"🛒 <b>買い候補 {len(candidates)}件</b>（実質差額プラス・JAN照合済）")
        for r in candidates[:TOP_N]:
            parts.append(
                f"{r.get('verify_badge', '')} <b>{escape_html(r['product_name'])}</b>\n"
                f"  🏪 仕入: {buy_label(r)}\n"
                f"  💰 {sell_label(r)}\n"
                f"  {gap_text(r.get('gap_yen'))}｜{stock_text(r)}"
            )
    else:
        parts.append("🛒 <b>本日の買い候補なし</b>（実質差額プラスが無し）。下に価格差ランキング👇")

    # --- Price-gap ranking (all items, incl. negatives, for visibility) ---
    if ranked:
        parts.append("📈 <b>価格差ランキング（最高値売り先 − 実質仕入れ）</b>")
        for r in ranked[:TOP_N]:
            parts.append(
                f"{r.get('verify_badge', '')} {escape_html(r['product_name'])}\n"
                f"  {gap_text(r.get('gap_yen'))}｜{stock_text(r)}\n"
                f"  🏪 {buy_label(r)}\n"
                f"  → 💰 {sell_label(r)}"
            )

    # --- Footer ---
    fetch_errors = sum(
        1 for r in rows
        if not r.get("fetch_ok") and r.get("parser_hint", "") not in monitor.DISCOVERY_HINTS
    )
    unverified = sum(1 for r in rows if not r.get("verified"))
    parts.append(
        "———\n"
        f"🔎 チェック {len(rows)}件 / 取得エラー {fetch_errors}件 / 未照合 {unverified}件\n"
        "✅JAN一致 🟡型番/名称一致 ⚠️未照合（買い候補は照合済のみ）\n"
        "※買取価格は設定値・要当日確認。ポイント還元・フリマ手数料は概算"
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
    rows = arb_engine.collect_rows()
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

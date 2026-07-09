"""Build a zero-cost static GitHub Pages dashboard."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"
PUBLIC_DIR = ROOT / "public"
JST = timezone(timedelta(hours=9), "JST")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def copy_if_exists(src: Path, dest: Path) -> None:
    if src.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def build_metadata(products: list[dict[str, Any]], opportunities: list[dict[str, Any]]) -> dict[str, Any]:
    verified = [row for row in opportunities if row.get("match_status") == "VERIFIED_EXACT_TRIPLE_CHECKED"]
    positive = [row for row in opportunities if isinstance(row.get("gross_gap_yen"), int) and row.get("gross_gap_yen") > 0]
    return {
        "generated_at_jst": datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "product_count": len(products),
        "opportunity_count": len(opportunities),
        "verified_exact_count": len(verified),
        "positive_gap_count": len(positive),
        "source_site": "https://newenoking-kaitori.com/",
        "mode": "GitHub Actions + GitHub Pages static dashboard",
    }


def index_html() -> str:
    return """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Enoking Cloud Monitor</title>
  <style>
    :root { color-scheme: light dark; --bg: #07111f; --panel: #101b2d; --panel2: #17243a; --text: #eef5ff; --muted: #9fb2cc; --accent: #62d2ff; --good: #49d17d; --warn: #ffca63; --bad: #ff7676; --border: #293a55; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: radial-gradient(circle at top left, #18365d 0, var(--bg) 42%); color: var(--text); }
    header { padding: 28px 18px 18px; max-width: 1280px; margin: auto; }
    h1 { margin: 0 0 8px; font-size: clamp(28px, 5vw, 48px); letter-spacing: .02em; }
    p { color: var(--muted); line-height: 1.7; }
    a { color: var(--accent); }
    main { max-width: 1280px; margin: auto; padding: 0 18px 48px; }
    .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin: 18px 0; }
    .card { background: linear-gradient(180deg, var(--panel), var(--panel2)); border: 1px solid var(--border); border-radius: 18px; padding: 16px; box-shadow: 0 16px 36px rgba(0,0,0,.25); }
    .card b { display: block; font-size: 28px; margin-top: 4px; }
    .toolbar { display: grid; grid-template-columns: 1fr repeat(3, minmax(130px, 180px)); gap: 10px; margin: 20px 0; }
    input, select { width: 100%; padding: 12px; border-radius: 12px; border: 1px solid var(--border); background: #091527; color: var(--text); }
    .panel { background: rgba(16,27,45,.86); border: 1px solid var(--border); border-radius: 18px; padding: 16px; margin-top: 18px; overflow: hidden; }
    .table-wrap { overflow: auto; max-height: 74vh; border-radius: 12px; border: 1px solid var(--border); }
    table { width: 100%; border-collapse: collapse; min-width: 1080px; background: rgba(7,17,31,.66); }
    th, td { padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
    th { position: sticky; top: 0; background: #13223a; z-index: 1; }
    tr:hover { background: rgba(98,210,255,.08); }
    .badge { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: 999px; font-size: 12px; border: 1px solid var(--border); white-space: nowrap; }
    .good { color: var(--good); border-color: rgba(73,209,125,.55); }
    .warn { color: var(--warn); border-color: rgba(255,202,99,.55); }
    .bad { color: var(--bad); border-color: rgba(255,118,118,.55); }
    .muted { color: var(--muted); }
    .links { display: flex; flex-wrap: wrap; gap: 6px; }
    .links a { border: 1px solid var(--border); padding: 4px 8px; border-radius: 999px; text-decoration: none; font-size: 12px; }
    .download-row { display: flex; flex-wrap: wrap; gap: 10px; margin: 10px 0 0; }
    .download-row a { background: #0a2740; border: 1px solid var(--border); padding: 8px 12px; border-radius: 10px; text-decoration: none; }
    @media (max-width: 760px) { .toolbar { grid-template-columns: 1fr; } table { min-width: 900px; } }
  </style>
</head>
<body>
  <header>
    <h1>Enoking Cloud Monitor</h1>
    <p>newenoking-kaitori.com の公開商品情報を毎日クラウドで取得し、JAN・買取価格・仕入れ候補・価格差・トリプルチェック状態を確認する低コスト静的ダッシュボードです。</p>
  </header>
  <main>
    <section class="cards" id="summaryCards"></section>
    <div class="download-row">
      <a href="data/products.json">products.json</a>
      <a href="downloads/latest_enoking_products.csv">products.csv</a>
      <a href="downloads/latest_enoking_products.xlsx">products.xlsx</a>
      <a href="data/opportunities.json">opportunities.json</a>
      <a href="downloads/latest_opportunities.csv">opportunities.csv</a>
      <a href="https://github.com/univcorp2-ctrl/enoking-monitor-starter/actions/workflows/enoking-cloud-site.yml">Actions</a>
    </div>

    <section class="panel">
      <h2>仕入れ先・価格差</h2>
      <p class="muted">APIキーなしでは検索リンクを生成します。<code>config/supplier_candidates.csv</code> や <code>RAKUTEN_APPLICATION_ID</code> を使うと、価格差とトリプルチェックが自動表示されます。</p>
      <div class="toolbar">
        <input id="q" placeholder="JAN・商品名・カテゴリ・仕入れ先で検索">
        <select id="gapFilter"><option value="all">全て</option><option value="positive">価格差プラスのみ</option><option value="verified">トリプルチェック済み</option><option value="needs">要確認のみ</option></select>
        <select id="categoryFilter"><option value="all">全カテゴリ</option></select>
        <select id="sort"><option value="gap_desc">価格差 大きい順</option><option value="buy_desc">買取価格 高い順</option><option value="name_asc">商品名順</option></select>
      </div>
      <div class="table-wrap"><table id="opTable"></table></div>
    </section>

    <section class="panel">
      <h2>取得済み Enoking 商品</h2>
      <div class="table-wrap"><table id="productTable"></table></div>
    </section>
  </main>
<script>
const yen = v => (v === null || v === undefined || v === '') ? '-' : new Intl.NumberFormat('ja-JP', { style: 'currency', currency: 'JPY', maximumFractionDigits: 0 }).format(v);
const esc = v => String(v ?? '').replace(/[&<>"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch]));
let products = [], opportunities = [], metadata = {};

function badge(row) {
  if (row.match_status === 'VERIFIED_EXACT_TRIPLE_CHECKED') return '<span class="badge good">✓ triple checked</span>';
  if (row.triple_check_done) return '<span class="badge warn">△ checked / review</span>';
  return '<span class="badge bad">manual check</span>';
}

function searchLinks(row) {
  const links = row.search_links || {};
  return '<div class="links">' + Object.entries(links).map(([label, url]) => `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(label)}</a>`).join('') + '</div>';
}

function renderSummary() {
  const cards = [
    ['商品数', metadata.product_count ?? products.length],
    ['仕入れ候補行', metadata.opportunity_count ?? opportunities.length],
    ['価格差プラス', metadata.positive_gap_count ?? 0],
    ['トリプルチェック済', metadata.verified_exact_count ?? 0],
    ['最終生成', metadata.generated_at_jst ?? '-']
  ];
  document.getElementById('summaryCards').innerHTML = cards.map(([k, v]) => `<div class="card"><span class="muted">${esc(k)}</span><b>${esc(v)}</b></div>`).join('');
}

function populateCategories() {
  const select = document.getElementById('categoryFilter');
  const cats = [...new Set(products.map(p => p.category).filter(Boolean))].sort();
  select.innerHTML = '<option value="all">全カテゴリ</option>' + cats.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
}

function filteredOpps() {
  const q = document.getElementById('q').value.toLowerCase();
  const gapFilter = document.getElementById('gapFilter').value;
  const cat = document.getElementById('categoryFilter').value;
  const sort = document.getElementById('sort').value;
  let rows = opportunities.filter(row => {
    const hay = [row.jan, row.product_name, row.category, row.supplier, row.supplier_product_name, row.match_status].join(' ').toLowerCase();
    if (q && !hay.includes(q)) return false;
    if (cat !== 'all' && row.category !== cat) return false;
    if (gapFilter === 'positive' && !(Number(row.gross_gap_yen) > 0)) return false;
    if (gapFilter === 'verified' && row.match_status !== 'VERIFIED_EXACT_TRIPLE_CHECKED') return false;
    if (gapFilter === 'needs' && row.match_status === 'VERIFIED_EXACT_TRIPLE_CHECKED') return false;
    return true;
  });
  rows.sort((a, b) => {
    if (sort === 'buy_desc') return Number(b.enoking_buy_price_yen || 0) - Number(a.enoking_buy_price_yen || 0);
    if (sort === 'name_asc') return String(a.product_name).localeCompare(String(b.product_name), 'ja');
    return Number(b.gross_gap_yen ?? -999999999) - Number(a.gross_gap_yen ?? -999999999);
  });
  return rows;
}

function renderOpportunities() {
  const rows = filteredOpps();
  document.getElementById('opTable').innerHTML = `
    <thead><tr><th>判定</th><th>JAN</th><th>商品</th><th>Enoking買取</th><th>仕入れ先</th><th>仕入れ値</th><th>価格差</th><th>チェック</th><th>検索リンク</th></tr></thead>
    <tbody>${rows.map(row => `
      <tr>
        <td>${badge(row)}<br><span class="muted">${esc(row.warning)}</span></td>
        <td>${esc(row.jan)}</td>
        <td><b>${esc(row.product_name)}</b><br><span class="muted">${esc(row.category)}</span></td>
        <td>${yen(row.enoking_buy_price_yen)}</td>
        <td>${row.supplier_url ? `<a href="${esc(row.supplier_url)}" target="_blank" rel="noopener">${esc(row.supplier)}</a>` : esc(row.supplier)}<br><span class="muted">${esc(row.supplier_product_name)}</span></td>
        <td>${yen(row.supplier_price_yen)}</td>
        <td><b class="${Number(row.gross_gap_yen) > 0 ? 'good' : 'muted'}">${yen(row.gross_gap_yen)}</b></td>
        <td><span class="badge ${row.jan_exact ? 'good' : 'warn'}">JAN ${row.jan_exact ? 'OK' : '未確認'}</span><br><span class="badge ${row.title_model_match ? 'good' : 'warn'}">名称/型番 ${row.title_model_match ? 'OK' : '要確認'}</span><br><span class="badge ${row.variant_safe ? 'good' : 'bad'}">色/容量 ${row.variant_safe ? 'OK' : '注意'}</span></td>
        <td>${searchLinks(row)}</td>
      </tr>`).join('')}</tbody>`;
}

function renderProducts() {
  const q = document.getElementById('q').value.toLowerCase();
  const rows = products.filter(p => !q || [p.jan, p.product_name, p.category, p.notes].join(' ').toLowerCase().includes(q));
  document.getElementById('productTable').innerHTML = `
    <thead><tr><th>JAN</th><th>商品</th><th>カテゴリ</th><th>参考買取金額</th><th>備考</th><th>取得元</th></tr></thead>
    <tbody>${rows.map(p => `<tr><td>${esc(p.jan)}</td><td><b>${esc(p.product_name)}</b></td><td>${esc(p.category)}</td><td>${yen(p.buy_price_yen)}</td><td>${esc(p.notes)}</td><td><a href="${esc(String(p.source_url).split(' | ')[0])}" target="_blank" rel="noopener">source</a></td></tr>`).join('')}</tbody>`;
}

async function init() {
  [products, opportunities, metadata] = await Promise.all([
    fetch('data/products.json').then(r => r.json()).catch(() => []),
    fetch('data/opportunities.json').then(r => r.json()).catch(() => []),
    fetch('data/metadata.json').then(r => r.json()).catch(() => ({}))
  ]);
  renderSummary(); populateCategories(); renderOpportunities(); renderProducts();
  ['q', 'gapFilter', 'categoryFilter', 'sort'].forEach(id => document.getElementById(id).addEventListener('input', () => { renderOpportunities(); renderProducts(); }));
}
init();
</script>
</body>
</html>
"""


def build_static_site(output_dir: Path = OUTPUT_DIR, public_dir: Path = PUBLIC_DIR) -> dict[str, Any]:
    products = read_json(output_dir / "latest_enoking_products.json", [])
    opportunities = read_json(output_dir / "latest_opportunities.json", [])
    metadata = build_metadata(products, opportunities)

    if public_dir.exists():
        shutil.rmtree(public_dir)
    (public_dir / "data").mkdir(parents=True, exist_ok=True)
    (public_dir / "downloads").mkdir(parents=True, exist_ok=True)

    (public_dir / "index.html").write_text(index_html(), encoding="utf-8")
    write_json(public_dir / "data" / "products.json", products)
    write_json(public_dir / "data" / "opportunities.json", opportunities)
    write_json(public_dir / "data" / "metadata.json", metadata)
    copy_if_exists(output_dir / "latest_enoking_products.csv", public_dir / "downloads" / "latest_enoking_products.csv")
    copy_if_exists(output_dir / "latest_enoking_products.xlsx", public_dir / "downloads" / "latest_enoking_products.xlsx")
    copy_if_exists(output_dir / "latest_opportunities.csv", public_dir / "downloads" / "latest_opportunities.csv")
    (public_dir / ".nojekyll").write_text("", encoding="utf-8")
    return metadata


def main() -> int:
    metadata = build_static_site()
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

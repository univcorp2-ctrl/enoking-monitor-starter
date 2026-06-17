"""Unit tests for the arbitrage engine: economics, JAN verification, best-sell."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from arb_models import (  # noqa: E402
    BuySource,
    Product,
    SellDest,
    best_sell_destination,
    normalize_jan,
    parse_rate,
)
from jan_verify import jan_in_text, verify  # noqa: E402


def test_normalize_jan_strips_separators():
    assert normalize_jan("4902370-553024") == "4902370553024"
    assert normalize_jan(" 4902370 553024 ") == "4902370553024"
    assert normalize_jan(None) == ""


def test_effective_cost_applies_points_and_shipping():
    src = BuySource(jan="x", shop="ヨドバシ", url="http://e", list_price_yen=37980, point_rate=0.10)
    # 37980 - round(37980*0.10) = 37980 - 3798 = 34182
    assert src.effective_cost() == 34182
    src2 = BuySource(jan="x", shop="s", url="http://e", list_price_yen=10000, shipping_yen=500)
    assert src2.effective_cost() == 10500
    assert BuySource(jan="x", shop="s", url="http://e", list_price_yen=None).effective_cost() is None


def test_sell_net_kaitori_vs_frima():
    kaitori = SellDest(jan="x", channel="kaitori", shop="エノキング", price_yen=50000)
    assert kaitori.net_yen == 50000
    frima = SellDest(jan="x", channel="frima", shop="メルカリ", price_yen=50000, fee_rate=0.10, shipping_yen=700)
    # round(50000*0.9) - 700 = 45000 - 700 = 44300
    assert frima.net_yen == 44300


def test_best_sell_destination_picks_max_net():
    dests = {
        "x": [
            SellDest(jan="x", channel="kaitori", shop="A", price_yen=48000),
            SellDest(jan="x", channel="frima", shop="メルカリ", price_yen=55000, fee_rate=0.10, shipping_yen=700),
            SellDest(jan="x", channel="kaitori", shop="B", price_yen=49000),
        ]
    }
    best = best_sell_destination("x", dests)
    # frima net = 49500 - 700 = 48800 > 49000? No: 48800 < 49000. So B(49000) wins.
    assert best.shop == "B"
    assert best.net_yen == 49000


def test_jan_in_text_tolerates_split_digits():
    assert jan_in_text("4902370553024", "型番 JAN: 4902370553024 在庫あり")
    assert jan_in_text("4902370553024", "コード 4902370 553024 です")
    assert jan_in_text("4902370553024", "JAN 4902370-553024 です")
    assert not jan_in_text("4902370553024", "全く別の商品 1234567890123")


def test_jan_not_matched_inside_longer_number():
    # Codex HIGH: must not match a JAN embedded in a longer digit run.
    assert not jan_in_text("4902370553024", "注文番号 904902370553024999")


def test_jan_not_matched_across_unrelated_concatenation():
    # Codex HIGH: scattered digits across the page must not concatenate to a hit.
    page = "価格4902370円 ポイント553024pt 在庫あり"
    assert not jan_in_text("4902370553024", page)


def test_parse_rate_accepts_percent_and_bare():
    assert parse_rate("0.10") == 0.10
    assert parse_rate("10%") == 0.10
    assert parse_rate("10") == 0.10  # bare percent typo
    assert parse_rate("") == 0.0


def test_verify_model_does_not_collapse_to_single_digit():
    # Codex CRITICAL: 'BEE-S-KB6CA' must not verify just because page has a '6'.
    p = Product(jan="4902370553024", product_name="無関係ドライヤー", model_no="BEE-S-KB6CA")
    r = verify(p, "<html>適当な家電 在庫6個 カートに入れる</html>")
    assert not r.verified


def test_choose_price_rejects_wild_parse():
    import arb_engine
    src = BuySource(jan="x", shop="Fujiya", url="http://e", list_price_yen=23100)
    # "10,000円以上送料無料" banner misparsed as 10000 -> rejected, use config.
    price, note = arb_engine.choose_price(10000, src)
    assert price == 23100 and "SUSPECT" in note
    # A plausible price (within tolerance) is kept.
    price2, note2 = arb_engine.choose_price(24000, src)
    assert price2 == 24000 and note2 == ""
    # No expected configured -> trust the parse.
    src2 = BuySource(jan="x", shop="s", url="http://e", list_price_yen=None)
    assert arb_engine.choose_price(5000, src2) == (5000, "")


def test_best_sell_skips_manual_only_and_condition_mismatch():
    dests = {
        "x": [
            SellDest(jan="x", channel="kaitori", shop="トップ", price_yen=99999, manual_only=True),
            SellDest(jan="x", channel="kaitori", shop="中古屋", price_yen=80000, condition="used"),
            SellDest(jan="x", channel="kaitori", shop="新品買取", price_yen=50000, condition="new"),
        ]
    }
    best = best_sell_destination("x", dests, required_condition="new")
    assert best is not None and best.shop == "新品買取" and best.net_yen == 50000


def test_verify_jan_match():
    p = Product(jan="4902370553024", product_name="Switch 2 本体", model_no="BEE-S-KB6CA")
    r = verify(p, "<html>JAN4902370553024 カートに入れる</html>")
    assert r.verified and r.method == "jan" and r.badge == "✅"


def test_verify_model_fallback():
    p = Product(jan="4902370553024", product_name="Switch 2 本体", model_no="BEE-S-KB6CA")
    r = verify(p, "<html>型番 BEE-S-KB6CA 在庫あり</html>")
    assert r.verified and r.method == "model" and r.badge == "🟡"


def test_verify_unverified_when_nothing_matches():
    p = Product(jan="4902370553024", product_name="Switch 2 本体 マリオカート", model_no="BEE-S-KB6CA")
    r = verify(p, "<html>全然違う家電 ドライヤー</html>")
    assert not r.verified and r.badge == "⚠️"

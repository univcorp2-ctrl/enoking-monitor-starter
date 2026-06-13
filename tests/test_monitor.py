from src.monitor import (
    Product,
    Supplier,
    detect_restocks,
    evaluate,
    parse_page,
    previous_in_stock,
    write_db,
)


def make_supplier(parser_hint: str, expected_price_yen=None) -> Supplier:
    return Supplier(
        jan="4902370548501",
        supplier="test",
        url="https://example.com",
        expected_price_yen=expected_price_yen,
        shipping_included=True,
        condition_required="new",
        enabled=True,
        parser_hint=parser_hint,
        notes="",
    )


def test_yahoo_price_and_out_of_stock():
    html = "価格 46,498 円 送料無料 在庫なし JAN/ISBNコード 4902370548501"
    result = parse_page(html, make_supplier("yahoo"))
    assert result.parsed_price_yen == 46498
    assert result.in_stock is False


def test_nojima_actual_price_and_sold_out():
    html = "発送目安： 完売御礼 価格： 参考価格： 47,980円 (税込) 37,980円 (税込) 送料無料"
    result = parse_page(html, make_supplier("nojima"))
    assert result.parsed_price_yen == 37980
    assert result.in_stock is False


def test_js_required_detection():
    html = "このサイトではJavaScriptを有効にする必要があります。"
    result = parse_page(html, make_supplier("nintendo_store"))
    assert result.parsed_price_yen is None
    assert result.in_stock is None
    assert "NEEDS_BROWSER" in result.notes


def test_search_discovery_never_extracts_price_or_stock():
    html = "検索結果 37,980円 カートに入れる 在庫あり"
    result = parse_page(html, make_supplier("search_discovery"))
    assert result.parsed_price_yen is None
    assert result.in_stock is None
    assert "DISCOVERY_ONLY" in result.notes


def test_search_discovery_never_becomes_buy_candidate_even_with_expected_price():
    product = Product("4902370548501", "Nintendo Switch OLED", 45300, "new")
    supplier = make_supplier("search_discovery", expected_price_yen=37980)
    result = parse_page("37,980円 カートに入れる 在庫あり", supplier)
    evaluated = evaluate(product, supplier, result)
    assert evaluated["is_buy_candidate"] is False
    assert evaluated["decision_reason"] == "DISCOVERY_ONLY_NO_BUY_DECISION"


def test_sony_store_out_of_stock_signal_detected():
    # ソニーストアの「入荷待ち」を在庫なしとして検知する
    result = parse_page("89,980円 税込 入荷待ち", make_supplier("generic"))
    assert result.parsed_price_yen == 89980
    assert result.in_stock is False


def test_stock_only_ignores_model_number_as_price():
    # 型番 CFIJ-10018 を価格と誤認しない。価格はconfigのexpected値に委ねる
    result = parse_page("PlayStation5 CFIJ-10018 ダブルパック 入荷待ち", make_supplier("stock_only"))
    assert result.parsed_price_yen is None
    assert result.in_stock is False


def test_stock_only_restock_uses_expected_price_for_margin():
    product = Product("4948872016940", "PS5 ダブルパック", 99500, "new")
    supplier = make_supplier("stock_only", expected_price_yen=89980)
    result = parse_page("CFIJ-10018 カートに入れる 在庫あり", supplier)
    evaluated = evaluate(product, supplier, result)
    assert evaluated["effective_price_yen"] == 89980
    assert evaluated["gross_profit_yen"] == 9520
    assert evaluated["is_buy_candidate"] is True


def _seed_row(jan: str, supplier: str, stamp: str, in_stock: bool):
    return {"checked_at_jst": stamp, "jan": jan, "supplier": supplier, "in_stock": in_stock}


def test_detect_restock_fires_on_out_to_in(tmp_path):
    db = tmp_path / "t.sqlite"
    write_db([_seed_row("J", "Sony", "t1", False)], db_path=db)
    assert previous_in_stock("J", "Sony", db_path=db) == 0
    rows = [
        {
            "jan": "J",
            "supplier": "Sony",
            "in_stock": True,
            "product_name": "PS5",
            "url": "https://example.com",
            "enoking_buy_price_yen": 99500,
            "buyback_source": "ルデヤ",
            "effective_price_yen": 89980,
            "gross_profit_yen": 9520,
        }
    ]
    events = detect_restocks(rows, db_path=db)
    assert len(events) == 1
    assert events[0]["supplier"] == "Sony"


def test_no_restock_when_previous_was_in_stock(tmp_path):
    db = tmp_path / "t.sqlite"
    write_db([_seed_row("J", "Sony", "t1", True)], db_path=db)
    rows = [{"jan": "J", "supplier": "Sony", "in_stock": True}]
    assert detect_restocks(rows, db_path=db) == []


def test_no_restock_on_first_ever_observation(tmp_path):
    db = tmp_path / "missing.sqlite"
    rows = [{"jan": "J", "supplier": "Sony", "in_stock": True}]
    assert detect_restocks(rows, db_path=db) == []

from src.monitor import Product, Supplier, evaluate, parse_page


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

from src.monitor import Supplier, parse_page


def make_supplier(parser_hint: str) -> Supplier:
    return Supplier(
        jan="4902370548501",
        supplier="test",
        url="https://example.com",
        expected_price_yen=None,
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

from src.monitor import (
    Supplier,
    parse_page,
    parse_rakuten_api,
    parse_yahoo_api,
    select_best_item,
)


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


def test_parse_rakuten_api_flat_format():
    payload = {
        "Items": [
            {
                "itemName": "Nintendo Switch 有機EL ネオン 新品",
                "itemPrice": 38000,
                "itemUrl": "https://item.rakuten.co.jp/shopa/x/",
                "shopName": "shopA",
                "availability": 1,
                "postageFlag": 0,
            },
            {
                "itemName": "Nintendo Switch 有機EL 中古",
                "itemPrice": 30000,
                "itemUrl": "https://item.rakuten.co.jp/shopb/y/",
                "shopName": "shopB",
                "availability": 1,
                "postageFlag": 1,
            },
        ]
    }
    items = parse_rakuten_api(payload)
    assert len(items) == 2
    assert items[0].shipping_included is True
    best = select_best_item(items)
    # The used cheaper item is filtered out; the new in-stock item wins.
    assert best.price_yen == 38000
    assert best.shop == "shopA"


def test_parse_yahoo_api_filters_used_and_picks_cheapest():
    payload = {
        "hits": [
            {
                "name": "Switch 有機EL ネオン",
                "price": 39000,
                "url": "https://store.shopping.yahoo.co.jp/shopa/x",
                "seller": {"name": "shopA"},
                "inStock": True,
                "condition": "new",
                "shipping": {"code": 3},
            },
            {
                "name": "Switch 有機EL 中古",
                "price": 28000,
                "url": "https://store.shopping.yahoo.co.jp/shopb/y",
                "seller": {"name": "shopB"},
                "inStock": True,
                "condition": "used",
                "shipping": {"code": 1},
            },
        ]
    }
    items = parse_yahoo_api(payload)
    assert len(items) == 1  # used item dropped
    best = select_best_item(items)
    assert best.price_yen == 39000
    assert best.shipping_included is True


def test_select_best_item_prefers_in_stock():
    payload = {
        "Items": [
            {"itemName": "A", "itemPrice": 30000, "itemUrl": "u1", "shopName": "s1",
             "availability": 0, "postageFlag": 0},
            {"itemName": "B", "itemPrice": 35000, "itemUrl": "u2", "shopName": "s2",
             "availability": 1, "postageFlag": 0},
        ]
    }
    best = select_best_item(parse_rakuten_api(payload))
    assert best.price_yen == 35000

from src.enoking_scraper import extract_category_links, parse_products_from_html


SAMPLE_HTML = """
<html><body>
<a href="/products?cat=abc">任天堂</a>
<article>
  <span>☆</span><p>任天堂</p>
  <h2>Nintendo Switch 有機ELモデル ホワイト</h2>
  <p>JAN: 4902370548495</p>
  <p>参考買取金額</p><p>¥45,500</p>
  <p>店舗ごとの買取金額を見る 現金買取可能</p>
  <p>翌日午前着必須</p>
  <p>商品数</p>
</article>
<article>
  <span>☆</span><p>iPhone17 ProMax</p>
  <h2>iPhone 17 ProMax 256GB シルバー</h2>
  <p>JAN: 4549995649284</p>
  <p>参考買取金額</p><p>¥193,000</p>
  <p>現金買取可能</p><p>商品数</p>
</article>
</body></html>
"""


def test_parse_products_from_html_extracts_jan_price_category_and_notes():
    products = parse_products_from_html(SAMPLE_HTML, "https://newenoking-kaitori.com/featured")
    assert len(products) == 2
    first = products[0]
    assert first.jan == "4902370548495"
    assert first.product_name == "Nintendo Switch 有機ELモデル ホワイト"
    assert first.category == "任天堂"
    assert first.buy_price_yen == 45500
    assert first.cash_purchase_available is True
    assert "翌日午前着必須" in first.notes


def test_extract_category_links_dedupes_product_category_urls():
    links = extract_category_links(SAMPLE_HTML, "https://newenoking-kaitori.com")
    assert [(link.name, link.url) for link in links] == [
        ("任天堂", "https://newenoking-kaitori.com/products?cat=abc")
    ]

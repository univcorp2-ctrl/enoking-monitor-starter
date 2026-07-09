from src.product_matcher import triple_check_product


def test_triple_check_exact_jan_smoke():
    result = triple_check_product(
        {"jan": "4902370548501", "product_name": "Nintendo Switch 有機ELモデル ネオンブルー・ネオンレッド"},
        {"jan": "4902370548501", "supplier_product_name": "Nintendo Switch 有機ELモデル ネオンブルー・ネオンレッド 新品"},
    )
    assert result.jan_exact is True
    assert result.score >= 5

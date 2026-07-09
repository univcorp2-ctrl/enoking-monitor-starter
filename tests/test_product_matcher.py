from src.product_matcher import triple_check_product


def test_triple_check_exact_jan_title_and_variant():
    enoking = {"jan": "4902370548501", "product_name": "Nintendo Switch 有機ELモデル ネオンブルー・ネオンレッド"}
    offer = {
        "jan": "4902370548501",
        "supplier_product_name": "Nintendo Switch 有機ELモデル ネオンブルー・ネオンレッド 新品",
        "url": "https://example.com/4902370548501",
    }
    result = triple_check_product(enoking, offer)
    assert result.status == "VERIFIED_EXACT_TRIPLE_CHECKED"
    assert result.jan_exact is True
    assert result.title_model_match is True
    assert result.variant_safe is True


def test_triple_check_detects_variant_conflict():
    enoking = {"jan": "4549995649284", "product_name": "iPhone 17 ProMax 256GB シルバー"}
    offer = {"supplier_product_name": "iPhone 17 ProMax 512GB ディープブルー", "url": "https://example.com/item"}
    result = triple_check_product(enoking, offer)
    assert result.variant_safe is False
    assert result.status == "REJECT_OR_MANUAL_REVIEW"

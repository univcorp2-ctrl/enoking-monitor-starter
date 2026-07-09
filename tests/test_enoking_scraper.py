from src.enoking_scraper import extract_jan, parse_yen, normalize_space


def test_enoking_scraper_helpers_are_stable():
    assert parse_yen("¥193,000") == 193000
    assert extract_jan("JAN: 4902370548501") == "4902370548501"
    assert normalize_space("Nintendo\u3000 Switch  ") == "Nintendo Switch"

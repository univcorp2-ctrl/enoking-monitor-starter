import json
from pathlib import Path

from src.site_builder import build_static_site


def test_build_static_site_writes_index_and_data(tmp_path: Path):
    output = tmp_path / "output"
    public = tmp_path / "public"
    output.mkdir()
    (output / "latest_enoking_products.json").write_text(
        json.dumps([
            {
                "jan": "4902370548501",
                "product_name": "Nintendo Switch 有機ELモデル ネオンブルー・ネオンレッド",
                "category": "任天堂",
                "buy_price_yen": 48700,
            }
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    (output / "latest_opportunities.json").write_text("[]", encoding="utf-8")
    metadata = build_static_site(output, public)
    assert metadata["product_count"] == 1
    assert (public / "index.html").exists()
    assert (public / "data" / "products.json").exists()

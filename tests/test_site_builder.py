import json

from src.site_builder import build_static_site


def test_build_static_site_smoke(tmp_path):
    output = tmp_path / "output"
    public = tmp_path / "public"
    output.mkdir()
    (output / "latest_enoking_products.json").write_text(json.dumps([], ensure_ascii=False), encoding="utf-8")
    (output / "latest_opportunities.json").write_text(json.dumps([], ensure_ascii=False), encoding="utf-8")
    metadata = build_static_site(output, public)
    assert metadata["product_count"] == 0
    assert (public / "index.html").exists()

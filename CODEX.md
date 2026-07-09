# CODEX.md

## 開発方針

このリポジトリは、公開されている買取商品情報を低頻度で取得し、仕入れ候補の確認を補助するためのクラウド実行・静的Webダッシュボードです。

## 禁止事項

- ログイン突破、CAPTCHA回避、待合室回避、アクセス制御回避
- カート追加、購入、買取申請、決済などの自動化
- APIキーやSecretのログ出力
- 高頻度アクセスやDoSにつながる実装

## 主要コマンド

```bash
pip install -r requirements-dev.txt
pytest -q
ruff check src tests
python -m src.run_cloud_pipeline
```

## 主要ファイル

- `src/enoking_scraper.py`: Enoking公開商品ページの取得と正規化
- `src/supplier_discovery.py`: 仕入れ候補検索リンク/API/CSV候補の統合
- `src/product_matcher.py`: JAN・名称/型番・バリエーションのトリプルチェック
- `src/site_builder.py`: GitHub Pages用静的サイト生成
- `.github/workflows/enoking-cloud-site.yml`: 毎日自動取得とPages公開

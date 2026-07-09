# 初期設定ガイド

## まず見る本番URL

GitHub PagesのURLは次です。

`https://univcorp2-ctrl.github.io/enoking-monitor-starter/`

初回のActions実行とPagesデプロイが完了すると、このURLでダッシュボードを確認できます。

## 低コスト構成

- サーバー不要
- DB不要
- 毎日実行はGitHub Actionsの無料枠
- 表示はGitHub Pages
- 成果物はActions ArtifactsとPages配下のCSV/JSON/XLSX

## 手動実行

GitHubのリポジトリで次を開きます。

`Actions` → `Enoking cloud scrape and Pages` → `Run workflow`

## 毎日自動実行

`.github/workflows/enoking-cloud-site.yml` が毎日 07:10 JST に実行します。

## 仕入れ先候補を自分で追加する場合

`config/supplier_candidates.csv` に次の形式で追加します。

```csv
jan,supplier,supplier_product_name,url,supplier_price_yen,stock_status,condition,image_url
4902370548501,Example Store,Nintendo Switch 有機ELモデル ネオンブルー・ネオンレッド,https://example.com/item/4902370548501,44800,in_stock,new,
```

追加後、Actionsが走るとWeb画面に価格差とトリプルチェック結果が表示されます。

## 楽天APIを使う場合

Repository Secretに `RAKUTEN_APPLICATION_ID` を追加します。実値はREADME、Issue、ログには貼らないでください。

## 出力ファイル

- `output/latest_enoking_products.csv`
- `output/latest_enoking_products.json`
- `output/latest_enoking_products.xlsx`
- `output/latest_opportunities.csv`
- `output/latest_opportunities.json`
- GitHub Pages `public/data/*.json`
- GitHub Pages `public/downloads/*.csv`, `*.xlsx`

## 注意

この仕組みは商品情報・価格差候補の確認までです。購入、カート投入、ログイン、申請、CAPTCHA回避、待合室回避などは実装していません。仕入れ前には必ず仕入れ先ページでJAN、型番、色、容量、状態、送料、在庫、キャンセル条件を目視確認してください。

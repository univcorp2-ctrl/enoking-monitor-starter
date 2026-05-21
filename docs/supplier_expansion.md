# 仕入れ先拡張メモ

## 方針

1. APIで取得できる仕入れ先を最優先にする。
2. APIがない、または会員・JavaScript・待機列があるサイトは `search_discovery` / `manual_check` として扱い、買い判定には使わない。
3. 自動購入、ログイン、CAPTCHA回避、待機列回避、カート投入は実装しない。
4. HTML取得は低頻度にし、`REQUEST_INTERVAL_SEC` を使って連続アクセスを避ける。

## 追加済みのAPI優先候補

| supplier | parser_hint | 必要なSecret | 役割 |
| --- | --- | --- | --- |
| Rakuten Ichiba API | `rakuten_api` | `RAKUTEN_APPLICATION_ID` | JAN/キーワードで楽天市場の商品を取得し、最安の新品候補を評価する |
| Yahoo Shopping API | `yahoo_api` | `YAHOO_CLIENT_ID` | JANコードでYahoo!ショッピングの商品を取得し、最安候補を評価する |
| Amazon JP PA-API Candidate | `amazon_api_candidate` | 未実装 | PA-APIの認証・Associate条件が必要なためデフォルト無効 |

## GitHub Actions Secrets

Repository Settings → Secrets and variables → Actions → New repository secret で以下を設定する。

- `RAKUTEN_APPLICATION_ID`
- `YAHOO_CLIENT_ID`
- 任意: `SLACK_WEBHOOK_URL`
- 任意: `DISCORD_WEBHOOK_URL`

Secret未設定の場合、API行は失敗扱いではなく `API_SKIPPED` としてCSVに記録する。

## 追加した低負荷Discovery候補

以下は価格・在庫の自動買い判定には使わず、該当ページの発見・シグナル確認用として追加した。

- BOOKOFF Online: 中古混在に注意。新品のみ手動確認。
- 駿河屋: 新品/中古混在に注意。買い判定には使わない。
- DMM Games: ゲーム系ECの該当確認用。
- HMV & BOOKS: ゲーム/周辺商材の該当確認用。

## Claude開発時の引き継ぎポイント

- `config/supplier_urls.csv` に行を追加すれば監視先を増やせる。
- 買い判定に使ってよいのは、価格・在庫・新品・送料込みが十分に判定できる行だけ。
- API候補は `api://...` 形式にし、`src/monitor.py` の `fetch_api_supplier` と `parse_api_response` にアダプタを追加する。
- HTML取得しかできないサイトは `search_discovery` に留める。
- 個別商品URLの専用パーサーを作る場合は、誤検知を避けるため最初は `expected_price_yen` を空にし、CSV出力のシグナル確認後に有効化する。

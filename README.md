# Enoking 仕入れ監視スターター

エノキング買取価格と仕入れ先URLの価格・在庫シグナルを突合し、粗利が一定以上ある候補をCSV出力するスターターです。

## 対象商品

| JAN | 商品 | エノキング買取 | 主な監視先 |
|---:|---|---:|---|
| 4902370552683 | Nintendo Switch 2 多言語版 BEE-S-KB6AA | 76,500円 | My Nintendo Store / Yahoo!ショッピング / 楽天 |
| 4902370548501 | Nintendo Switch 有機ELモデル ネオン | 45,300円 | ヨドバシ / ノジマ / TSUTAYA / Yahoo! / イオン |

## 買い候補条件

```text
エノキング買取価格 - 仕入れ価格 >= 2,000円
かつ新品
かつ在庫あり
かつ送料込み
かつ注文キャンセルリスクが低い店舗
```

このリポジトリの初期実装では、価格と在庫文言から一次判定します。数量制限、会員ランク、キャンセルリスクは `notes` と手動確認で補完する想定です。

## ローカル実行

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python src/monitor.py
```

結果は `output/monitor_result_YYYYMMDD_HHMMSS.csv` に出力されます。

## GitHub Actionsで毎日監視

`.github/workflows/daily-monitor.yml` により、毎日 09:30 JST に監視を実行します。

- 実行結果CSVはGitHub ActionsのArtifactsに保存されます。
- `SLACK_WEBHOOK_URL` または `DISCORD_WEBHOOK_URL` をRepository Secretsに設定すると、買い候補が出た時だけ通知します。
- 手動実行は GitHub Actions の `Daily supplier monitor` から `Run workflow` を押します。

## 注意

- 自動購入はしません。価格・在庫候補の検知までです。
- My Nintendo StoreやTSUTAYAなどJavaScript必須ページは、`requests` だけでは取得できない場合があります。その場合は `NEEDS_BROWSER` として記録します。
- 利用規約、アクセス頻度、robots.txt、会員条件、購入制限を守ってください。
- 価格・在庫は変動するため、購入前に必ず公式ページで確認してください。

## ディレクトリ

```text
config/
  products_sample.csv      # JAN・商品名・エノキング買取価格
  supplier_urls.csv        # 監視URL・想定価格・パーサーヒント
src/
  monitor.py               # 監視本体
output/                    # 実行結果CSV出力先
.github/workflows/
  daily-monitor.yml        # 毎日実行
```

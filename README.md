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

## GitHub Actionsで監視（高頻度）

`.github/workflows/daily-monitor.yml` により、**30分ごと**に監視を実行します（実質ニアリアルタイム）。間隔は `cron` で調整できます。

- 実行結果CSVはGitHub ActionsのArtifactsに保存されます。
- 楽天・Yahoo!ショッピングのAPI IDはワークフローに既定値が埋め込まれているため、追加設定なしでAPI監視が動きます。
- 別のIDに切り替えたい場合は `RAKUTEN_APP_ID` / `RAKUTEN_ACCESS_KEY` / `YAHOO_APP_ID` をRepository Secretsに登録すると既定値を上書きします。
- `SLACK_WEBHOOK_URL` または `DISCORD_WEBHOOK_URL` をRepository Secretsに設定すると、買い候補が出た時だけ通知します。同じ出品の連投は `actions/cache` に保存した状態で抑制し、新規出現・値下がり時のみ通知します。
- Secretsは `Settings → Secrets and variables → Actions → New repository secret` から登録します。
- 手動実行は GitHub Actions の `Supplier monitor` から `Run workflow` を押します。
- 注意: プライベートリポジトリではActions無料枠を消費します。頻度はコストと相談して調整してください。

## 監視の仕組み

監視は2系統です。

1. **マーケットプレイスAPIスキャン（安定・推奨）** — 楽天市場・Yahoo!ショッピングの商品検索APIでJANを横断検索し、各マーケットプレイス全店（数千店舗）から最安の候補を取得します。新品・在庫あり・送料込みで突合し、上位の出品を採用します。中古・新古品は除外します。
2. **直販ECスクレイピング（補助）** — My Nintendo Store等、APIの無いサイトをHTMLから一次判定します。ヨドバシ・ノジマ・イオン等はWAFにより `requests` ではブロック（403/503）されることが多く、その場合は取得失敗として記録します。本格対応はPlaywright（ブラウザ）化が必要です。

| 環境変数 / Secret | API | 取得元 |
|---|---|---|
| `RAKUTEN_APP_ID` | 楽天市場 商品検索API | Rakuten Developers の Application ID |
| `RAKUTEN_ACCESS_KEY` | 楽天市場 商品検索API | Rakuten Developers の Access Key（UUID形式IDのみ必須） |
| `YAHOO_APP_ID` | Yahoo!ショッピング 商品検索API V3 | Yahoo!デベロッパー の Client ID |

APIの最安候補は、実際の出品ページを取得してJANコード一致と在庫表記を確認してから採用します。確認できないものは「要手動確認」として買い候補から除外します。

ローカルで使う場合は環境変数を設定してから実行します。

```bash
export RAKUTEN_APP_ID="..."
export RAKUTEN_ACCESS_KEY="..."
export YAHOO_APP_ID="..."
python src/monitor.py
```

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

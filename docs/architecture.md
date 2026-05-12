# 仕入れ監視アーキテクチャ案

## 結論

2商品・数URLの毎日監視は実現可能です。ただし、全URLを単純な `requests` だけで完全自動監視するのは難しく、以下の3レイヤーに分けるのが現実的です。

1. 静的HTMLで取得できるページ: `requests` + 正規表現で価格・在庫文言を抽出
2. JavaScript必須ページ: まず `NEEDS_BROWSER` として検知し、必要ならPlaywrightへ拡張
3. 店舗在庫・ログイン/会員条件ページ: 自動判定は補助情報まで。最終購入判断は手動確認

## 初期構成

```text
GitHub Actions cron
  ↓ daily 09:30 JST
src/monitor.py
  ↓
config/products_sample.csv      # 買取価格
config/supplier_urls.csv        # 監視URL
  ↓
output/monitor_result_*.csv
  ↓
Artifacts / Slack / Discord optional
```

## 監視ロジック

1. 商品CSVからJAN・商品名・買取価格を読む
2. 仕入れURL CSVから監視対象を読む
3. 各URLを低頻度で取得する
4. サイト別パーサーで価格・在庫シグナルを抽出する
5. `買取価格 - 仕入れ価格 >= 2,000円` を満たし、在庫あり・新品・送料込みなら買い候補にする
6. CSV出力し、候補があれば通知する

## サイト別の難易度

| 監視先 | 難易度 | 理由 | 初期対応 |
|---|---:|---|---|
| Yahoo!ショッピング | 低〜中 | HTMLに価格・在庫なし・カート文言が出やすい | `yahoo` パーサー |
| ノジマオンライン | 低〜中 | HTMLに価格・完売御礼が出る場合がある | `nojima` パーサー |
| イオンスタイル | 低〜中 | HTMLに価格・購入不可文言が出る場合がある | `aeon` パーサー |
| ヨドバシ.com | 中 | 取得制限やHTML差分が出やすい | `yodobashi` パーサー + 手動確認 |
| My Nintendo Store | 高 | JavaScript/待機列/アクセス制御がある | `NEEDS_BROWSER` 判定 |
| TSUTAYA店舗在庫 | 高 | JavaScriptと地域入力が必要 | `NEEDS_BROWSER` 判定、将来Playwright化 |
| 楽天 | 中 | 店舗によりHTML構造が違う | 汎用価格抽出から開始 |

## 拡張案

### Phase 1: 現在のスターター

- GitHub Actionsで毎日実行
- CSV artifact保存
- Slack/Discord通知は任意
- 自動購入なし

### Phase 2: ブラウザ監視

My Nintendo StoreやTSUTAYAを本気で監視する場合は、Playwrightを追加します。

```text
Playwright Chromium
  - JSレンダリング
  - スクリーンショット保存
  - 価格/在庫テキスト抽出
  - CAPTCHA/ログイン/待機列は突破しない
```

### Phase 3: データ蓄積

毎日の結果を蓄積するなら、次のどちらかにします。

- GitHub Actions artifact: 初期運用向き
- SQLite/Supabase/Google Sheets: 価格推移・通知履歴を見たい場合

### Phase 4: 通知強化

- Slack/Discord/LINE Notify代替Webhook
- 買い候補のみ通知
- 同じURLの重複通知抑制
- 粗利、在庫変化、価格下落率で優先度付け

## 運用上の注意

- アクセス頻度は1日1回〜数回程度に抑える
- 自動購入、ログイン突破、CAPTCHA突破、待機列回避はしない
- 店舗の購入制限、会員条件、キャンセルポリシーは必ず購入前に確認する
- ポイント還元は実質利益に入れすぎない。付与上限や期間限定ポイントを別管理にする

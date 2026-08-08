# QTrader

<p align="center">
  <img src="docs/qtrader-banner.svg" alt="QTrader Banner" width="100%">
</p>

**[简体中文](README.zh-CN.md)** | **[English](README.en.md)** | **[Français](README.fr.md)** | **[Deutsch](README.de.md)** | **[Español](README.es.md)** | **[日本語](README.ja.md)** | **[한국어](README.ko.md)**

---

## はじめに

[Qlib](https://github.com/microsoft/qlib) エコシステム上に構築されたフルスタックのクォンツ・トレーディング・プラットフォームです。複数のデータソース、AIモデルのトレーニング＆バックテスト、シミュレーション/ライブトレード、リアルタイムのリスク管理を備えています。

### 機能

- **複数データソース**: AKShare / Qlib の統合抽象化、実行時のホットスイッチ、SQLite インクリメンタルキャッシュ
- **分足データ**: 1/5/15/30/60分足Kラインの同期と照会、APScheduler による終値後の自動同期
- **AIトレーニングエンジン**: Qlib エコシステムに接続 — 15モデル対応（LightGBM / XGBoost / CatBoost / Linear / GRU / LSTM / ALSTM / Transformer / TCN / TabNet / DNN / GATs / SFM / DoubleEnsemble / **HFLGBModel**）
- **高頻度モデル**: HFLGBModel + HighFreqHandler、1分データでトレーニング、ポジションバッファリング実行（REBALANCE_INTERVAL=5, BUFFER_ZONE=2）
- **トレーニングダッシュボード**: 6次元のシグナル分析チャート（Loss / RankIC / RankICIR / Long-Short NAV / 十分位リターン / 回転率）+ HF専用メトリクス（回転率あたりリターン / コスト分解 / シグナル半減期 / キャパシティ曲線）
- **ポートフォリオバックテスト**: TopkDropoutStrategy（topk=30, n_drop=3）+ VWAP約定 + 実回転率 + 年率リターン/シャープレシオ/最大ドローダウン/IR
- **個別銘柄予測**: トレーニング済みモデルをロードし、予測スコア + 強気/弱気シグナル + 強度を生成（HFモデルを自動的に分足パスへルーティング）
- **モデルバージョニング**: トレーニング済みモデルを自動永続化、バージョン番号を増分し、ジョブ単位で照会・ダウンロード可能
- **モデル星評価**: トレーニング済みモデルに1〜5星の評価を付け、最適モデル選択を容易に
- **バックテストエンジン**: TopkDropout戦略 + 評価器（シャープレシオ、最大ドローダウン、Calmar、IR）+ Plotlyチャート + マルチ戦略比較
- **トレードモジュール**: SimBroker インメモリ照合（T+1）+ EastMoney jvQuant API 統合
- **リスク管理**: 注文ごとの上限 / 日次トレード上限 / ポジション比率 / ストップ高フィルター / 日次損失サーキットブレーカー
- **戦略エンジン**: シグナル → リスクフィルター → 注文実行、スケジュールリバランス + 実行ログ
- **ジョブ永続化**: トレーニング/バックテストジョブを SQLite（デフォルト）または PostgreSQL に保存
- **リアルタイム進捗**: トレーニング進捗率 + ログタイムライン + WebSocket プッシュ
- **ローカルKライン読み取り**: ネットワークリクエストなしで Qlib .bin ファイルを直接読み取り、hfq/raw切替対応
- **同期チェックポイント**: 中断後の正確な再開、重複取得を回避
- **サービス管理**: `qtrader.sh` ワンコマンドスクリプト（start / stop / restart / status / logs）

### 技術スタック

| 層 | 技術 |
|---|---|
| バックエンド | FastAPI + Pydantic v2 + Uvicorn |
| フロントエンド | React 18 + TypeScript + Vite 6 + Ant Design 5 + Zustand |
| 可視化 | Plotly + Lightweight Charts |
| AI/ML | Qlib + LightGBM + XGBoost + CatBoost + PyTorch (GRU/LSTM/Transformer/TCN/GATs) |
| ストレージ | SQLite / PostgreSQL（ジョブ）+ ファイルシステム（モデル） |

### クイックスタート

**要件**: Python 3.10+ / Node.js 18+ / Qlib データ（`~/.qlib/qlib_data/cn_data`）

```bash
git clone https://github.com/shark8848/sharkyai-qtrader.git
cd sharkyai-qtrader

pip install -r requirements.txt

cd frontend && npm install && cd ..

./qtrader.sh start
```

| サービス | URL |
|---|---|
| フロントエンド | http://localhost:5173 |
| バックエンド API | http://localhost:8000 |
| API ドキュメント | http://localhost:8000/docs |

カスタムポート: `QTRADER_PORT=9000 QTRADER_FE_PORT=3000 ./qtrader.sh start`

### API 概要

**データ管理** `/api/data`
- `GET /sources` — 利用可能なデータソースの一覧
- `POST /switch` — アクティブなデータソースの切り替え
- `GET /stocks` — 銘柄リストの取得
- `GET /kline` — Kライン・データの取得
- `POST /sync_minute` — 分足Kライン・データの同期
- `GET /sync_minute/status` — 分足同期の進捗
- `GET /minute/calendar` — 分足データのある日付
- `GET /minute/{symbol}` — 特定日の銘柄分足Kラインを取得
- `GET /minute_stocks/{date}` — 特定日に分足データのある銘柄
- `GET /local_kline/{symbol}` — ローカル .bin 日足Kラインの読み取り

**トレーニング** `/api/train`
- `GET /config` — デフォルトのトレーニング設定を取得（モデル/ハンドラー/市場）
- `POST /start` — トレーニングジョブを開始（非同期）
- `GET /status/{job_id}` — トレーニング進捗を照会（リアルタイムログ付き）
- `GET /jobs` — 全トレーニングジョブの一覧
- `DELETE /jobs/{job_id}` — トレーニングジョブの削除

**モデル管理** `/api/models`
- `GET /` — 保存済みモデルの一覧（バージョン情報付き）
- `GET /{model_id}` — モデルメタデータの取得
- `GET /by-job/{job_id}` — トレーニングジョブでモデルを検索
- `GET /{model_id}/download` — モデルファイルのダウンロード
- `DELETE /{model_id}` — モデルの削除
- `PATCH /{model_id}/rating?rating=N` — モデル星評価の設定（0–5）

**バックテスト** `/api/backtest`
- `POST /run` — バックテスト実行（非同期）
- `GET /result/{job_id}` — バックテスト結果 + チャートの取得
- `GET /jobs` — 全バックテストジョブの一覧
- `POST /compare` — 複数戦略の比較

**トレード** `/api/trade`
- `POST /connect` — ブローカーへの接続
- `GET /status` — ブローカー/戦略ステータス
- `GET /balance` — 残高の照会
- `GET /positions` — ポジションの照会
- `POST /order` — 注文の発行（リスクチェック付き）
- `GET /orders` — 本日の注文の照会
- `POST /cancel/{order_id}` — 注文の取消
- `POST /strategy/start` — 自動戦略の開始
- `POST /strategy/stop` — 自動戦略の停止
- `GET /strategy/logs` — 戦略実行ログ

**リスク管理** `/api/trade/risk`
- `GET /config` — リスク設定の取得
- `PUT /config` — リスク設定の更新
- `GET /stats` — 日次リスク統計

**予測** `/api/predict`
- `GET /data_range` — 利用可能なデータ日付範囲の取得
- `POST /run` — 個別銘柄予測（HF/日次を自動検出、スコア系列 + シグナル + 強度を返す）
- `POST /minute` — 分足HF予測（単日バーレベルのシグナル）

**WebSocket**: `ws://localhost:8000/ws` — リアルタイムプッシュ（quotes / orders / training / position チャンネル）

### リスクパラメータ

| パラメータ | デフォルト | 説明 |
|---|---|---|
| `max_order_amount` | 100,000 | 注文あたりの最大金額 |
| `max_daily_trades` | 50 | 日次最大取引回数 |
| `max_position_pct` | 0.2 | 銘柄あたりの最大ポジション比率 |
| `filter_limit_up` | true | ストップ高銘柄の除外 |
| `circuit_breaker_loss` | -0.05 | 日次損失サーキットブレーカーのしきい値 |

### 環境変数

すべての設定は `QTRADER_` プレフィックス付きの環境変数または `.env` ファイルをサポートします:

| 変数 | デフォルト | 説明 |
|---|---|---|
| `QTRADER_PORT` | 8000 | バックエンドポート |
| `QTRADER_FE_PORT` | 5173 | フロントエンドポート |
| `QTRADER_HOST` | 0.0.0.0 | バックエンド待受アドレス |
| `QTRADER_JOB_STORE_BACKEND` | sqlite | ジョブストアバックエンド（sqlite / postgresql） |
| `QTRADER_JOB_STORE_PG_DSN` | — | PostgreSQL 接続文字列 |
| `QTRADER_BROKER_TYPE` | sim | ブローカー種別（sim / eastmoney） |

---

## ライセンス

[MITライセンス](LICENSE)

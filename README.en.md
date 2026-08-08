# QTrader

<p align="center">
  <img src="docs/qtrader-banner.svg" alt="QTrader Banner" width="100%">
</p>

**[简体中文](README.zh-CN.md)** | **[English](README.en.md)** | **[Français](README.fr.md)** | **[Deutsch](README.de.md)** | **[Español](README.es.md)** | **[日本語](README.ja.md)** | **[한국어](README.ko.md)**

---

## Introduction

A full-stack quantitative trading platform built on the [Qlib](https://github.com/microsoft/qlib) ecosystem, featuring multi-source data, AI model training & backtesting, simulated/live trading, and real-time risk control.

### Features

- **Multi-Source Data**: Unified AKShare / Qlib abstraction with runtime hot-switching and SQLite incremental caching
- **Minute-Level Data**: 1/5/15/30/60-min K-line sync & query, APScheduler auto-sync after market close
- **AI Training Engine**: Bridges the Qlib ecosystem — supports 15 models (LightGBM / XGBoost / CatBoost / Linear / GRU / LSTM / ALSTM / Transformer / TCN / TabNet / DNN / GATs / SFM / DoubleEnsemble / **HFLGBModel**)
- **High-Frequency Model**: HFLGBModel + HighFreqHandler, trained on 1min data with position buffering (REBALANCE_INTERVAL=5, BUFFER_ZONE=2)
- **Training Dashboard**: 6-dimension signal analysis charts (Loss / RankIC / RankICIR / Long-Short NAV / Decile Returns / Turnover) + HF-specific metrics (return per turnover / cost decomposition / signal half-life / capacity curve)
- **Portfolio Backtest**: TopkDropoutStrategy (topk=30, n_drop=3) + VWAP execution + real turnover + annualized return/Sharpe/max drawdown/IR
- **Single-Stock Prediction**: Load trained models to generate prediction scores + bullish/bearish signal + strength (auto-routes HF models to minute-level path)
- **Model Versioning**: Trained models auto-persisted with incremental versioning, queryable by job and downloadable
- **Model Star Rating**: Rate trained models 1–5 stars, persisted to storage for easy best-model selection
- **Backtesting Engine**: TopkDropout strategy + evaluator (Sharpe, max drawdown, Calmar, IR) with Plotly charts + multi-strategy comparison
- **Trading Module**: SimBroker in-memory matching (T+1) + EastMoney jvQuant API integration
- **Risk Control**: Per-order limit / daily trade cap / position ratio / limit-up filter / daily loss circuit breaker
- **Strategy Engine**: Signal → risk filter → order execution with scheduled rebalancing + runtime logs
- **Job Persistence**: Training/backtest jobs stored in SQLite (default) or PostgreSQL
- **Real-Time Progress**: Training progress percentage + log timeline + WebSocket push
- **Local K-line Reader**: Read Qlib .bin files directly without network requests, supports hfq/raw price toggle
- **Sync Checkpoint**: Resume from exact interruption point, avoiding duplicate fetches
- **Service Management**: One-command `qtrader.sh` script (start / stop / restart / status / logs)

### Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Pydantic v2 + Uvicorn |
| Frontend | React 18 + TypeScript + Vite 6 + Ant Design 5 + Zustand |
| Visualization | Plotly + Lightweight Charts |
| AI/ML | Qlib + LightGBM + XGBoost + CatBoost + PyTorch (GRU/LSTM/Transformer/TCN/GATs) |
| Storage | SQLite / PostgreSQL (jobs) + File system (models) |

### Quick Start

**Requirements**: Python 3.10+ / Node.js 18+ / Qlib data (`~/.qlib/qlib_data/cn_data`)

```bash
git clone https://github.com/shark8848/sharkyai-qtrader.git
cd sharkyai-qtrader

pip install -r requirements.txt

cd frontend && npm install && cd ..

./qtrader.sh start
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

Custom ports: `QTRADER_PORT=9000 QTRADER_FE_PORT=3000 ./qtrader.sh start`

### API Overview

**Data Management** `/api/data`
- `GET /sources` — List available data sources
- `POST /switch` — Switch active data source
- `GET /stocks` — Get stock list
- `GET /kline` — Get K-line data
- `POST /sync_minute` — Sync minute-level K-line data
- `GET /sync_minute/status` — Minute sync progress
- `GET /minute/calendar` — Dates with minute data
- `GET /minute/{symbol}` — Get minute K-line for a stock on a date
- `GET /minute_stocks/{date}` — Stocks with minute data on a date
- `GET /local_kline/{symbol}` — Read local .bin daily K-line

**Training** `/api/train`
- `GET /config` — Get default training config (available models/handlers/markets)
- `POST /start` — Start a training job (async)
- `GET /status/{job_id}` — Query training progress (with real-time logs)
- `GET /jobs` — List all training jobs
- `DELETE /jobs/{job_id}` — Delete a training job

**Model Management** `/api/models`
- `GET /` — List all saved models (with version info)
- `GET /{model_id}` — Get model metadata
- `GET /by-job/{job_id}` — Find model by training job
- `GET /{model_id}/download` — Download model file
- `DELETE /{model_id}` — Delete model
- `PATCH /{model_id}/rating?rating=N` — Set model star rating (0–5)

**Backtesting** `/api/backtest`
- `POST /run` — Execute backtest (async)
- `GET /result/{job_id}` — Get backtest results + charts
- `GET /jobs` — List all backtest jobs
- `POST /compare` — Compare multiple strategies

**Trading** `/api/trade`
- `POST /connect` — Connect to broker
- `GET /status` — Broker/strategy status
- `GET /balance` — Query balance
- `GET /positions` — Query positions
- `POST /order` — Place order (with risk check)
- `GET /orders` — Query today's orders
- `POST /cancel/{order_id}` — Cancel order
- `POST /strategy/start` — Start auto strategy
- `POST /strategy/stop` — Stop auto strategy
- `GET /strategy/logs` — Strategy runtime logs

**Risk Control** `/api/trade/risk`
- `GET /config` — Get risk config
- `PUT /config` — Update risk config
- `GET /stats` — Daily risk statistics

**Prediction** `/api/predict`
- `GET /data_range` — Get available data date range
- `POST /run` — Single-stock prediction (auto-detects HF/daily model, returns score series + signal + strength)
- `POST /minute` — Minute-level HF prediction (single-day bar-level signals)

**WebSocket**: `ws://localhost:8000/ws` — Real-time push (quotes / orders / training / position channels)

### Risk Parameters

| Parameter | Default | Description |
|---|---|---|
| `max_order_amount` | 100,000 | Max amount per order |
| `max_daily_trades` | 50 | Max daily trades |
| `max_position_pct` | 0.2 | Max single-stock position ratio |
| `filter_limit_up` | true | Filter limit-up stocks |
| `circuit_breaker_loss` | -0.05 | Daily loss circuit breaker threshold |

### Environment Variables

All settings support `QTRADER_` prefixed env vars or a `.env` file:

| Variable | Default | Description |
|---|---|---|
| `QTRADER_PORT` | 8000 | Backend port |
| `QTRADER_FE_PORT` | 5173 | Frontend port |
| `QTRADER_HOST` | 0.0.0.0 | Backend listen address |
| `QTRADER_JOB_STORE_BACKEND` | sqlite | Job store backend (sqlite / postgresql) |
| `QTRADER_JOB_STORE_PG_DSN` | — | PostgreSQL connection string |
| `QTRADER_BROKER_TYPE` | sim | Broker type (sim / eastmoney) |

---

## License

[MIT License](LICENSE)

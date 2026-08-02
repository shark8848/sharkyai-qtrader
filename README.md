# QTrader

**[中文](#中文)** | **[English](#english)**

---

## 中文

基于 [Qlib](https://github.com/microsoft/qlib) 生态构建的全流程量化交易平台，支持多数据源、AI 模型训练回测、模拟/实盘交易和实时风控。

### 功能特性

- **多数据源**：AKShare / Qlib 统一抽象，运行时热切换，SQLite 增量缓存
- **分钟级数据**：1/5/15/30/60 分钟 K 线同步与查询，APScheduler 收盘自动同步
- **AI 训练引擎**：桥接 Qlib 生态，支持 15 种模型（LightGBM / XGBoost / CatBoost / Linear / GRU / LSTM / ALSTM / Transformer / TCN / TabNet / DNN / GATs / SFM / DoubleEnsemble / **HFLGBModel**）
- **高频模型支持**：HFLGBModel + HighFreqHandler，基于 1min 数据训练，持仓缓冲执行（REBALANCE_INTERVAL=5, BUFFER_ZONE=2）
- **训练看板**：6 维信号分析图表（Loss / RankIC / RankICIR / Long-Short 净值 / 分层收益 / 换手率）+ 高频专用指标（单位换手收益 / 成本分解 / 信号半衰期 / 容量曲线）
- **组合回测**：TopkDropoutStrategy（topk=30, n_drop=3）+ VWAP 成交 + 真实换手率 + 年化收益/Sharpe/最大回撤/信息比率
- **单股预测**：加载已训练模型，对单只股票生成预测评分 + 多空信号 + 强度分析（自动识别高频模型走分钟级路径）
- **模型版本管理**：训练模型自动持久化，版本号递增，支持按任务查询与下载
- **模型星级评分**：对已训练模型标注 1~5 星评级，持久化存储，便于筛选最优模型
- **回测引擎**：TopkDropout 策略 + 评估器（Sharpe、最大回撤、Calmar、信息比率）+ Plotly 图表 + 多策略对比
- **交易模块**：SimBroker 内存撮合（T+1）+ 东方财富 jvQuant API 接口
- **风控体系**：单笔限额 / 日交易次数 / 仓位比例 / 涨停过滤 / 日亏损熔断
- **策略引擎**：信号 → 风控过滤 → 下单执行 + 定时调仓 + 运行日志
- **任务持久化**：训练/回测任务支持 SQLite（默认）或 PostgreSQL 后端
- **实时进度**：训练进度百分比 + 日志时间线 + WebSocket 推送
- **本地 K 线读取**：直接读取 Qlib .bin 文件，无需网络请求，支持后复权/不复权切换
- **同步断点续传**：checkpoint 机制保证中断后精确恢复，避免重复拉取
- **服务管理**：`qtrader.sh` 一键启停脚本（start / stop / restart / status / logs）

### 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + Pydantic v2 + Uvicorn |
| 前端 | React 18 + TypeScript + Vite 6 + Ant Design 5 + Zustand |
| 可视化 | Plotly + Lightweight Charts |
| AI/ML | Qlib + LightGBM + XGBoost + CatBoost + PyTorch (GRU/LSTM/Transformer/TCN/GATs) |
| 存储 | SQLite / PostgreSQL（任务）+ 文件系统（模型） |

### 快速开始

**环境要求**：Python 3.10+ / Node.js 18+ / Qlib 数据（`~/.qlib/qlib_data/cn_data`）

```bash
# 克隆项目
git clone https://github.com/shark8848/sharkyai-qtrader.git
cd sharkyai-qtrader

# 后端依赖
pip install -r requirements.txt

# 前端依赖
cd frontend && npm install && cd ..

# 一键启动（后端 + 前端）
./qtrader.sh start
```

| 服务 | 地址 |
|---|---|
| 前端界面 | http://localhost:5173 |
| 后端 API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |

自定义端口：`QTRADER_PORT=9000 QTRADER_FE_PORT=3000 ./qtrader.sh start`

### API 概览

**数据管理** `/api/data`
- `GET /sources` — 获取可用数据源
- `POST /switch` — 切换数据源
- `GET /stocks` — 获取股票列表
- `GET /kline` — 获取 K 线数据
- `POST /sync_minute` — 同步分钟级 K 线数据
- `GET /sync_minute/status` — 分钟同步进度
- `GET /minute/calendar` — 有分钟数据的日期列表
- `GET /minute/{symbol}` — 获取某股某日分钟 K 线
- `GET /minute_stocks/{date}` — 获取某日有分钟数据的股票
- `GET /local_kline/{symbol}` — 读取本地 .bin 日 K 线

**训练** `/api/train`
- `GET /config` — 获取默认训练配置（可用模型/因子/市场）
- `POST /start` — 启动训练任务（异步）
- `GET /status/{job_id}` — 查询训练进度（含实时日志）
- `GET /jobs` — 列出所有训练任务
- `DELETE /jobs/{job_id}` — 删除训练任务

**模型管理** `/api/models`
- `GET /` — 列出所有已保存模型（含版本号）
- `GET /{model_id}` — 获取模型元数据
- `GET /by-job/{job_id}` — 按训练任务查找模型
- `GET /{model_id}/download` — 下载模型文件
- `DELETE /{model_id}` — 删除模型
- `PATCH /{model_id}/rating?rating=N` — 设置模型星级评分（0~5）

**回测** `/api/backtest`
- `POST /run` — 执行回测（异步）
- `GET /result/{job_id}` — 获取回测结果 + 图表
- `GET /jobs` — 列出所有回测任务
- `POST /compare` — 多策略对比

**交易** `/api/trade`
- `POST /connect` — 连接券商
- `GET /status` — 券商/策略状态
- `GET /balance` — 查询资金
- `GET /positions` — 查询持仓
- `POST /order` — 下单（含风控检查）
- `GET /orders` — 查询今日委托
- `POST /cancel/{order_id}` — 撤单
- `POST /strategy/start` — 启动自动策略
- `POST /strategy/stop` — 停止自动策略
- `GET /strategy/logs` — 策略运行日志

**风控** `/api/trade/risk`
- `GET /config` — 获取风控配置
- `PUT /config` — 更新风控配置
- `GET /stats` — 风控日统计

**预测** `/api/predict`
- `GET /data_range` — 获取可用数据日期范围
- `POST /run` — 单股预测（自动识别高频/日频模型，返回评分序列 + 多空信号 + 强度）
- `POST /minute` — 分钟级高频预测（单日 bar 级信号）

**WebSocket**：`ws://localhost:8000/ws` — 实时推送（quotes / orders / training / position 频道）

### 风控参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `max_order_amount` | 100,000 | 单笔最大金额 |
| `max_daily_trades` | 50 | 日最大交易次数 |
| `max_position_pct` | 0.2 | 单票最大仓位比例 |
| `filter_limit_up` | true | 涨停股过滤 |
| `circuit_breaker_loss` | -0.05 | 日亏损熔断阈值 |

### 环境变量

所有配置项支持 `QTRADER_` 前缀环境变量或 `.env` 文件：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `QTRADER_PORT` | 8000 | 后端端口 |
| `QTRADER_FE_PORT` | 5173 | 前端端口 |
| `QTRADER_HOST` | 0.0.0.0 | 后端监听地址 |
| `QTRADER_JOB_STORE_BACKEND` | sqlite | 任务存储后端 (sqlite / postgresql) |
| `QTRADER_JOB_STORE_PG_DSN` | — | PostgreSQL 连接串 |
| `QTRADER_BROKER_TYPE` | sim | 券商类型 (sim / eastmoney) |

---

## English

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

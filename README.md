# QTrader

**[中文](#中文)** | **[English](#english)**

---

## 中文

基于 [Qlib](https://github.com/microsoft/qlib) 生态构建的全流程量化交易平台，支持多数据源、AI 模型训练回测、模拟/实盘交易和实时风控。

### 功能特性

- **多数据源**：AKShare / Qlib 统一抽象，运行时热切换，SQLite 增量缓存
- **AI 训练引擎**：桥接 Qlib 生态，支持 LightGBM / XGBoost / CatBoost / Linear 四种模型
- **回测引擎**：TopkDropout 策略 + 评估器（Sharpe、最大回撤、Calmar、信息比率）+ Plotly 图表
- **交易模块**：SimBroker 内存撮合（T+1）+ 东方财富 jvQuant API 接口
- **风控体系**：单笔限额 / 日交易次数 / 仓位比例 / 涨停过滤 / 日亏损熔断
- **策略引擎**：信号 → 风控过滤 → 下单执行 + 定时调仓
- **实时进度**：训练进度百分比 + 日志时间线 + WebSocket 推送
- **服务管理**：`qtrader.sh` 一键启停脚本

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

**数据管理**
- `GET /api/data/sources` — 获取可用数据源
- `POST /api/data/switch` — 切换数据源
- `GET /api/data/stocks` — 获取股票列表
- `GET /api/data/kline` — 获取 K 线数据

**训练回测**
- `POST /api/train/start` — 启动训练任务
- `GET /api/train/status/{job_id}` — 查询训练进度（含实时日志）
- `POST /api/backtest/run` — 执行回测
- `GET /api/backtest/result/{job_id}` — 获取回测结果 + 图表

**交易**
- `POST /api/trade/connect` — 连接券商
- `POST /api/trade/order` — 下单（含风控检查）
- `GET /api/trade/positions` — 查询持仓
- `PUT /api/trade/risk/config` — 配置风控参数

**WebSocket**：`ws://localhost:8000/ws` — 实时推送（quotes / orders / training / position 频道）

### 风控参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `max_order_amount` | 100,000 | 单笔最大金额 |
| `max_daily_trades` | 50 | 日最大交易次数 |
| `max_position_pct` | 0.2 | 单票最大仓位比例 |
| `filter_limit_up` | true | 涨停股过滤 |
| `circuit_breaker_loss` | -0.05 | 日亏损熔断阈值 |

---

## English

A full-stack quantitative trading platform built on the [Qlib](https://github.com/microsoft/qlib) ecosystem, featuring multi-source data, AI model training & backtesting, simulated/live trading, and real-time risk control.

### Features

- **Multi-Source Data**: Unified AKShare / Qlib abstraction with runtime hot-switching and SQLite incremental caching
- **AI Training Engine**: Bridges the Qlib ecosystem — supports LightGBM, XGBoost, CatBoost, and Linear models
- **Backtesting Engine**: TopkDropout strategy + evaluator (Sharpe, max drawdown, Calmar, IR) with Plotly charts
- **Trading Module**: SimBroker in-memory matching (T+1) + EastMoney jvQuant API integration
- **Risk Control**: Per-order limit / daily trade cap / position ratio / limit-up filter / daily loss circuit breaker
- **Strategy Engine**: Signal → risk filter → order execution with scheduled rebalancing
- **Real-Time Progress**: Training progress percentage + log timeline + WebSocket push
- **Service Management**: One-command `qtrader.sh` start/stop script

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

**Data Management**
- `GET /api/data/sources` — List available data sources
- `POST /api/data/switch` — Switch active data source
- `GET /api/data/stocks` — Get stock list
- `GET /api/data/kline` — Get K-line data

**Training & Backtesting**
- `POST /api/train/start` — Start a training job
- `GET /api/train/status/{job_id}` — Query training progress (with real-time logs)
- `POST /api/backtest/run` — Execute backtest
- `GET /api/backtest/result/{job_id}` — Get backtest results + charts

**Trading**
- `POST /api/trade/connect` — Connect to broker
- `POST /api/trade/order` — Place order (with risk check)
- `GET /api/trade/positions` — Query positions
- `PUT /api/trade/risk/config` — Configure risk parameters

**WebSocket**: `ws://localhost:8000/ws` — Real-time push (quotes / orders / training / position channels)

### Risk Parameters

| Parameter | Default | Description |
|---|---|---|
| `max_order_amount` | 100,000 | Max amount per order |
| `max_daily_trades` | 50 | Max daily trades |
| `max_position_pct` | 0.2 | Max single-stock position ratio |
| `filter_limit_up` | true | Filter limit-up stocks |
| `circuit_breaker_loss` | -0.05 | Daily loss circuit breaker threshold |

---

## License

[MIT License](LICENSE)

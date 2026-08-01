# QTrader - 独立量化交易系统

基于 [Qlib](https://github.com/microsoft/qlib) 生态构建的全流程量化交易平台，支持多数据源、AI 模型训练回测、模拟/实盘交易和实时风控。

## 功能特性

- **多数据源**：AKShare / Qlib 统一抽象，运行时热切换，SQLite 增量缓存
- **AI 训练引擎**：桥接 Qlib 生态，支持 LightGBM / XGBoost / CatBoost / Linear 四种模型
- **回测引擎**：TopkDropout 策略 + 评估器（Sharpe、最大回撤、Calmar、信息比率）+ Plotly 图表
- **交易模块**：SimBroker 内存撮合（T+1）+ 东方财富 jvQuant API 接口
- **风控体系**：单笔限额 / 日交易次数 / 仓位比例 / 涨停过滤 / 日亏损熔断
- **策略引擎**：信号 → 风控过滤 → 下单执行 + 定时调仓
- **实时进度**：训练进度百分比 + 日志时间线 + WebSocket 推送
- **服务管理**：`qtrader.sh` 一键启停脚本

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.10+, FastAPI, Pydantic v2, Uvicorn |
| 前端 | React 18, TypeScript, Vite, Ant Design 5 |
| 数据 | AKShare, Qlib, SQLite |
| 可视化 | Plotly, Lightweight Charts |
| 状态管理 | Zustand |

## 项目结构

```
qtrader/
├── backend/
│   ├── api/                  # FastAPI 路由
│   │   ├── data.py           # 数据管理 API
│   │   ├── trading.py        # 交易 API
│   │   ├── training.py       # 训练回测 API
│   │   └── ws.py             # WebSocket 频道订阅
│   ├── config.py             # Pydantic Settings 配置
│   ├── main.py               # FastAPI 入口
│   └── core/
│       ├── data/             # 数据源抽象 + 缓存
│       │   ├── base.py       # DataSource 基类
│       │   ├── akshare_source.py
│       │   ├── qlib_source.py
│       │   ├── manager.py    # DataManager 统一管理
│       │   └── store.py      # SQLite 缓存层
│       ├── engine/           # 训练回测引擎
│       │   ├── trainer.py    # 模型训练 + 实时进度
│       │   ├── backtest.py   # 回测执行
│       │   └── evaluator.py  # 指标计算 + 图表生成
│       └── trading/          # 交易模块
│           ├── broker_base.py     # 券商抽象基类
│           ├── sim_broker.py      # 模拟撮合引擎
│           ├── eastmoney_broker.py # 东方财富接口
│           ├── risk_manager.py    # 风控管理
│           ├── order_manager.py   # 订单管理
│           └── strategy.py        # 策略执行
├── frontend/
│   └── src/pages/
│       ├── Dashboard.tsx      # 仪表盘
│       ├── DataManager.tsx    # 数据管理
│       ├── BacktestPanel.tsx  # 训练与回测
│       ├── TradingPanel.tsx   # 实盘交易
│       └── Settings.tsx       # 系统设置
├── qtrader.sh                 # 服务管理脚本
└── requirements.txt
```

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- Qlib 数据（`~/.qlib/qlib_data/cn_data`）

### 安装

```bash
# 克隆项目
git clone https://github.com/shark8848/sharkyai-qtrader.git
cd sharkyai-qtrader

# 后端依赖
pip install -r requirements.txt

# 前端依赖
cd frontend && npm install && cd ..
```

### 启动服务

```bash
# 一键启动（后端 + 前端）
./qtrader.sh start

# 查看状态
./qtrader.sh status

# 查看日志
./qtrader.sh logs

# 停止服务
./qtrader.sh stop
```

### 访问

| 服务 | 地址 |
|---|---|
| 前端界面 | http://localhost:5173 |
| 后端 API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |

### 自定义端口

```bash
QTRADER_PORT=9000 QTRADER_FE_PORT=3000 ./qtrader.sh start
```

## API 概览

### 数据管理
- `GET /api/data/sources` — 获取可用数据源
- `POST /api/data/switch` — 切换数据源
- `GET /api/data/stocks` — 获取股票列表
- `GET /api/data/kline` — 获取 K 线数据

### 训练回测
- `POST /api/train/start` — 启动训练任务
- `GET /api/train/status/{job_id}` — 查询训练进度（含实时日志）
- `POST /api/backtest/run` — 执行回测
- `GET /api/backtest/result/{job_id}` — 获取回测结果 + 图表

### 交易
- `POST /api/trade/connect` — 连接券商
- `POST /api/trade/order` — 下单（含风控检查）
- `GET /api/trade/positions` — 查询持仓
- `PUT /api/trade/risk/config` — 配置风控参数

### WebSocket
- `ws://localhost:8000/ws` — 实时推送（支持 quotes/orders/training/position 频道）

## 风控参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `max_order_amount` | 100,000 | 单笔最大金额 |
| `max_daily_trades` | 50 | 日最大交易次数 |
| `max_position_pct` | 0.2 | 单票最大仓位比例 |
| `filter_limit_up` | true | 涨停股过滤 |
| `circuit_breaker_loss` | -0.05 | 日亏损熔断阈值 |

## 许可证

[MIT License](LICENSE)

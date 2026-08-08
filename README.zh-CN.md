# QTrader

<p align="center">
  <img src="docs/qtrader-banner.svg" alt="QTrader Banner" width="100%">
</p>

**[简体中文](README.zh-CN.md)** | **[English](README.en.md)** | **[Français](README.fr.md)** | **[Deutsch](README.de.md)** | **[Español](README.es.md)** | **[日本語](README.ja.md)** | **[한국어](README.ko.md)**

---

## 简介

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

## 许可证

[MIT License](LICENSE)

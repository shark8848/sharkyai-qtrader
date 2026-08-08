# QTrader 多源数据管理架构设计

> 版本：v1.0  
> 日期：2026-08-08  
> 状态：设计稿（待同步完成后实施）  
> 作者：QTrader

---

## 1. 背景与目标

### 1.1 现状问题

现有数据管理是"**单活跃源 + SQLite 缓存**"模式：

- `DataSource` ABC → 仅 `AKShareSource` / `QlibSource` 两个实现
- `DataManager` 管理"当前活跃源"（`switch_source` 全局互斥切换）
- 训练 pipeline **硬编码**读 qlib 二进制（`~/.qlib/qlib_data/cn_data`），通过 `_ensure_qlib(high_freq)` 切换日线/高频目录
- 同步是独立流程（`qlib_sync.py` / `minute_sync.py`），与 DataManager 的源抽象两套体系

**核心痛点**：

| # | 问题 | 影响 |
|---|---|---|
| 1 | 训练与数据源解耦不足 | 训练只认 qlib provider_uri，无法选择"用哪个渠道同步的数据"训练 |
| 2 | 同步与查询两套体系 | `qlib_sync` 直接拉 sina 写 bin，绕过统一抽象 |
| 3 | 多源互斥 | 只有一个 active source，无法同时持有多个渠道数据并对比 |
| 4 | 规格不统一 | akshare→统一 df，qlib_sync→.bin，分钟→Parquet，缓存→SQLite，四套并存 |
| 5 | amount 字段历史丢失 | `_fetch_stock_kline` 裁剪掉 amount 导致永远全量重跑（已修复，需根治） |

### 1.2 设计目标

1. **多源并存**：akshare / sina / tushare / baostock / qlib_local 同时注册，非互斥
2. **统一规格**：所有源输出标准 `StandardBar`，转换层统一写入 .bin / Parquet / SQLite
3. **每日自动同步**：保证数据最新，工作日收盘后自动增量同步（A 股为主）
4. **训练可选数据**：训练时按 `dataset_id` 选择数据集（默认 qlib）
5. **前端全面重构**：DataManager 页 4-Tab（数据源 / 同步任务 / 数据集 / 自动同步）

---

## 2. 总体架构

```
┌────────────────────────────────────────────────────────────┐
│                  Frontend DataManager 页（全面重构）          │
│   ①数据源卡片  ②同步任务面板  ③数据集列表  ④自动同步配置       │
└──────────────────────────┬─────────────────────────────────┘
                           │ /api/data/*
┌──────────────────────────▼─────────────────────────────────┐
│                 DataOrchestrator（数据编排器）               │
│  · 多源注册表（eastmoney/akshare/sina/tushare/baostock/qlib）│
│  · 同步调度（按源×市场×频率×目标）                            │
│  · DataCatalog（数据集元数据）                               │
│  · APScheduler 每日定时同步                                  │
└──────┬──────────────────┬──────────────────┬───────────────┘
       │                  │                  │
┌──────▼─────┐    ┌───────▼───────┐   ┌──────▼──────┐
│  源层 Source │    │ 转换层 Converter│   │ 训练接口     │
│ get_daily/  │    │ to_qlib_bin   │   │ TrainProvider│
│ get_minute  │    │ to_parquet    │   │ dataset_id   │
└──────┬─────┘    └───────┬───────┘   └──────┬──────┘
       │                  │                  │
     eastmoney/akshare/ 统一 StandardBar    qlib provider_uri
     sina/tushare/       → .bin / Parquet   (默认 cn_data)
     baostock
```

### 2.1 目录结构

```
backend/core/data/
├── base.py              # DataSource ABC（增强 capabilities/data_format）
├── manager.py           # DataManager（多源注册，保留 active_source 查询默认）
├── schema.py            # 【新增】StandardBar + validate_bars()
├── converter.py         # 【新增】Converter：to_qlib_bin / to_parquet / to_sqlite
├── orchestrator.py      # 【新增】SyncOrchestrator + SyncJob
├── catalog.py           # 【新增】DataCatalog（dataset_catalog 表）
├── sources/
│   ├── eastmoney_source.py  # 【新增】东方财富直连（日线/实时/分钟降级）
│   ├── akshare_source.py    # 现有
│   ├── sina_source.py       # 【新增】独立 sina 通道
│   ├── tushare_source.py    # 【新增】需 token
│   ├── baostock_source.py   # 【新增】免 token
│   └── qlib_source.py       # 现有
├── qlib_sync.py         # 重构：改为 Source → StandardBar → to_qlib_bin
├── minute_sync.py       # 保留
├── minute_to_qlib.py    # 保留
├── local_reader.py      # 保留
├── store.py             # 保留（SQLite 缓存）
└── checkpoint.py        # 保留（断点续传）
```

---

## 3. 统一 Schema（StandardBar）

### 3.1 数据契约

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class StandardBar:
    symbol: str            # SH600519（统一大写）
    datetime: str          # "YYYY-MM-DD"（日）/ "YYYY-MM-DD HH:MM:SS"（分钟）
    freq: str              # "1d" / "1min" / "5min" / "15min" / "30min" / "60min"
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float          # 必填，缺失标记 NaN（不静默丢弃）
    vwap: Optional[float]  # 分钟特有
    paused: Optional[bool] # 分钟特有
    adjusted: str          # "none" / "qfq" / "hfq"
    source_id: str         # 溯源：数据来自哪个渠道
```

### 3.2 校验规则

`validate_bars(bars) -> list[StandardBar]`：

| 规则 | 说明 | 失败处理 |
|---|---|---|
| 字段完整 | 8 个必填字段全部存在 | 拒绝该 bar |
| 数值合法 | open/high/low/close/volume/amount ≥ 0 | 拒绝该 bar |
| NaN 检查 | 必填字段无 NaN | 拒绝该 bar（amount 缺失不再静默） |
| 时间递增 | datetime 严格递增 | 排序后去重 |
| 涨跌幅一致 | high ≥ open/close ≥ low（容忍 1e-6） | 警告并保留 |

### 3.3 设计要点

- **amount 强制必填**：吸取本次 amount 丢失导致全量重跑的教训，缺失即标记，绝不静默裁剪
- **source_id 溯源**：每条数据记录来源，DataCatalog 可追溯"哪个渠道同步的"

---

## 4. 源层（多源并存）

### 4.1 DataSource ABC 增强

```python
class DataSource(ABC):
    source_id: str          # "akshare" / "eastmoney" / "sina" / "tushare" / "baostock" / "qlib_local"
    name: str
    capabilities: set[str]  # {"daily","minute","realtime","financial","stock_list"}
    data_format: str        # "api" / "local_bin"
    enabled: bool           # 可启停

    async def get_stock_list(self) -> list[str]
    async def get_daily_kline(self, symbol, start, end, adjust) -> list[StandardBar]
    async def get_minute_kline(self, symbol, date, period) -> list[StandardBar]  # 新增
    async def health_check(self) -> bool
```

### 4.2 内置源一览

| 源 | source_id | 能力 | 需要 | 优先级 | 备注 |
|---|---|---|---|---|---|
| 东方财富 | `eastmoney` | daily/realtime/stock_list | 无 | 默认 | 直连 EastMoney API，日线/实时质量高 |
| AKShare | `akshare` | daily/minute/realtime/financial | 无 | 默认 | EastMoney + Sina 聚合，分钟经 Sina |
| Sina | `sina` | daily/minute | 无 | 高 | 独立通道，backup |
| Tushare | `tushare` | daily/minute | token | 可选 | 质量高 |
| Baostock | `baostock` | daily/minute | 无 | 可选 | 免费稳定 |
| Qlib Local | `qlib_local` | daily/minute | 本地 .bin | 训练默认 | 只读 |

### 4.2.1 东方财富源（eastmoney）

**定位**：A 股日线 + 实时行情的首选渠道，直连东财开放接口，与交易层 `EastMoneyBroker` 共用厂商。

**接口映射**（经 akshare 封装，或直连东财 push2/push2his API）：

| 能力 | 接口 | 状态 |
|---|---|---|
| 日线历史 | `stock_zh_a_hist`（push2his） | ✅ 稳定（已验证） |
| 实时行情 | `stock_zh_a_spot_em`（push2） | ✅ 稳定 |
| 股票列表 | `stock_info_a_code_name` | ✅ 稳定 |
| 分钟 K 线 | `stock_zh_a_hist_min_em`（push2his） | ⚠️ 不稳定（偶发 RemoteDisconnected，需重试/降级） |
| 财务数据 | `stock_financial_abstract` | ✅ 可用 |

**分钟降级策略**：东财分钟接口失败时，回退到 Sina 通道（`stock_zh_a_minute`，现有 minute_sync 已在用）。

**实现**：

```python
class EastMoneySource(DataSource):
    source_id = "eastmoney"
    capabilities = {"daily", "realtime", "stock_list", "minute", "financial"}
    # 日线/实时：直连东财接口
    # 分钟：东财优先，失败降级 sina
    async def get_daily_kline(...) -> list[StandardBar]
    async def get_realtime_quote(...) -> DataFrame
    async def get_minute_kline(...) -> list[StandardBar]  # 带降级
```

### 4.3 多源并存语义

- **所有源同时注册**，前端展示每个源状态（健康度/能力/启用开关）
- **不再有全局互斥的 active source**
- 保留 `active_source` 仅作 **API 查询默认值**（`GET /api/data/kline` 不带 source 时用它）
- 同步、训练均可显式指定 source_id

---

## 5. 转换层（Converter）

```python
class Converter:
    def to_qlib_bin(bars: list[StandardBar], market: str, freq: str) -> int:
        """标准数据 → qlib .bin（日线 cn_data / 高频 cn_data_1min）"""
        # 复用现有 _write_stock_bins 的二进制格式，但输入为 StandardBar
        # [start_calendar_index, val0, val1, ...] float32

    def to_parquet(bars: list[StandardBar], freq: str) -> Path:
        """标准数据 → Parquet（~/.qtrader/data/{freq}/）"""

    def to_sqlite(bars: list[StandardBar]) -> int:
        """标准数据 → SQLite cache.db（复用 store.py）"""
```

### 5.1 关键重构

现有 `qlib_sync.py` 的写入路径改为：

```
旧：akshare/sina 直接拉 → DataFrame → 写 .bin（amount 易丢）
新：任意 Source → StandardBar（校验）→ Converter.to_qlib_bin
```

**这是 amount 缺失 bug 的根治**：任何渠道进 .bin 都走统一规格，字段完整校验。

---

## 6. 同步编排器（SyncOrchestrator）

### 6.1 SyncJob 模型

```python
class SyncJob:
    job_id: str            # sync_{uuid4().hex[:12]}
    source_id: str         # akshare / tushare / ...
    market: str            # all / csi300 / csi500 / sh50 / ...
    freq: str              # daily / 1min / 5min ...
    target: str            # qlib_bin / parquet / sqlite
    status: str            # idle|running|done|error|stopped
    progress: float
    message: str
    checkpoint: set        # 断点续传（复用 SyncCheckpoint）
    start_date, end_date   # 覆盖范围
    started_at, finished_at
    fail_count, success_count, skip_count
```

### 6.2 并发语义

- **不同 source 的任务可并行**（akshare 与 tushare 互不影响）
- **同 source 内串行**（防 sina/EastMoney 封 IP，0.5s 限速保留）
- 全局 `threading.Semaphore` 控制线程数

### 6.3 停止语义

复用已实现的 `_sync_stop` 协同停止：置位后当前股票处理完即退出，**保留 checkpoint**（已修复的 finish() 误删问题）。

### 6.4 每日自动同步（APScheduler）

```python
# main.py lifespan 扩展
scheduler.add_job(_scheduled_daily_sync, "cron", day_of_week="mon-fri", hour=15, minute=30)
scheduler.add_job(_scheduled_minute_sync, "cron", day_of_week="mon-fri", hour=15, minute=35)
```

| Job | 时间 | 内容 |
|---|---|---|
| 日线增量同步 | 工作日 15:30 | 全市场增量 → qlib_bin（A 股收盘后数据完整） |
| 分钟 1min 同步 | 工作日 15:35 | 现有逻辑保留 |

**可配置**（`backend/config.py` 新增）：

```python
qtrader_auto_sync: bool = True       # 是否开启自动同步
qtrader_auto_sync_time: str = "15:30" # 日线同步时间
qtrader_auto_sync_markets: str = "all"  # 市场范围
```

---

## 7. DataCatalog（数据集目录）

### 7.1 表结构

```sql
CREATE TABLE IF NOT EXISTS dataset_catalog (
    dataset_id     TEXT PRIMARY KEY,  -- csi300_daily_akshare_20260808
    source_id      TEXT NOT NULL,
    market         TEXT NOT NULL,
    freq           TEXT NOT NULL,     -- daily/1min/5min...
    storage        TEXT NOT NULL,     -- qlib_bin/parquet/sqlite
    start_date     TEXT,
    end_date       TEXT,
    stock_count    INTEGER DEFAULT 0,
    coverage_pct   REAL DEFAULT 0,    -- 有效覆盖股票数/总数
    adjusted       TEXT DEFAULT 'hfq',
    synced_at      TEXT,
    status         TEXT DEFAULT 'syncing'  -- ready/syncing/stale/error
);
```

### 7.2 数据新鲜度

- 每次同步完成更新 `synced_at`
- `is_stale(dataset_id)`：`synced_at` 距今 > 1 个交易日 → `status='stale'`
- 前端高亮提示"建议重新同步"

### 7.3 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/data/datasets` | 列出所有数据集（含覆盖度/新鲜度/状态） |
| GET | `/api/data/datasets/{id}` | 数据集详情 |
| GET | `/api/data/datasets/{id}/coverage` | 覆盖明细（哪些股票缺失） |
| POST | `/api/data/datasets/{id}/resync` | 重新同步该数据集 |

---

## 8. 训练接口（TrainProvider）

### 8.1 配置扩展

```python
class TrainConfig(BaseModel):
    ...
    dataset_id: str = ""      # 新增：指定数据集（默认 qlib cn_data）
    data_source: str = "qlib" # 兼容：直接指定源
```

### 8.2 trainer 改造

`_ensure_qlib` 改为：

```python
def _ensure_qlib(self, high_freq: bool = False, dataset_id: str = ""):
    # 1. dataset_id 非空 → 从 DataCatalog 解析 provider_uri + market + freq
    # 2. 否则默认 cn_data / cn_data_1min（保持现状）
    # 3. 检查 C.registered 当前 provider_uri，不一致则重新 init（现有逻辑）
```

新增接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/train/datasets` | 复用 data datasets，供前端训练表单下拉选择 |

### 8.3 训练前校验

- `train_range` 必须落在数据集 `start_date`~`end_date` 内
- 数据集 `status != ready` 时警告（建议先同步）
- 股票池 `market` 与数据集一致校验

---

## 9. 前端 DataManager 全面重构

### 9.1 页面结构（4-Tab）

```
DataManager.tsx
├── Tab1: 📡 数据源
│   └── SourceCard 组件列表：每个源显示
│       - 图标 + 名称 + 状态（健康/不可用/未启用）
│       - 能力徽章（日线/分钟/实时/财务）
│       - 启用/停用开关
│       - "设为查询默认"按钮
├── Tab2: 🔄 同步任务
│   ├── 新建同步表单：源 × 市场 × 频率 × 目标存储
│   ├── 任务列表：进度条/状态/断点/停止/重试
│   └── 实时进度轮询（GET /api/data/sync_qlib/status 或 /sync/{job_id}/status）
├── Tab3: 📊 数据集
│   ├── 数据集卡片：market × freq × source
│   ├── 显示覆盖度 progress + stock_count + 新鲜度
│   ├── stale 标记高亮 + "重新同步"按钮
│   └── 覆盖明细展开（缺失股票列表）
└── Tab4: ⏰ 自动同步
    ├── 开启/关闭开关（QTRADER_AUTO_SYNC）
    ├── 同步时间设置（15:30 日线 / 15:35 分钟）
    ├── 市场范围选择
    └── 最近同步记录列表
```

### 9.2 组件拆分

```
frontend/src/
├── pages/DataManager.tsx          # 4-Tab 容器
├── components/data/
│   ├── SourceCard.tsx             # 源卡片
│   ├── SyncForm.tsx               # 新建同步表单
│   ├── SyncTaskList.tsx           # 同步任务列表
│   ├── DatasetCard.tsx            # 数据集卡片
│   ├── DatasetCoverage.tsx        # 覆盖明细
│   └── AutoSyncPanel.tsx          # 自动同步配置
├── stores/dataStore.ts            # Zustand：sources/tasks/datasets/autoSync
└── api/data.ts                    # axios 封装（现有扩展）
```

---

## 10. 数据流全景

```
① 用户选择源 + 市场 + 频率 → 发起同步（手动 或 每日 15:30 自动）
② SyncOrchestrator 拉取源数据 → validate_bars → StandardBar
③ Converter → to_qlib_bin / to_parquet / to_sqlite
④ DataCatalog 更新元数据（覆盖度/新鲜度/synced_at）
⑤ 训练时前端选 dataset_id → trainer 解析 provider_uri → 训练
⑥ 预测同理（复用 dataset_id 定位数据）
```

---

## 11. 实施计划

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| **P1** | StandardBar + Converter（`to_qlib_bin` 重构）| amount 全覆盖，单测通过 |
| **P2** | SyncOrchestrator + DataCatalog + 每日定时同步 | 定时触发日线+分钟同步 |
| **P3** | 多源接入（eastmoney/sina/tushare/baostock）+ DataManager 多源 | 前端源卡片可切换，东财日线/实时直连可用 |
| **P4** | TrainProvider（训练选 dataset）+ 前端 4-Tab 重构 | 端到端选源训练 |

### 前置条件

- 待当前全量同步（5205 只）完成后开始 P1
- tushare 接入需用户提供 token（无则 P3 先做 sina+baostock）

### 风险与对策

| 风险 | 对策 |
|---|---|
| Converter 重构影响现有同步 | P1 独立成模块，`qlib_sync.py` 逐步迁移，先保留旧路径跑通再切换 |
| 多源并发触发上游限流 | 同源串行 + 0.5s 限速 + 超时保护（已实现） |
| 训练选错数据集 | dataset 覆盖范围校验 + 前端状态提示 |

---

## 12. 参考

- 现有代码：`backend/core/data/{base,manager,store,qlib_sync,minute_sync}.py`
- 已修复经验：amount 缺失（`sync-amount-bug`）、超时保护、断点续传、stop 协同停止

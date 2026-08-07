"""Convert Parquet minute data to Qlib 1min .bin format.

Reads from: ~/.qtrader/minute_data/{date}/{symbol}.parquet
Writes to:  ~/.qlib/qlib_data/cn_data_1min/
            ├── calendars/1min.txt
            ├── instruments/all.txt
            └── features/{symbol}/*.1min.bin

Supports incremental updates (only converts new dates).
"""

import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MINUTE_DATA_DIR = Path.home() / ".qtrader" / "minute_data"
QLIB_1MIN_DIR = Path.home() / ".qlib" / "qlib_data" / "cn_data_1min"
DAY_INST_DIR = Path.home() / ".qlib" / "qlib_data" / "cn_data" / "instruments"

FEATURES = ["open", "high", "low", "close", "volume", "vwap", "paused_num"]
FREQ = "1min"
BIN_SUFFIX = ".bin"


class ConvertTask:
    """Tracks progress of Parquet → Qlib 1min conversion."""

    def __init__(self):
        self.status = "idle"  # idle | running | done | error
        self.progress = 0.0
        self.message = ""
        self.total_stocks = 0
        self.done_stocks = 0
        self.error: Optional[str] = None
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None

    def to_dict(self):
        return {
            "status": self.status,
            "progress": round(self.progress, 1),
            "message": self.message,
            "total_stocks": self.total_stocks,
            "done_stocks": self.done_stocks,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


_task = ConvertTask()
_lock = threading.Lock()


def get_convert_status() -> dict:
    d = _task.to_dict()
    # Add info about existing qlib 1min data
    if QLIB_1MIN_DIR.exists():
        cal_file = QLIB_1MIN_DIR / "calendars" / "1min.txt"
        if cal_file.exists():
            lines = cal_file.read_text().strip().split("\n")
            d["qlib_bars"] = len(lines)
        feat_dir = QLIB_1MIN_DIR / "features"
        if feat_dir.exists():
            d["qlib_stocks"] = len([p for p in feat_dir.iterdir() if p.is_dir()])
    return d


def patch_missing_features() -> dict:
    """增量补齐历史转换缺失的 paused_num 字段。

    qlib 的 HighFreqHandler 特征表达式依赖 $paused_num（Select(Gt($paused_num, 1.001))），
    但历史 1min 转换只生成了 open/high/low/close/volume，导致分钟预测/训练崩溃。
    本函数遍历已有特征目录，为缺失股票补写 paused_num（固定 2.0，正常成交分钟）。
    vwap 缺失不影响 handler（If(IsNull($vwap), $close, $vwap) 兜底），无需补齐。
    """
    import numpy as np

    if not QLIB_1MIN_DIR.exists():
        return {"error": f"Qlib 1min 目录不存在: {QLIB_1MIN_DIR}"}

    feat_dir = QLIB_1MIN_DIR / "features"
    patched = {"paused_num": 0, "skipped": 0}

    for stock_dir in feat_dir.iterdir():
        if not stock_dir.is_dir():
            continue

        # 以 close bin 为参考（决定 start index 与长度）
        ref_bin = stock_dir / "close.1min.bin"
        if not ref_bin.exists():
            patched["skipped"] += 1
            continue
        try:
            ref = np.fromfile(str(ref_bin), dtype="<f")
            start_idx = int(ref[0])
            n = len(ref) - 1
            if n <= 0:
                patched["skipped"] += 1
                continue
        except Exception:
            patched["skipped"] += 1
            continue

        # paused_num：固定 2.0（正常成交分钟），无源数据依赖。
        # qlib HighFreqHandler 用 Select(Gt($paused_num, 1.001), ...) 过滤暂停分钟，
        # 缺该字段会导致特征表达式为空、分钟预测/训练崩溃。vwap 缺失则由
        # handler 内 If(IsNull($vwap), $close, $vwap) 兜底，无需补齐。
        pn_path = stock_dir / "paused_num.1min.bin"
        if not pn_path.exists():
            pn = np.full(n + 1, 2.0, dtype="<f")
            pn[0] = start_idx
            pn.tofile(str(pn_path))
            patched["paused_num"] += 1

    return patched


def start_convert() -> dict:
    """Start background conversion task."""
    global _task
    with _lock:
        if _task.status == "running":
            return {"error": "转换任务正在运行中，请等待完成"}
        _task = ConvertTask()
        _task.status = "running"
        _task.started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _task.message = "正在扫描分钟数据..."

    t = threading.Thread(target=_run_convert, daemon=True)
    t.start()
    return {"message": "Parquet → Qlib 1min 转换已启动"}


def _generate_market_instruments(inst_dir: Path, instruments_data: list):
    """Generate csi300/csi500/csi100 instrument files by intersecting with day-line pools."""
    # Build map: symbol -> (start, end) from actual 1min data
    range_map = {}
    for line in instruments_data:
        parts = line.split("\t")
        if len(parts) >= 3:
            range_map[parts[0]] = (parts[1], parts[2])

    for fname in ["csi300.txt", "csi500.txt", "csi100.txt"]:
        src = DAY_INST_DIR / fname
        if not src.exists():
            continue
        lines_out = []
        with open(src) as f:
            for line in f:
                parts = line.strip().split("\t")
                if parts and parts[0] in range_map:
                    start, end = range_map[parts[0]]
                    lines_out.append(f"{parts[0]}\t{start}\t{end}")
        if lines_out:
            with open(inst_dir / fname, "w") as f:
                f.write("\n".join(lines_out) + "\n")
            logger.info(f"Generated {fname}: {len(lines_out)} stocks")


def _run_convert():
    """Main conversion logic."""
    global _task
    try:
        if not MINUTE_DATA_DIR.exists():
            raise ValueError(f"分钟数据目录不存在: {MINUTE_DATA_DIR}")

        # Scan all date directories
        date_dirs = sorted(
            [d.name for d in MINUTE_DATA_DIR.iterdir()
             if d.is_dir() and d.name[0].isdigit()]
        )
        if not date_dirs:
            raise ValueError("无分钟数据日期目录")

        _task.message = f"发现 {len(date_dirs)} 个交易日数据"

        # Collect all symbols across all dates
        all_symbols = set()
        for date_str in date_dirs:
            day_dir = MINUTE_DATA_DIR / date_str
            for f in day_dir.glob("*.parquet"):
                all_symbols.add(f.stem)

        symbols = sorted(all_symbols)
        _task.total_stocks = len(symbols)
        _task.message = f"共 {len(symbols)} 只股票，开始转换..."

        # Phase 1: Build global calendar (all unique minute timestamps)
        _task.message = "正在构建交易日历..."
        all_timestamps = set()
        stock_data: dict[str, list[pd.DataFrame]] = {}

        for i, symbol in enumerate(symbols):
            dfs = []
            for date_str in date_dirs:
                pq_path = MINUTE_DATA_DIR / date_str / f"{symbol}.parquet"
                if not pq_path.exists():
                    continue
                try:
                    df = pd.read_parquet(pq_path)
                    if df.empty:
                        continue
                    # Ensure datetime column
                    if "datetime" not in df.columns:
                        if "date" in df.columns and "time" in df.columns:
                            df["datetime"] = pd.to_datetime(df["date"] + " " + df["time"])
                        else:
                            continue
                    df["datetime"] = pd.to_datetime(df["datetime"])
                    dfs.append(df)
                    all_timestamps.update(df["datetime"].tolist())
                except Exception as e:
                    logger.debug(f"Skip {symbol}/{date_str}: {e}")
                    continue

            if dfs:
                stock_data[symbol] = dfs

            _task.done_stocks = i + 1
            _task.progress = (i + 1) / len(symbols) * 50  # Phase 1 = 0-50%
            if (i + 1) % 100 == 0:
                _task.message = f"读取数据: {i+1}/{len(symbols)} 只"

        # Sort calendar
        calendar = sorted(all_timestamps)
        if not calendar:
            raise ValueError("无有效分钟时间戳")

        _task.message = f"日历构建完成: {len(calendar)} 个时间戳，开始写入 .bin ..."

        # Phase 2: Write Qlib .bin files
        # Create directories
        cal_dir = QLIB_1MIN_DIR / "calendars"
        feat_dir = QLIB_1MIN_DIR / "features"
        inst_dir = QLIB_1MIN_DIR / "instruments"
        cal_dir.mkdir(parents=True, exist_ok=True)
        feat_dir.mkdir(parents=True, exist_ok=True)
        inst_dir.mkdir(parents=True, exist_ok=True)

        # Write calendar
        cal_path = cal_dir / "1min.txt"
        cal_strings = [ts.strftime("%Y-%m-%d %H:%M:%S") for ts in calendar]
        np.savetxt(str(cal_path), cal_strings, fmt="%s", encoding="utf-8")

        # Build calendar index lookup
        cal_index = {ts: idx for idx, ts in enumerate(calendar)}

        # Write instruments
        instruments_data = []
        written_stocks = 0

        for i, (symbol, dfs) in enumerate(stock_data.items()):
            try:
                # Merge all dates for this stock
                merged = pd.concat(dfs, ignore_index=True)
                merged = merged.drop_duplicates(subset=["datetime"], keep="last")
                merged = merged.sort_values("datetime").reset_index(drop=True)

                if merged.empty:
                    continue

                # Create stock feature directory
                # Qlib symbol format: SH600519 (uppercase)
                qlib_symbol = symbol.upper()
                # Qlib FileFeatureStorage uses lowercase paths
                stock_feat_dir = feat_dir / qlib_symbol.lower()
                stock_feat_dir.mkdir(parents=True, exist_ok=True)

                # Get start index in global calendar
                first_ts = merged["datetime"].iloc[0]
                start_idx = cal_index.get(first_ts)
                if start_idx is None:
                    continue

                # 计算 vwap（成交额/成交量）与 paused_num（qlib 高频 handler 依赖）
                # - vwap：源数据有 amount 列，vwap = amount / volume，volume 为 0 时回退 close
                # - paused_num：qlib 用 Gt($paused_num, 1.001) 过滤暂停分钟；AKShare 聚合的
                #   连续分钟 bar 均为正常成交，参考 qlib 官方数据取 2.0
                if "amount" in merged.columns and "volume" in merged.columns:
                    volume = pd.to_numeric(merged["volume"], errors="coerce").fillna(0)
                    amount = pd.to_numeric(merged["amount"], errors="coerce").fillna(0)
                    vwap = amount / volume.replace(0, np.nan)
                    merged["vwap"] = vwap.fillna(merged["close"])
                else:
                    merged["vwap"] = merged["close"]
                merged["paused_num"] = 2.0

                # Write each feature as .bin
                for field in FEATURES:
                    if field not in merged.columns:
                        continue
                    values = pd.to_numeric(merged[field], errors="coerce").fillna(0).values
                    # Qlib bin format: [start_index, val0, val1, ...]
                    bin_data = np.hstack([[start_idx], values]).astype("<f")
                    bin_path = stock_feat_dir / f"{field}.{FREQ}{BIN_SUFFIX}"
                    bin_data.tofile(str(bin_path))

                # Track instrument range
                last_ts = merged["datetime"].iloc[-1]
                instruments_data.append(
                    f"{qlib_symbol.lower()}\t{first_ts.strftime('%Y-%m-%d %H:%M:%S')}\t{last_ts.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                written_stocks += 1

            except Exception as e:
                logger.debug(f"Write {symbol} failed: {e}")
                continue

            _task.progress = 50 + (i + 1) / len(stock_data) * 50  # Phase 2 = 50-100%
            if (i + 1) % 100 == 0:
                _task.message = f"写入 .bin: {i+1}/{len(stock_data)} 只"

        # Write instruments file
        inst_path = inst_dir / "all.txt"
        with open(inst_path, "w") as f:
            f.write("\n".join(instruments_data) + "\n")

        # Generate market-specific instrument files (intersect with day-line pools)
        _generate_market_instruments(inst_dir, instruments_data)

        _task.status = "done"
        _task.progress = 100
        _task.message = (
            f"转换完成: {written_stocks} 只股票，"
            f"{len(calendar)} 个时间戳，"
            f"输出目录 {QLIB_1MIN_DIR}"
        )
        _task.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"Convert done: {written_stocks} stocks, {len(calendar)} bars")

    except Exception as e:
        logger.exception("Convert failed")
        _task.status = "error"
        _task.error = str(e)
        _task.message = f"转换失败: {e}"
        _task.finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

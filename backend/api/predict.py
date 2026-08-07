"""Single-stock prediction API routes."""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from qtrader.backend.core.engine.model_store import get_model_store

logger = logging.getLogger(__name__)
router = APIRouter()


def _ensure_qlib_initialized(provider_uri: str, high_freq: bool = False) -> None:
    """安全初始化 qlib，避免与训练任务并发时重复注册。

    训练进行中会激活 QlibRecorder（active_experiment 非空），此时再次调用
    qlib.init() 会抛 RecorderInitializationError。因此：
    - 若 qlib 已注册（C.registered）且 provider_uri 匹配：直接跳过（数据已在缓存中）
    - 若 provider_uri 不匹配（日线/分钟切换）且训练进行中：抛 ValueError，明确告知用户
    - 若 provider_uri 不匹配且无活跃训练：安全重注册
    """
    import qlib
    from qlib.config import C

    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")

    # 已注册且数据源一致：无需重复初始化
    if C.registered:
        current = str(C["provider_uri"].get("__DEFAULT_FREQ", ""))
        if current == str(provider_uri):
            return
        # 数据源不同：若训练未在跑则可安全重注册，否则给出明确错误
        try:
            from qlib.workflow import R
            if getattr(R, "exp_manager", None) is not None and R.exp_manager.active_experiment is not None:
                raise ValueError(
                    f"训练任务进行中，无法切换 qlib 数据源 {current} -> {provider_uri}，"
                    f"请等待训练完成后再发起该预测"
                )
        except ValueError:
            raise
        except Exception:
            pass

    # 未注册，或数据源不同且无活跃训练：初始化
    from qlib.constant import REG_CN
    if high_freq:
        from qlib.contrib.ops.high_freq import DayLast, FFillNan, BFillNan, Date, Select, IsNull, IsInf, Cut
        qlib.init(
            provider_uri=provider_uri,
            region=REG_CN,
            custom_ops=[DayLast, FFillNan, BFillNan, Date, Select, IsNull, IsInf, Cut],
            expression_cache=None,
        )
    else:
        qlib.init(provider_uri=provider_uri, region=REG_CN)


class PredictRequest(BaseModel):
    model_id: str
    symbol: str  # e.g. "SH600519"
    start_date: Optional[str] = None  # default: 6 months ago
    end_date: Optional[str] = None    # default: today


class MinutePredictRequest(BaseModel):
    symbol: str  # e.g. "sh600519"
    date: Optional[str] = None  # default: latest available
    model_id: Optional[str] = None  # default: latest HF model


@router.get("/data_range")
async def get_data_range():
    """Return the available data date range."""
    try:
        from pathlib import Path
        data_dir = str(Path.home() / ".qlib" / "qlib_data" / "cn_data")
        _ensure_qlib_initialized(data_dir)
        from qlib.data import D
        cal = D.calendar(freq="day")
        if len(cal) == 0:
            return {"start": None, "end": None}
        return {
            "start": str(cal[0].date()),
            "end": str(cal[-1].date()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run")
async def run_predict(req: PredictRequest):
    """Use a trained model to generate prediction scores for a single stock."""
    store = get_model_store()
    meta = store.get_meta(req.model_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Model {req.model_id} not found")

    # Defaults
    end_date = req.end_date or "2020-09-25"
    start_date = req.start_date or "2020-03-01"

    # 高频模型走分钟级预测路径
    handler_name = meta.get("handler", "Alpha158")
    if handler_name == "HighFreqHandler":
        try:
            result = _predict_minute(
                symbol=req.symbol,
                date=end_date,  # 用结束日期作为预测目标日
                model_id=req.model_id,
            )
            # 适配前端统一格式
            merged_data = []
            for a, p in zip(result.get("actual", []), result.get("predicted", [])):
                merged_data.append({
                    "date": a["time"],
                    "close": a["close"],
                    "score": p["score"],
                })
            sig = result.get("signal", {})
            direction = "看多" if sig.get("direction") == "看涨" else "看空"
            return {
                "model_id": result.get("model_id", req.model_id),
                "symbol": req.symbol,
                "start_date": start_date,
                "end_date": end_date,
                "handler": handler_name,
                "total_days": result.get("total_bars", len(merged_data)),
                "data": merged_data,
                "signal": {
                    "direction": direction,
                    "latest_score": sig.get("latest_score"),
                    "avg_score": sig.get("avg_score"),
                    "recent_avg": sig.get("avg_score"),
                    "strength": sig.get("strength", 0),
                },
            }
        except Exception as e:
            logger.exception(f"Minute prediction failed for {req.symbol}")
            raise HTTPException(status_code=500, detail=str(e))

    try:
        result = _predict_single_stock(
            model_id=req.model_id,
            symbol=req.symbol,
            start_date=start_date,
            end_date=end_date,
            handler=handler_name,
            market=meta.get("market", "csi300"),
            train_config=meta.get("config", {}),
        )
        return result
    except Exception as e:
        logger.exception(f"Prediction failed for {req.symbol} with {req.model_id}")
        raise HTTPException(status_code=500, detail=str(e))


def _predict_single_stock(
    model_id: str,
    symbol: str,
    start_date: str,
    end_date: str,
    handler: str,
    market: str,
    train_config: dict,
) -> dict:
    """Synchronous prediction logic."""
    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")

    from pathlib import Path
    data_dir = str(Path.home() / ".qlib" / "qlib_data" / "cn_data")
    # 安全初始化：训练进行中不重复注册（避免 RecorderInitializationError）
    _ensure_qlib_initialized(data_dir)

    # 校验日期范围是否在数据覆盖内
    from qlib.data import D
    cal = D.calendar(freq="day")
    if len(cal) == 0:
        raise ValueError("无可用交易日历数据")
    data_start = str(cal[0].date())
    data_end = str(cal[-1].date())
    if start_date > data_end or end_date < data_start:
        raise ValueError(
            f"请求日期范围 {start_date}~{end_date} 超出可用数据范围 ({data_start} ~ {data_end})，请调整日期"
        )
    # 裁剪到数据范围内
    start_date = max(start_date, data_start)
    end_date = min(end_date, data_end)

    from qlib.utils import init_instance_by_config
    from qtrader.backend.core.engine.model_store import get_model_store

    # Load model
    store = get_model_store()
    model = store.load_model(model_id)

    # Build dataset for the single stock
    # Use a wider start for handler fitting (need history for feature computation)
    fit_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=365)).strftime("%Y-%m-%d")

    handler_config = {
        "class": handler,
        "module_path": "qlib.contrib.data.handler",
        "kwargs": {
            "start_time": fit_start,
            "end_time": end_date,
            "fit_start_time": fit_start,
            "fit_end_time": start_date,
            "instruments": [symbol],
        },
    }

    dataset_config = {
        "class": "DatasetH",
        "module_path": "qlib.data.dataset",
        "kwargs": {
            "handler": handler_config,
            "segments": {
                "train": (fit_start, start_date),
                "valid": (start_date, start_date),
                "test": (start_date, end_date),
            },
        },
    }

    dataset = init_instance_by_config(dataset_config)

    # Fill NaN features to avoid NaN propagation in neural network models.
    # 注意: handler._data 和 handler._infer 可能都含 NaN（如 VWAP0 缺失），
    # 且 prepare() 读取的是 _infer，因此必须 patch prepare() 的返回值。
    import pandas as pd
    import numpy as np

    def _fill_df(df):
        if isinstance(df, pd.DataFrame) and not df.empty:
            nan_count = int(df.isna().sum().sum())
            if nan_count > 0:
                return df.ffill().bfill().fillna(0)
        return df

    # 同时填充 handler 内部缓存（_data 和 _infer）
    try:
        for attr in ('_data', '_infer'):
            internal = getattr(dataset.handler, attr, None)
            if isinstance(internal, pd.DataFrame) and internal.isna().sum().sum() > 0:
                setattr(dataset.handler, attr, internal.ffill().bfill().fillna(0))
    except Exception:
        pass

    # Patch prepare() 确保返回的 DataFrame 无 NaN（兜底）
    _original_prepare = dataset.prepare
    def _patched_prepare(*args, **kwargs):
        result = _original_prepare(*args, **kwargs)
        if isinstance(result, list):
            return [_fill_df(item) for item in result]
        return _fill_df(result)
    dataset.prepare = _patched_prepare

    # Check for corrupted model weights (NaN in parameters)
    try:
        import torch
        nn_module = None
        for attr in ['model', 'lstm_model', 'rnn', 'net', 'transformer']:
            obj = getattr(model, attr, None)
            if obj is not None and hasattr(obj, 'named_parameters'):
                nn_module = obj
                break
        if nn_module is not None:
            nan_params = sum(1 for _, p in nn_module.named_parameters() if torch.isnan(p).any())
            if nan_params > 0:
                raise ValueError(
                    f"模型 {model_id} 权重已损坏（{nan_params} 个参数含 NaN），"
                    f"可能是训练数据含 NaN 导致。请重新训练或使用其他模型（如 XGBoost/LightGBM）。"
                )
    except ImportError:
        pass

    # Generate predictions
    pred = model.predict(dataset, segment="test")

    # Get actual price data
    import pandas as pd
    from qlib.data import D

    df_price = D.features(
        [symbol],
        ["$close", "$open", "$high", "$low", "$volume"],
        start_time=start_date,
        end_time=end_date,
        freq="day",
    )

    # Align prediction with price
    if isinstance(pred, pd.Series):
        pred_df = pred.to_frame("score")
    else:
        pred_df = pd.DataFrame({"score": pred})

    # Filter to the target symbol
    if isinstance(pred_df.index, pd.MultiIndex):
        pred_df = pred_df.xs(symbol, level="instrument")
    if isinstance(df_price.index, pd.MultiIndex):
        df_price = df_price.xs(symbol, level="instrument")

    # Ensure DatetimeIndex (xs may leave a generic Index)
    pred_df.index = pd.to_datetime(pred_df.index)
    df_price.index = pd.to_datetime(df_price.index)

    # Merge
    merged = df_price.join(pred_df, how="inner")
    merged = merged.dropna(subset=["score"])

    # Build response
    records = []
    for date, row in merged.iterrows():
        records.append({
            "date": date.strftime("%Y-%m-%d"),
            "close": round(float(row["$close"]), 2),
            "open": round(float(row["$open"]), 2),
            "high": round(float(row["$high"]), 2),
            "low": round(float(row["$low"]), 2),
            "volume": int(row["$volume"]) if not pd.isna(row["$volume"]) else 0,
            "score": round(float(row["score"]), 6),
        })

    # Compute signal summary
    if records:
        latest = records[-1]
        scores = [r["score"] for r in records]
        avg_score = sum(scores) / len(scores)
        recent_5 = scores[-5:] if len(scores) >= 5 else scores
        recent_avg = sum(recent_5) / len(recent_5)

        signal = "看多" if latest["score"] > avg_score else "看空"
        strength = abs(latest["score"] - avg_score) / (max(scores) - min(scores) + 1e-8)
        strength_pct = min(round(strength * 100), 100)
    else:
        latest = None
        signal = "无数据"
        strength_pct = 0
        recent_avg = 0
        avg_score = 0

    return {
        "model_id": model_id,
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
        "handler": handler,
        "total_days": len(records),
        "data": records,
        "signal": {
            "direction": signal,
            "latest_score": latest["score"] if latest else None,
            "avg_score": round(avg_score, 6),
            "recent_avg": round(recent_avg, 6),
            "strength": strength_pct,
        },
    }


# ---------------------------------------------------------------------------
# High-frequency minute prediction
# ---------------------------------------------------------------------------


@router.post("/minute")
async def run_minute_predict(req: MinutePredictRequest):
    """Use HFLGBModel to predict minute-level price movement."""
    try:
        result = _predict_minute(
            symbol=req.symbol,
            date=req.date,
            model_id=req.model_id,
        )
        return result
    except Exception as e:
        logger.exception(f"Minute prediction failed for {req.symbol}")
        raise HTTPException(status_code=500, detail=str(e))


def _predict_minute(symbol: str, date: Optional[str], model_id: Optional[str]) -> dict:
    """Minute-level prediction using Qlib high-freq pipeline."""
    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    from pathlib import Path

    qlib_1min_dir = Path.home() / ".qlib" / "qlib_data" / "cn_data_1min"
    if not qlib_1min_dir.exists():
        raise ValueError(
            "Qlib 1min 数据目录不存在，请先在数据管理页面执行「转换为 Qlib 1min」"
        )

    # 安全初始化：训练进行中不重复注册（避免 RecorderInitializationError）
    _ensure_qlib_initialized(str(qlib_1min_dir), high_freq=True)

    # Determine date range
    from qlib.data import D
    cal = D.calendar(freq="1min")
    if len(cal) == 0:
        raise ValueError("Qlib 1min 日历为空，请先转换数据")

    # If date specified, filter to that day; otherwise use last day
    import pandas as pd
    cal_series = pd.Series(cal)
    if date:
        day_mask = cal_series.dt.strftime("%Y-%m-%d") == date
        if day_mask.sum() == 0:
            raise ValueError(f"日期 {date} 无 1min 数据")
        day_cal = cal_series[day_mask]
    else:
        # Use last available day
        last_date = cal[-1].strftime("%Y-%m-%d")
        day_mask = cal_series.dt.strftime("%Y-%m-%d") == last_date
        day_cal = cal_series[day_mask]
        date = last_date

    start_time = str(day_cal.iloc[0])
    end_time = str(day_cal.iloc[-1])

    # Load model
    from qtrader.backend.core.engine.model_store import get_model_store
    store = get_model_store()

    if model_id:
        model = store.load_model(model_id)
        meta = store.get_meta(model_id)
    else:
        # Find latest HFLGBModel
        all_models = store.list_models()
        hf_models = [m for m in all_models if m.get("model_class") == "HFLGBModel"]
        if not hf_models:
            raise ValueError("无可用 HFLGBModel 模型，请先训练高频模型")
        meta = hf_models[-1]
        model = store.load_model(meta["model_id"])
        model_id = meta["model_id"]

    # Build dataset for prediction using the same handler as HFLGBModel training.
    # 注意：必须与 trainer.py 中 HFLGBModel 的训练配置一致（DataHandlerLP + dict config +
    # swap_level=False），否则列结构与模型期望不匹配。HighFreqHandler 返回单级列名，
    # RobustZScoreNorm 期望 MultiIndex（feature/label），会导致 KeyError: 'feature'。
    from qlib.utils import init_instance_by_config
    from qlib.contrib.data.highfreq_handler import HighFreqHandler as _HFH

    # Use a wider range for handler fitting
    cal_dates = sorted(cal_series.dt.strftime("%Y-%m-%d").unique())
    fit_start = str(cal[0])
    fit_end = start_time

    _tmp = _HFH.__new__(_HFH)
    feature_fields, feature_names = _tmp.get_feature_config()
    label_fields = ["Ref($close, -10)/$close - 1"]
    label_names = ["LABEL0"]

    handler_config = {
        "class": "DataHandlerLP",
        "module_path": "qlib.data.dataset.handler",
        "kwargs": {
            "start_time": fit_start,
            "end_time": end_time,
            "instruments": [symbol.upper()],
            "data_loader": {
                "class": "QlibDataLoader",
                "kwargs": {
                    "config": {
                        "feature": (feature_fields, feature_names),
                        "label": (label_fields, label_names),
                    },
                    "swap_level": False,
                    "freq": "1min",
                },
            },
            "infer_processors": [
                {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": False, "fit_start_time": fit_start, "fit_end_time": fit_end}},
                {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
            ],
            "learn_processors": [
                {"class": "DropnaLabel"},
                {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
            ],
        },
    }

    dataset_config = {
        "class": "DatasetH",
        "module_path": "qlib.data.dataset",
        "kwargs": {
            "handler": handler_config,
            "segments": {
                "train": (fit_start, fit_end),
                "test": (start_time, end_time),
            },
        },
    }

    dataset = init_instance_by_config(dataset_config)

    # Generate predictions
    # HFLGBModel.predict(dataset) 不接受 segment 参数（内部硬编码 prepare("test")），
    # 此处传 segment 会抛 TypeError，故省略。
    pred = model.predict(dataset)

    # Get actual price data for the day
    df_price = D.features(
        [symbol.upper()],
        ["$close", "$volume"],
        start_time=start_time,
        end_time=end_time,
        freq="1min",
    )

    # Align prediction with price
    if isinstance(pred, pd.Series):
        pred_df = pred.to_frame("score")
    else:
        pred_df = pd.DataFrame({"score": pred})

    if isinstance(pred_df.index, pd.MultiIndex):
        pred_df = pred_df.xs(symbol.upper(), level="instrument")
    if isinstance(df_price.index, pd.MultiIndex):
        df_price = df_price.xs(symbol.upper(), level="instrument")

    pred_df.index = pd.to_datetime(pred_df.index)
    df_price.index = pd.to_datetime(df_price.index)

    merged = df_price.join(pred_df, how="inner").dropna(subset=["score"])

    # Build response
    actual = []
    predicted = []
    for ts, row in merged.iterrows():
        time_str = ts.strftime("%Y-%m-%d %H:%M:%S")
        actual.append({"time": time_str, "close": round(float(row["$close"]), 3)})
        predicted.append({"time": time_str, "score": round(float(row["score"]), 6)})

    # Signal summary
    if predicted:
        scores = [p["score"] for p in predicted]
        avg_score = sum(scores) / len(scores)
        latest_score = scores[-1]
        recent_10 = scores[-10:] if len(scores) >= 10 else scores
        recent_avg = sum(recent_10) / len(recent_10)

        direction = "看涨" if latest_score > avg_score else "看跌"
        strength = abs(latest_score - avg_score) / (max(scores) - min(scores) + 1e-8)
        strength_pct = min(round(strength * 100), 100)

        current_price = actual[-1]["close"] if actual else 0
        # Estimate target: score > 0 means expected up movement
        change_pct = round(latest_score * 100, 3)
        target_price = round(current_price * (1 + latest_score), 3)
    else:
        direction = "无数据"
        strength_pct = 0
        current_price = 0
        target_price = 0
        change_pct = 0
        avg_score = 0
        recent_avg = 0
        latest_score = 0

    return {
        "model_id": model_id,
        "symbol": symbol,
        "date": date,
        "total_bars": len(actual),
        "actual": actual,
        "predicted": predicted,
        "signal": {
            "direction": direction,
            "strength": strength_pct,
            "current_price": current_price,
            "target_price": target_price,
            "change_pct": change_pct,
            "latest_score": round(latest_score, 6),
            "avg_score": round(avg_score, 6),
        },
    }

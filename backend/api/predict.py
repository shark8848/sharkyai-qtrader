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


class PredictRequest(BaseModel):
    model_id: str
    symbol: str  # e.g. "SH600519"
    start_date: Optional[str] = None  # default: 6 months ago
    end_date: Optional[str] = None    # default: today


@router.get("/data_range")
async def get_data_range():
    """Return the available data date range."""
    try:
        import qlib
        from qlib.constant import REG_CN
        from pathlib import Path
        os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
        data_dir = str(Path.home() / ".qlib" / "qlib_data" / "cn_data")
        qlib.init(provider_uri=data_dir, region=REG_CN)
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

    try:
        result = _predict_single_stock(
            model_id=req.model_id,
            symbol=req.symbol,
            start_date=start_date,
            end_date=end_date,
            handler=meta.get("handler", "Alpha158"),
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

    import qlib
    from qlib.constant import REG_CN

    # 始终调用 qlib.init()（可重复调用，与 trainer 保持一致）
    from pathlib import Path
    data_dir = str(Path.home() / ".qlib" / "qlib_data" / "cn_data")
    qlib.init(provider_uri=data_dir, region=REG_CN)

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

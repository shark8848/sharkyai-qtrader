"""Training and backtest API routes."""

from fastapi import APIRouter, HTTPException, BackgroundTasks

from qtrader.backend.core.engine.trainer import trainer, TrainConfig
from qtrader.backend.core.engine.backtest import backtest_engine, BacktestConfig
from qtrader.backend.core.engine.evaluator import evaluator
from qtrader.backend.core.engine.model_store import get_model_store

router = APIRouter()

# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

@router.get("/train/config")
async def get_train_config():
    """Get default training configuration."""
    return {
        "model_class": "LGBModel",
        "handler": "Alpha158",
        "market": "csi300",
        "train_range": ["2008-01-01", "2014-12-31"],
        "valid_range": ["2015-01-01", "2016-12-31"],
        "test_range": ["2017-01-01", "2020-08-01"],
        "benchmark": "SH000300",
        "available_models": ["LGBModel", "XGBModel", "CatBoostModel", "LinearModel"],
        "available_handlers": ["Alpha158", "Alpha360"],
        "available_markets": ["csi300", "csi500", "csi800", "csi100"],
    }


@router.post("/train/config")
async def save_train_config(config: dict):
    """Save training configuration."""
    return {"message": "Config saved", "config": config}


@router.post("/train/start")
async def start_training(config: TrainConfig, background_tasks: BackgroundTasks):
    """Start a training job (async)."""
    job = trainer.submit(config)
    background_tasks.add_task(trainer.run, job.job_id)
    return {"message": "Training started", "job_id": job.job_id, "status": job.status.value}


@router.get("/train/status/{job_id}")
async def get_training_status(job_id: str):
    """Query training job status with real-time progress."""
    job = trainer.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@router.get("/train/jobs")
async def list_training_jobs():
    """List all training jobs."""
    return [j.to_dict() for j in trainer.list_jobs()]


# ---------------------------------------------------------------------------
# Model Store
# ---------------------------------------------------------------------------

@router.get("/models")
async def list_models():
    """List all saved models with version info."""
    store = get_model_store()
    return store.list_models()


@router.get("/models/{model_id}")
async def get_model_detail(model_id: str):
    """Get model metadata by model_id (e.g. model_v1)."""
    store = get_model_store()
    meta = store.get_meta(model_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    return meta


@router.get("/models/by-job/{job_id}")
async def get_model_by_job(job_id: str):
    """Find model by training job_id."""
    store = get_model_store()
    meta = store.find_by_job(job_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"No model found for job {job_id}")
    return meta


@router.delete("/models/{model_id}")
async def delete_model(model_id: str):
    """Delete a saved model."""
    store = get_model_store()
    meta = store.get_meta(model_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")
    store.delete_model(model_id)
    return {"message": f"Model {model_id} deleted"}


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

@router.post("/backtest/run")
async def run_backtest(config: BacktestConfig, background_tasks: BackgroundTasks):
    """Execute a backtest (async)."""
    result = backtest_engine.submit(config)
    background_tasks.add_task(backtest_engine.run, result.job_id)
    return {"message": "Backtest started", "job_id": result.job_id, "status": result.status}


@router.get("/backtest/result/{job_id}")
async def get_backtest_result(job_id: str):
    """Get backtest results with charts."""
    result = backtest_engine.get_result(job_id)
    if not result:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return {
        "job_id": result.job_id,
        "status": result.status,
        "created_at": result.created_at,
        "finished_at": result.finished_at,
        "error": result.error,
        "metrics": {
            "annual_return": result.annual_return,
            "sharpe": result.sharpe,
            "max_drawdown": result.max_drawdown,
            "information_ratio": result.information_ratio,
            "calmar": result.calmar,
        },
        "charts": {
            "equity_curve": result.equity_curve,
            "drawdown_curve": result.drawdown_curve,
        },
    }


@router.post("/backtest/compare")
async def compare_strategies(job_ids: list[str]):
    """Compare multiple backtest results."""
    results = []
    for jid in job_ids:
        r = backtest_engine.get_result(jid)
        if r:
            results.append({
                "job_id": r.job_id,
                "status": r.status,
                "annual_return": r.annual_return,
                "sharpe": r.sharpe,
                "max_drawdown": r.max_drawdown,
                "information_ratio": r.information_ratio,
                "calmar": r.calmar,
            })
    return {"job_ids": job_ids, "comparison": results}


@router.get("/backtest/jobs")
async def list_backtest_jobs():
    """List all backtest jobs."""
    return [
        {
            "job_id": r.job_id,
            "status": r.status,
            "config": r.config.model_dump(),
            "created_at": r.created_at,
            "finished_at": r.finished_at,
        }
        for r in backtest_engine.list_results()
    ]

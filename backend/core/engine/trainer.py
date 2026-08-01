"""
Trainer: 桥接 qlib 模型训练生态
支持 LGBModel / XGBModel / CatBoostModel / LinearModel
通过 JSON 配置驱动，后台线程异步训练，状态可查询
实时进度 + WebSocket 推送
"""
import asyncio
import os
import uuid
import logging
import threading
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置模型
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class TrainConfig(BaseModel):
    model_class: str = "LGBModel"
    handler: str = "Alpha158"
    market: str = "csi300"
    train_range: list[str] = ["2008-01-01", "2014-12-31"]
    valid_range: list[str] = ["2015-01-01", "2016-12-31"]
    test_range: list[str] = ["2017-01-01", "2020-08-01"]
    model_kwargs: dict[str, Any] = {}


class LogEntry(BaseModel):
    time: str
    step: str
    level: str = "info"  # info | warn | error


class TrainJob:
    """训练任务（可变状态，线程安全）"""

    def __init__(self, job_id: str, config: TrainConfig):
        self.job_id = job_id
        self.config = config
        self.status: JobStatus = JobStatus.PENDING
        self.created_at: str = datetime.now().isoformat(timespec="seconds")
        self.finished_at: Optional[str] = None
        self.error: Optional[str] = None
        self.model_path: Optional[str] = None
        self.metrics: Optional[dict] = None
        # 实时进度
        self.progress: int = 0          # 0-100
        self.current_step: str = ""     # 当前步骤描述
        self.logs: list[dict] = []      # [{time, step, level}]
        self._lock = threading.Lock()

    def update_progress(self, progress: int, step: str, level: str = "info"):
        """线程安全地更新进度"""
        with self._lock:
            self.progress = progress
            self.current_step = step
            entry = {
                "time": datetime.now().strftime("%H:%M:%S"),
                "step": step,
                "level": level,
            }
            self.logs.append(entry)

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "job_id": self.job_id,
                "status": self.status.value,
                "created_at": self.created_at,
                "finished_at": self.finished_at,
                "error": self.error,
                "metrics": self.metrics,
                "progress": self.progress,
                "current_step": self.current_step,
                "logs": list(self.logs),
                "config": self.config.model_dump(),
            }


# ---------------------------------------------------------------------------
# 模型注册表
# ---------------------------------------------------------------------------

MODEL_REGISTRY: dict[str, dict] = {
    "LGBModel": {
        "class": "LGBModel",
        "module_path": "qlib.contrib.model.gbdt",
        "default_kwargs": {
            "loss": "mse",
            "colsample_bytree": 0.8879,
            "learning_rate": 0.0421,
            "subsample": 0.8789,
            "lambda_l1": 205.6999,
            "lambda_l2": 580.9768,
            "max_depth": 8,
            "num_leaves": 210,
            "num_threads": 20,
        },
    },
    "XGBModel": {
        "class": "XGBModel",
        "module_path": "qlib.contrib.model.xgboost",
        "default_kwargs": {
            "max_depth": 8,
            "learning_rate": 0.05,
            "n_estimators": 800,
            "colsample_bytree": 0.8879,
            "subsample": 0.8789,
        },
    },
    "CatBoostModel": {
        "class": "CatBoostModel",
        "module_path": "qlib.contrib.model.catboost_model",
        "default_kwargs": {
            "iterations": 800,
            "learning_rate": 0.05,
            "depth": 8,
        },
    },
    "LinearModel": {
        "class": "LinearModel",
        "module_path": "qlib.contrib.model.linear",
        "default_kwargs": {},
    },
}

HANDLER_REGISTRY: dict[str, dict] = {
    "Alpha158": {
        "class": "Alpha158",
        "module_path": "qlib.contrib.data.handler",
    },
    "Alpha360": {
        "class": "Alpha360",
        "module_path": "qlib.contrib.data.handler",
    },
}


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------

class Trainer:
    """异步训练管理器"""

    def __init__(self, data_dir: str = None):
        self._jobs: dict[str, TrainJob] = {}
        self._data_dir = data_dir or str(Path.home() / ".qlib" / "qlib_data" / "cn_data")
        self._qlib_initialized = False

    def _ensure_qlib(self):
        """延迟初始化 qlib"""
        if not self._qlib_initialized:
            os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
            import qlib
            from qlib.constant import REG_CN
            qlib.init(provider_uri=self._data_dir, region=REG_CN)
            self._qlib_initialized = True
            logger.info("Qlib initialized for training")

    def submit(self, config: TrainConfig) -> TrainJob:
        """提交训练任务"""
        job_id = f"train_{uuid.uuid4().hex[:12]}"
        job = TrainJob(job_id=job_id, config=config)
        self._jobs[job_id] = job
        return job

    async def run(self, job_id: str):
        """在后台线程中执行训练"""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.status = JobStatus.RUNNING
        job.update_progress(0, "任务已提交，等待执行...")

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, self._run_training, job)
            job.status = JobStatus.SUCCESS
            job.metrics = result.get("metrics")
            job.model_path = result.get("model_path")
            job.update_progress(100, "训练完成")
        except Exception as e:
            logger.exception(f"Training job {job_id} failed")
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.update_progress(job.progress, f"训练失败: {e}", level="error")
        finally:
            job.finished_at = datetime.now().isoformat(timespec="seconds")

    def _run_training(self, job: TrainJob) -> dict:
        """同步训练逻辑（在线程中执行）"""
        job.update_progress(5, "正在初始化 Qlib ...")
        self._ensure_qlib()

        from qlib.utils import init_instance_by_config
        from qlib.workflow import R
        from qlib.workflow.record_temp import SignalRecord, PortAnaRecord, SigAnaRecord

        config = job.config

        # 构建模型配置
        model_info = MODEL_REGISTRY.get(config.model_class, MODEL_REGISTRY["LGBModel"])
        model_kwargs = {**model_info["default_kwargs"], **config.model_kwargs}
        model_config = {
            "class": model_info["class"],
            "module_path": model_info["module_path"],
            "kwargs": model_kwargs,
        }
        job.update_progress(10, f"模型配置: {config.model_class}")

        # 构建数据集配置
        handler_info = HANDLER_REGISTRY.get(config.handler, HANDLER_REGISTRY["Alpha158"])
        dataset_config = {
            "class": "DatasetH",
            "module_path": "qlib.data.dataset",
            "kwargs": {
                "handler": {
                    "class": handler_info["class"],
                    "module_path": handler_info["module_path"],
                    "kwargs": {
                        "start_time": config.train_range[0],
                        "end_time": config.test_range[1],
                        "fit_start_time": config.train_range[0],
                        "fit_end_time": config.train_range[1],
                        "instruments": config.market,
                    },
                },
                "segments": {
                    "train": tuple(config.train_range),
                    "valid": tuple(config.valid_range),
                    "test": tuple(config.test_range),
                },
            },
        }

        job.update_progress(15, f"加载数据集 {config.handler} | 股票池 {config.market} ...")

        model = init_instance_by_config(model_config)
        job.update_progress(25, "模型实例化完成")

        dataset = init_instance_by_config(dataset_config)
        job.update_progress(35, f"数据集加载完成 (训练集 {config.train_range[0]}~{config.train_range[1]})")

        # 训练
        job.update_progress(40, "开始训练模型 ...")
        with R.start(experiment_name=f"qtrader_{job.job_id}"):
            model.fit(dataset)
            job.update_progress(60, "模型训练完成，生成预测信号 ...")

            recorder = R.get_recorder()
            sr = SignalRecord(model, dataset, recorder)
            sr.generate()
            job.update_progress(75, "预测信号生成完成")

            sar = SigAnaRecord(recorder)
            sar.generate()
            job.update_progress(90, "信号分析完成")

        # 尝试提取分析指标
        metrics = self._extract_metrics(recorder)

        job.update_progress(95, "保存结果 ...")
        return {"metrics": metrics, "model_path": None}

    def _extract_metrics(self, recorder) -> dict:
        """从 recorder 提取分析数据"""
        try:
            analysis = recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
            if hasattr(analysis, "to_dict"):
                return {"analysis": "available"}
        except Exception:
            pass
        return {"status": "completed"}

    def get_job(self, job_id: str) -> Optional[TrainJob]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[TrainJob]:
        return list(self._jobs.values())


# 全局单例
trainer = Trainer()

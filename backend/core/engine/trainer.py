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
    train_range: list[str] = ["2019-01-01", "2024-12-31"]
    valid_range: list[str] = ["2025-01-01", "2025-06-30"]
    test_range: list[str] = ["2025-07-01", "2026-07-31"]
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
        # 训练曲线（每 epoch 的指标，TensorBoard 经典指标）
        self.train_history: dict = {
            "epochs": [], "train_loss": [], "valid_loss": [],
            "train_ic": [], "valid_ic": [], "lr": [], "grad_norm": [],
        }
        self._lock = threading.Lock()
        self._on_update = None          # 进度更新回调 (用于持久化)

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
        # 触发持久化回调
        if self._on_update:
            try:
                self._on_update(self)
            except Exception:
                pass

    def to_dict(self) -> dict:
        import math
        # Sanitize metrics: replace NaN/Inf with None for JSON compliance
        clean_metrics = None
        if self.metrics:
            clean_metrics = {
                k: (None if isinstance(v, float) and (math.isnan(v) or math.isinf(v)) else v)
                for k, v in self.metrics.items()
            }
        with self._lock:
            return {
                "job_id": self.job_id,
                "status": self.status.value,
                "created_at": self.created_at,
                "finished_at": self.finished_at,
                "error": self.error,
                "metrics": clean_metrics,
                "model_path": self.model_path,
                "progress": self.progress,
                "current_step": self.current_step,
                "logs": list(self.logs),
                "config": self.config.model_dump(),
                "train_history": self.train_history,
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
    "DEnsembleModel": {
        "class": "DEnsembleModel",
        "module_path": "qlib.contrib.model.double_ensemble",
        "default_kwargs": {
            "base_model": "gbm",
            "loss": "mse",
            "num_models": 6,
            "enable_sr": True,
            "enable_fs": True,
            "decay": 0.5,
            "epochs": 100,
        },
    },
    "GRU": {
        "class": "GRU",
        "module_path": "qlib.contrib.model.pytorch_gru",
        "default_kwargs": {
            "d_feat": 158,
            "hidden_size": 64,
            "num_layers": 2,
            "dropout": 0.0,
            "n_epochs": 200,
            "lr": 0.001,
            "batch_size": 2000,
            "early_stop": 20,
            "metric": "ic",
            "GPU": -1,
        },
    },
    "LSTM": {
        "class": "LSTM",
        "module_path": "qlib.contrib.model.pytorch_lstm",
        "default_kwargs": {
            "d_feat": 158,
            "hidden_size": 64,
            "num_layers": 2,
            "dropout": 0.0,
            "n_epochs": 200,
            "lr": 0.001,
            "batch_size": 2000,
            "early_stop": 20,
            "metric": "ic",
            "GPU": -1,
        },
    },
    "ALSTM": {
        "class": "ALSTM",
        "module_path": "qlib.contrib.model.pytorch_alstm",
        "default_kwargs": {
            "d_feat": 158,
            "hidden_size": 64,
            "num_layers": 2,
            "dropout": 0.0,
            "n_epochs": 200,
            "lr": 0.001,
            "batch_size": 2000,
            "early_stop": 20,
            "metric": "ic",
            "GPU": -1,
        },
    },
    "TransformerModel": {
        "class": "TransformerModel",
        "module_path": "qlib.contrib.model.pytorch_transformer",
        "default_kwargs": {
            "d_feat": 158,
            "d_model": 64,
            "nhead": 2,
            "num_layers": 2,
            "dropout": 0.0,
            "n_epochs": 200,
            "lr": 0.0001,
            "batch_size": 2048,
            "early_stop": 5,
            "metric": "ic",
            "GPU": -1,
        },
    },
    "TCN": {
        "class": "TCN",
        "module_path": "qlib.contrib.model.pytorch_tcn",
        "default_kwargs": {
            "d_feat": 158,
            "n_chans": 128,
            "kernel_size": 5,
            "num_layers": 5,
            "dropout": 0.5,
            "n_epochs": 200,
            "lr": 0.0001,
            "batch_size": 2000,
            "early_stop": 20,
            "metric": "ic",
            "GPU": -1,
        },
    },
    "TabnetModel": {
        "class": "TabnetModel",
        "module_path": "qlib.contrib.model.pytorch_tabnet",
        "default_kwargs": {
            "d_feat": 158,
            "n_epochs": 200,
            "lr": 0.001,
            "batch_size": 2000,
            "early_stop": 20,
            "metric": "ic",
            "GPU": -1,
        },
    },
    "DNNModelPytorch": {
        "class": "DNNModelPytorch",
        "module_path": "qlib.contrib.model.pytorch_nn",
        "default_kwargs": {
            "lr": 0.001,
            "optimizer": "adam",
            "metric": "ic",
            "GPU": -1,
        },
    },
    "GATs": {
        "class": "GATs",
        "module_path": "qlib.contrib.model.pytorch_gats",
        "default_kwargs": {
            "d_feat": 158,
            "hidden_size": 64,
            "num_layers": 2,
            "dropout": 0.0,
            "n_epochs": 200,
            "lr": 0.001,
            "early_stop": 20,
            "base_model": "GRU",
            "metric": "ic",
            "GPU": -1,
        },
    },
    "SFM_Model": {
        "class": "SFM_Model",
        "module_path": "qlib.contrib.model.pytorch_sfm",
        "default_kwargs": {
            "d_feat": 158,
            "hidden_size": 64,
            "output_dim": 32,
            "freq_dim": 25,
            "n_epochs": 200,
            "lr": 0.001,
            "batch_size": 2000,
            "early_stop": 20,
            "metric": "ic",
            "GPU": -1,
        },
    },
    "HFLGBModel": {
        "class": "HFLGBModel",
        "module_path": "qlib.contrib.model.highfreq_gdbt_model",
        "default_kwargs": {
            "loss": "binary",
            "metric": ["binary_logloss", "auc"],
            "verbosity": -1,
            "learning_rate": 0.01,
            "max_depth": 8,
            "num_leaves": 150,
            "lambda_l1": 1.5,
            "lambda_l2": 1,
            "num_threads": 20,
        },
        "high_freq": True,
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
    "HighFreqHandler": {
        "class": "HighFreqHandler",
        "module_path": "qlib.contrib.data.highfreq_handler",
    },
}


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------

class Trainer:
    """异步训练管理器（支持持久化）"""

    def __init__(self, data_dir: str = None, job_store=None):
        self._jobs: dict[str, TrainJob] = {}
        self._data_dir = data_dir or str(Path.home() / ".qlib" / "qlib_data" / "cn_data")
        self._qlib_initialized = False
        # 训练信号量：同一时间只允许一个任务执行数据加载+训练，防止 Qlib 并发死锁
        self._train_semaphore = threading.Semaphore(1)
        # 持久化存储
        self._store = job_store
        if self._store is None:
            self._store = self._create_default_store()
        self._restore_jobs()

    @staticmethod
    def _create_default_store():
        """根据配置创建默认 JobStore"""
        try:
            from qtrader.backend.config import settings
            from qtrader.backend.core.engine.job_store import create_job_store
            if settings.job_store_backend in ("postgresql", "postgres", "pg"):
                return create_job_store("postgresql", dsn=settings.job_store_pg_dsn)
            else:
                return create_job_store("sqlite", db_path=settings.job_store_db_path)
        except Exception as e:
            logger.warning(f"Failed to create job store, using in-memory only: {e}")
            return None

    def _restore_jobs(self):
        """从存储恢复历史任务"""
        if self._store is None:
            return
        try:
            rows = self._store.load_all_jobs()
            for row in rows:
                job = self._row_to_job(row)
                if job:
                    job._on_update = lambda j: self._persist_job(j)
                    # running 状态的任务重启后标记为 failed
                    if job.status == JobStatus.RUNNING:
                        job.status = JobStatus.FAILED
                        job.error = "服务重启，任务中断"
                        job.finished_at = datetime.now().isoformat(timespec="seconds")
                    self._jobs[job.job_id] = job
            logger.info(f"Restored {len(self._jobs)} jobs from store")
        except Exception as e:
            logger.warning(f"Failed to restore jobs: {e}")

    def _row_to_job(self, row: dict) -> Optional[TrainJob]:
        """从存储行恢复 TrainJob"""
        try:
            config_data = row.get("config", {})
            if isinstance(config_data, str):
                import json
                config_data = json.loads(config_data)
            config = TrainConfig(**config_data)
            job = TrainJob(job_id=row["job_id"], config=config)
            job.status = JobStatus(row.get("status", "pending"))
            job.created_at = row.get("created_at", "")
            job.finished_at = row.get("finished_at")
            job.error = row.get("error")
            job.model_path = row.get("model_path")
            metrics = row.get("metrics")
            if isinstance(metrics, str):
                import json
                metrics = json.loads(metrics)
            job.metrics = metrics
            job.progress = row.get("progress", 0)
            job.current_step = row.get("current_step", "")
            logs = row.get("logs", [])
            if isinstance(logs, str):
                import json
                logs = json.loads(logs)
            job.logs = logs if isinstance(logs, list) else []
            # 恢复训练曲线
            history = row.get("train_history")
            if isinstance(history, str):
                import json
                try:
                    history = json.loads(history)
                except (json.JSONDecodeError, TypeError):
                    history = None
            if isinstance(history, dict) and "epochs" in history:
                job.train_history = history
            return job
        except Exception as e:
            logger.warning(f"Failed to restore job {row.get('job_id')}: {e}")
            return None

    def _persist_job(self, job: TrainJob):
        """持久化任务状态到存储"""
        if self._store is None:
            return
        try:
            self._store.save_job(job.to_dict())
        except Exception as e:
            logger.warning(f"Failed to persist job {job.job_id}: {e}")

    def _ensure_qlib(self, high_freq: bool = False):
        """延迟初始化 qlib"""
        os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
        import qlib
        from qlib.constant import REG_CN

        if high_freq:
            from pathlib import Path
            from qlib.contrib.ops.high_freq import DayLast, FFillNan, BFillNan, Date, Select, IsNull, IsInf, Cut
            hf_dir = str(Path.home() / ".qlib" / "qlib_data" / "cn_data_1min")
            qlib.init(
                provider_uri=hf_dir,
                region=REG_CN,
                custom_ops=[DayLast, FFillNan, BFillNan, Date, Select, IsNull, IsInf, Cut],
                expression_cache=None,  # 高频Select算子与DiskExpressionCache不兼容
                kernels=1,  # 单进程避免uvicorn内多进程死锁
            )
            logger.info("Qlib initialized for HIGH-FREQ training (1min)")
        elif not self._qlib_initialized:
            qlib.init(
                provider_uri=self._data_dir,
                region=REG_CN,
                expression_cache="DiskExpressionCache",
                kernels=min(os.cpu_count() or 4, 16),
            )
            self._qlib_initialized = True
            logger.info("Qlib initialized for training (expression cache enabled)")

    def submit(self, config: TrainConfig) -> TrainJob:
        """提交训练任务"""
        job_id = f"train_{uuid.uuid4().hex[:12]}"
        job = TrainJob(job_id=job_id, config=config)
        job._on_update = lambda j: self._persist_job(j)
        self._jobs[job_id] = job
        self._persist_job(job)
        return job

    async def run(self, job_id: str):
        """在后台线程中执行训练"""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.status = JobStatus.RUNNING
        job.update_progress(0, "任务已提交，等待执行...")
        self._persist_job(job)

        loop = asyncio.get_event_loop()
        try:
            # 信号量保证同一时间只有一个任务在加载数据+训练，防止 Qlib 并发死锁
            await loop.run_in_executor(None, self._train_semaphore.acquire)
            job.update_progress(1, "获得执行权，开始训练...")
            try:
                result = await loop.run_in_executor(None, self._run_training, job)
            finally:
                self._train_semaphore.release()
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
            self._persist_job(job)

    def _run_training(self, job: TrainJob) -> dict:
        """同步训练逻辑（在线程中执行）"""
        config = job.config
        model_info = MODEL_REGISTRY.get(config.model_class, MODEL_REGISTRY["LGBModel"])
        is_high_freq = model_info.get("high_freq", False)

        job.update_progress(5, "正在初始化 Qlib ...")
        self._ensure_qlib(high_freq=is_high_freq)

        from qlib.utils import init_instance_by_config
        from qlib.workflow import R
        from qlib.workflow.record_temp import SignalRecord, PortAnaRecord, SigAnaRecord

        # 构建模型配置
        model_kwargs = {**model_info["default_kwargs"], **config.model_kwargs}
        model_config = {
            "class": model_info["class"],
            "module_path": model_info["module_path"],
            "kwargs": model_kwargs,
        }
        job.update_progress(10, f"模型配置: {config.model_class}")

        # 构建数据集配置
        if is_high_freq:
            # High-freq: build grouped handler (feature + label) for HFLGBModel
            from qlib.contrib.data.highfreq_handler import HighFreqHandler as _HFH
            _tmp = _HFH.__new__(_HFH)
            feature_fields, feature_names = _tmp.get_feature_config()
            # Label: 10-min future return（匹配信号半衰期 10~20 bars）
            label_fields = ["Ref($close, -10)/$close - 1"]
            label_names = ["LABEL0"]

            handler_config = {
                "class": "DataHandlerLP",
                "module_path": "qlib.data.dataset.handler",
                "kwargs": {
                    "start_time": config.train_range[0],
                    "end_time": config.test_range[1],
                    "instruments": config.market,
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
                        {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": False, "fit_start_time": config.train_range[0], "fit_end_time": config.train_range[1]}},
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
                        "train": tuple(config.train_range),
                        "valid": tuple(config.valid_range),
                        "test": tuple(config.test_range),
                    },
                },
            }
        else:
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

        # NaN 处理策略（按模型类型）
        model_info = MODEL_REGISTRY.get(config.model_class, {})
        is_pytorch = "pytorch" in model_info.get("module_path", "")
        is_tree = config.model_class in ("LGBModel", "XGBModel", "DEnsembleModel")

        if config.model_class == "CatBoostModel":
            # CatBoost 的 RMSE 不允许目标列含 NaN
            job.update_progress(37, "正在清洗数据（移除 NaN 标签）...")
            nan_count = self._clean_dataset_nan(dataset)
            if nan_count > 0:
                job.update_progress(38, f"已移除 {nan_count} 条 NaN 标签数据")
            else:
                job.update_progress(38, "数据清洗完成，无 NaN 标签")
        elif config.model_class == "LinearModel" or is_pytorch:
            # LinearModel 内部 dropna() 会删除含 NaN 的行
            # PyTorch 模型（LSTM/GRU/Transformer等）无法处理 NaN 输入
            # Alpha158/360 的 CSZScoreNorm 处理器引入大量 NaN，需拦截 prepare()
            job.update_progress(37, "正在预处理 NaN（填充缺失值）...")
            self._fill_feature_nan(dataset)
            job.update_progress(38, "已启用自动 NaN 填充")
        elif is_tree:
            job.update_progress(38, "跳过 NaN 清洗（树模型内置处理）")
        else:
            # 未知模型类型，保守起见也做 NaN 填充
            job.update_progress(37, "正在预处理 NaN...")
            self._fill_feature_nan(dataset)
            job.update_progress(38, "已启用自动 NaN 填充")

        # 训练
        job.update_progress(40, "开始训练模型 ...")
        evals_result = {}

        # 对 PyTorch 模型，安装训练钩子捕获 Loss/IC/LR/梯度范数曲线
        restore_hooks = None
        if is_pytorch:
            restore_hooks = self._install_training_hooks(model, job)

        with R.start(experiment_name=f"qtrader_{job.job_id}"):
            try:
                model.fit(dataset, evals_result=evals_result)
            except TypeError:
                # 某些模型不支持 evals_result 参数
                model.fit(dataset)

            # 将 evals_result 写入 job.train_history
            self._capture_evals_result(evals_result, job, is_pytorch)
            job.update_progress(55, "模型训练完成，生成预测信号 ...")

            recorder = R.get_recorder()
            sr = SignalRecord(model, dataset, recorder)
            sr.generate()
            job.update_progress(65, "预测信号生成完成")

            sar = SigAnaRecord(recorder)
            sar.generate()
            job.update_progress(75, "信号分析完成")

            # 计算信号分析曲线（RankIC/ICIR/Long-Short/分层收益/换手率）
            job.update_progress(76, "计算信号分析曲线 ...")
            try:
                self._compute_signal_curves(model, dataset, job)
            except Exception as sc_err:
                logger.warning(f"信号曲线计算失败: {sc_err}")

            # 高频模型：计算高频专用指标（单位换手收益/成本分解/半衰期/容量曲线）
            if is_high_freq:
                job.update_progress(77, "计算高频专用指标 ...")
                try:
                    self._compute_hf_metrics(model, dataset, job)
                except Exception as hf_err:
                    logger.warning(f"高频指标计算失败: {hf_err}")

            # 组合回测分析（可能因 qlib 版本兼容性问题失败，不影响模型训练结果）
            job.update_progress(78, "正在执行组合回测分析 ...")
            try:
                port_analysis_config = {
                    # 回测执行器：模拟逐日交易
                    "executor": {
                        "class": "SimulatorExecutor",
                        "module_path": "qlib.backtest.executor",
                        "kwargs": {
                            "time_per_step": "day",           # 每步时间粒度（日级调仓）
                            "generate_portfolio_metrics": True, # 生成组合指标报告（收益/回撤/换手等）
                        },
                    },
                    # 交易策略：Top-K 淘汰制
                    "strategy": {
                        "class": "TopkDropoutStrategy",
                        "module_path": "qlib.contrib.strategy.signal_strategy",
                        "kwargs": {
                            "signal": (model, dataset),  # 信号来源：模型预测分
                            "topk": 30,     # 持仓数量：持有预测分最高的 30 只股票
                            "n_drop": 3,    # 每日淘汰数：最多替换 3 只（换手率上限 10%/日）
                        },
                    },
                    # 回测环境与交易成本
                    "backtest": {
                        "start_time": config.test_range[0],  # 回测起始日（= 测试集开始）
                        "end_time": config.test_range[1],    # 回测结束日（= 测试集结束）
                        "account": 100000000,      # 初始资金：1 亿元
                        "benchmark": "SH000300",   # 基准：沪深300指数（用于计算超额收益）
                        "exchange_kwargs": {
                            "freq": "day",              # 交易频率：日级
                            "limit_threshold": 0.095,   # 涨跌停阈值：9.5%（超过则无法成交）
                            "deal_price": "vwap",       # 成交价：用当日均价（比 close 更贴近实际）
                            "open_cost": 0.0003,        # 买入费率：万3（佣金）
                            "close_cost": 0.0013,       # 卖出费率：万13（印花税0.05% + 佣金万3 + 过户费）
                            "min_cost": 5,              # 最低手续费：5元/笔
                        },
                    },
                }
                par = PortAnaRecord(recorder, port_analysis_config, "day")
                par.generate()
                job.update_progress(90, "组合回测分析完成")

                # 用实际组合换手率替换信号级换手率
                try:
                    import pandas as pd
                    report_df = recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
                    if isinstance(report_df, pd.DataFrame) and "turnover" in report_df.columns:
                        real_to = report_df["turnover"].tolist()
                        curves = job.train_history.get("signal_curves")
                        if curves and "turnover" in curves:
                            n_sig = len(curves["turnover"])
                            n_bt = len(real_to)
                            # 对齐长度：回测天数可能略少于信号曲线天数
                            if n_bt >= n_sig:
                                curves["turnover"] = [round(float(x), 4) for x in real_to[:n_sig]]
                            else:
                                # 回测短于信号曲线：前部分用回测值，尾部补 None
                                aligned = [round(float(x), 4) for x in real_to]
                                aligned += [None] * (n_sig - n_bt)
                                curves["turnover"] = aligned
                            # 用实际换手率重算净 alpha
                            import numpy as _np
                            # 从 ls_cum 反推每日 ls 收益
                            ls_cum = curves.get("ls_cum", [])
                            if ls_cum:
                                ls_daily = _np.diff([0] + ls_cum)
                                to_arr = _np.array([x if x is not None else 0 for x in curves["turnover"][:len(ls_daily)]])
                                cost_rate = 0.0015
                                net_alpha = ls_daily[:len(to_arr)] - to_arr * cost_rate * 2
                                curves["net_alpha_cum"] = _np.cumsum(net_alpha).round(6).tolist()
                            logger.info(f"换手率已替换为实际组合回测值 (mean={_np.nanmean([x for x in curves['turnover'] if x is not None]):.2%})")
                except Exception as to_err:
                    logger.warning(f"替换实际换手率失败: {to_err}")

            except Exception as bt_err:
                logger.warning(f"组合回测分析失败（不影响模型训练）: {bt_err}")
                job.update_progress(90, f"组合回测跳过（{type(bt_err).__name__}），模型训练已完成")

        # 提取真实回测指标
        metrics = self._extract_metrics(recorder)

        # 保存模型权重
        job.update_progress(95, "保存模型 ...")
        # 移除训练钩子（实例级 patch），避免 pickle 局部函数失败
        if restore_hooks is not None:
            restore_hooks()
        model_meta = self._save_model(model, job, metrics)

        job.update_progress(98, "保存结果 ...")
        return {"metrics": metrics, "model_path": model_meta.get("model_file") if model_meta else None}

    def _save_model(self, model, job: TrainJob, metrics: dict) -> Optional[dict]:
        """保存训练好的模型到 ModelStore"""
        try:
            from qtrader.backend.core.engine.model_store import get_model_store
            store = get_model_store()
            meta = store.save_model(
                model=model,
                job_id=job.job_id,
                model_class=job.config.model_class,
                handler=job.config.handler,
                market=job.config.market,
                metrics=metrics,
                config=job.config.model_dump(),
            )
            logger.info(f"Model saved: {meta['model_id']} (version={meta['version']})")
            return meta
        except Exception as e:
            logger.warning(f"Failed to save model: {e}")
            return None

    def _clean_dataset_nan(self, dataset) -> int:
        """清洗数据集中的 NaN 标签行（仅修改 handler 内部数据）"""
        total_dropped = 0
        try:
            df = self._get_handler_df(dataset)
            if df is None:
                return 0
            label_cols = [c for c in df.columns if 'LABEL' in str(c).upper()]
            if not label_cols:
                return 0
            nan_mask = df[label_cols].isna().any(axis=1)
            total_dropped = int(nan_mask.sum())
            if total_dropped > 0:
                self._set_handler_df(dataset, df[~nan_mask])
                logger.info(f"Dropped {total_dropped} NaN rows from label")
        except Exception as e:
            logger.warning(f"NaN cleaning failed: {e}")
            total_dropped = 0
        return total_dropped

    def _extract_metrics(self, recorder) -> dict:
        """从 recorder 提取回测和信号分析指标"""
        metrics = {}
        # 1. 信号分析指标 (IC/ICIR)
        try:
            sig_metrics = recorder.list_metrics()
            if sig_metrics:
                for k in ['IC', 'ICIR', 'Rank IC', 'Rank ICIR']:
                    if k in sig_metrics:
                        metrics[k.lower().replace(' ', '_')] = round(sig_metrics[k], 4)
        except Exception as e:
            logger.warning(f"Failed to extract signal metrics: {e}")

        # 2. 组合回测指标 (年化收益/Sharpe/最大回撤/信息比率)
        try:
            pa = recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
            import pandas as pd
            if isinstance(pa, pd.DataFrame) and not pa.empty:
                # 查找收益列
                ret_col = None
                for col in ['excess_return_without_cost', 'excess_return_with_cost', 'return']:
                    if col in pa.columns:
                        ret_col = col
                        break
                if ret_col:
                    ret_series = pa[ret_col].dropna()
                    if len(ret_series) > 0:
                        from qlib.contrib.evaluate import risk_analysis
                        risk = risk_analysis(ret_series)
                        # 提取关键指标
                        if 'annualized_return' in risk.index:
                            ann_ret = float(risk.loc['annualized_return'].iloc[0]) if hasattr(risk.loc['annualized_return'], 'iloc') else float(risk.loc['annualized_return'])
                            metrics['annualized_return'] = round(ann_ret * 100, 2)
                        if 'max_drawdown' in risk.index:
                            mdd = float(risk.loc['max_drawdown'].iloc[0]) if hasattr(risk.loc['max_drawdown'], 'iloc') else float(risk.loc['max_drawdown'])
                            metrics['max_drawdown'] = round(mdd * 100, 2)
                        if 'information_ratio' in risk.index:
                            ir = float(risk.loc['information_ratio'].iloc[0]) if hasattr(risk.loc['information_ratio'], 'iloc') else float(risk.loc['information_ratio'])
                            metrics['information_ratio'] = round(ir, 2)
                        # 从 std 和 annualized_return 计算 Sharpe
                        if 'std' in risk.index and 'annualized_return' in risk.index:
                            std = float(risk.loc['std'].iloc[0]) if hasattr(risk.loc['std'], 'iloc') else float(risk.loc['std'])
                            ann_ret_raw = float(risk.loc['annualized_return'].iloc[0]) if hasattr(risk.loc['annualized_return'], 'iloc') else float(risk.loc['annualized_return'])
                            annual_std = std * (252 ** 0.5)
                            if annual_std > 0:
                                metrics['sharpe'] = round(ann_ret_raw / annual_std, 2)
        except Exception as e:
            logger.warning(f"Failed to extract portfolio metrics: {e}")

        if not metrics:
            metrics = {"status": "completed"}
        return metrics

    def _install_training_hooks(self, model, job: TrainJob):
        """为 PyTorch 模型安装训练钩子，捕获 TensorBoard 经典指标：
        Loss / IC / Learning Rate / Gradient Norm。
        返回一个 restore 函数，保存模型前必须调用（移除 patch，避免 pickle 失败）。"""
        import math
        patches = []  # [(obj, attr_name), ...] 记录被覆盖的实例属性

        def safe(v):
            if v is None:
                return None
            v = float(v)
            return None if (math.isnan(v) or math.isinf(v)) else round(v, 6)

        # 用于在 epoch 内累积每个 batch 的梯度范数
        grad_buf = []

        # ---- 1. 拦截 optimizer.step 捕获梯度范数 + 学习率 ----
        optimizer = getattr(model, 'train_optimizer', None)
        if optimizer is not None and hasattr(optimizer, 'step'):
            original_step = optimizer.step
            patches.append((optimizer, 'step'))

            def patched_step(*args, **kwargs):
                # 更新前梯度已就绪，计算全局梯度范数 (L2)
                total = 0.0
                cur_lr = None
                for group in optimizer.param_groups:
                    if cur_lr is None:
                        cur_lr = group.get('lr')
                    for p in group['params']:
                        if p.grad is not None:
                            total += float(p.grad.data.norm(2).item()) ** 2
                grad_buf.append(total ** 0.5)
                with job._lock:
                    job.train_history.setdefault('_grad_buf', grad_buf)
                    job.train_history['_last_lr'] = cur_lr
                return original_step(*args, **kwargs)

            optimizer.step = patched_step

        # ---- 2. 拦截 test_epoch 捕获 Loss / IC，并在每个 epoch 汇总 LR 与梯度范数 ----
        if hasattr(model, 'test_epoch'):
            original_test_epoch = model.test_epoch
            patches.append((model, 'test_epoch'))
            call_counter = [0]

            def patched_test_epoch(data_x, data_y):
                loss, score = original_test_epoch(data_x, data_y)
                # fit() 每 epoch 调用两次 test_epoch：第1次=train，第2次=valid
                call_counter[0] += 1
                with job._lock:
                    if call_counter[0] % 2 == 1:
                        # train 调用 → 一个 epoch 的训练结束
                        job.train_history["epochs"].append(len(job.train_history["epochs"]) + 1)
                        job.train_history["train_loss"].append(safe(loss))
                        job.train_history["train_ic"].append(safe(score))
                        # 汇总本 epoch 的梯度范数（取均值）与学习率
                        if grad_buf:
                            job.train_history["grad_norm"].append(safe(sum(grad_buf) / len(grad_buf)))
                            grad_buf.clear()
                        else:
                            job.train_history["grad_norm"].append(None)
                        job.train_history["lr"].append(safe(job.train_history.get('_last_lr')))
                    else:
                        # valid 调用
                        job.train_history["valid_loss"].append(safe(loss))
                        job.train_history["valid_ic"].append(safe(score))
                return loss, score

            model.test_epoch = patched_test_epoch

        def restore():
            """移除实例级 patch，恢复类方法，使模型可被 pickle。"""
            for obj, attr in patches:
                try:
                    delattr(obj, attr)
                except AttributeError:
                    pass
            # 清理临时辅助键
            with job._lock:
                job.train_history.pop('_grad_buf', None)
                job.train_history.pop('_last_lr', None)

        return restore

    def _capture_evals_result(self, evals_result: dict, job: TrainJob, is_pytorch: bool):
        """将 evals_result 规范化写入 job.train_history"""
        import math
        if not evals_result:
            return

        def safe_val(v):
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return None
            return round(float(v), 6)

        if is_pytorch:
            # PyTorch: evals_result = {"train": [ic1, ic2, ...], "valid": [ic1, ...]}
            # loss 已由 _patch_test_epoch 捕获，这里补充 IC（如果 patch 未生效）
            if not job.train_history["train_ic"] and "train" in evals_result:
                train_scores = evals_result["train"]
                valid_scores = evals_result.get("valid", [])
                for i, s in enumerate(train_scores):
                    job.train_history["epochs"].append(i + 1)
                    job.train_history["train_ic"].append(safe_val(s))
                for i, s in enumerate(valid_scores):
                    job.train_history["valid_ic"].append(safe_val(s))
        else:
            # 树模型: evals_result 有两种格式
            # LightGBM: {"train": {"l2": [...]}, "valid": {"l2": [...]}}
            # XGBoost:  {"train": [v1, v2, ...], "valid": [v1, v2, ...]}  (已被 flatten)
            for split_name in ["train", "valid"]:
                if split_name not in evals_result:
                    continue
                split_data = evals_result[split_name]
                if isinstance(split_data, dict):
                    # LightGBM 格式：取第一个指标
                    metric_name = next(iter(split_data), None)
                    if metric_name is None:
                        continue
                    values = split_data[metric_name]
                elif isinstance(split_data, list):
                    # XGBoost 格式：已经是纯数值列表
                    values = split_data
                else:
                    continue
                for i, v in enumerate(values):
                    if split_name == "train":
                        job.train_history["epochs"].append(i + 1)
                        job.train_history["train_loss"].append(safe_val(v))
                    else:
                        job.train_history["valid_loss"].append(safe_val(v))

    def _compute_signal_curves(self, model, dataset, job: TrainJob):
        """计算5项信号分析曲线：RankIC、RankICIR、Long-Short净值、分层收益、换手率"""
        import pandas as pd
        import numpy as np
        from scipy.stats import spearmanr
        from qlib.data.dataset.handler import DataHandlerLP

        # 获取测试集预测和标签
        pred = model.predict(dataset)
        if isinstance(pred, pd.Series):
            pred = pred.to_frame("score")
        label_df = dataset.prepare("test", col_set="label", data_key=DataHandlerLP.DK_I)
        if isinstance(label_df, pd.DataFrame) and label_df.shape[1] == 1:
            label_series = label_df.iloc[:, 0]
        else:
            label_series = label_df

        # 合并 pred 和 label
        df = pd.DataFrame({"pred": pred.iloc[:, 0] if isinstance(pred, pd.DataFrame) else pred, "label": label_series})
        df = df.dropna()
        if df.empty or len(df.index.get_level_values(0).unique()) < 3:
            return

        dates = sorted(df.index.get_level_values(0).unique())
        daily_rank_ic = []
        daily_ls_ret = []  # Long-Short return
        daily_turnover = []
        decile_rets = {f"D{i}": [] for i in range(1, 11)}  # D1=bottom, D10=top
        prev_top_set = None

        for dt in dates:
            day_df = df.loc[dt]
            if len(day_df) < 10:
                daily_rank_ic.append(None)
                daily_ls_ret.append(None)
                daily_turnover.append(None)
                for k in decile_rets:
                    decile_rets[k].append(None)
                continue

            # 1. RankIC (Spearman)
            ic, _ = spearmanr(day_df["pred"], day_df["label"])
            daily_rank_ic.append(round(float(ic), 6) if not np.isnan(ic) else None)

            # 2. Long-Short: top 10% - bottom 10%
            n = len(day_df)
            k = max(int(n * 0.1), 1)
            sorted_df = day_df.sort_values("pred")
            bottom_ret = sorted_df["label"].iloc[:k].mean()
            top_ret = sorted_df["label"].iloc[-k:].mean()
            daily_ls_ret.append(round(float(top_ret - bottom_ret), 6))

            # 3. Decile returns
            try:
                day_df_copy = day_df.copy()
                day_df_copy["decile"] = pd.qcut(day_df_copy["pred"].rank(method="first"), 10, labels=False) + 1
                for d in range(1, 11):
                    mask = day_df_copy["decile"] == d
                    decile_rets[f"D{d}"].append(round(float(day_df_copy.loc[mask, "label"].mean()), 6) if mask.sum() > 0 else None)
            except Exception:
                for k2 in decile_rets:
                    decile_rets[k2].append(None)

            # 4. Turnover: 换手率 = |当日top集合 - 前一日top集合| / k
            top_set = set(sorted_df.index[-k:])
            if prev_top_set is not None and len(prev_top_set) > 0:
                turnover = 1.0 - len(top_set & prev_top_set) / max(len(top_set), 1)
                daily_turnover.append(round(float(turnover), 4))
            else:
                daily_turnover.append(None)
            prev_top_set = top_set

        # 计算滚动 RankIC 均值
        ic_series = pd.Series(daily_rank_ic)
        rank_ic_ma20 = ic_series.rolling(20, min_periods=1).mean().round(6).tolist()
        rank_ic_ma60 = ic_series.rolling(60, min_periods=1).mean().round(6).tolist()

        # 计算累计 RankICIR
        ic_arr = np.array([x if x is not None else 0 for x in daily_rank_ic])
        cum_mean = np.cumsum(ic_arr) / np.arange(1, len(ic_arr) + 1)
        cum_std = pd.Series(ic_arr).expanding().std().fillna(1).values
        cum_std[cum_std == 0] = 1
        rank_icir = (cum_mean / cum_std).round(4).tolist()

        # Long-Short 累计净值
        ls_arr = np.array([x if x is not None else 0 for x in daily_ls_ret])
        ls_cum = np.cumsum(ls_arr).round(6).tolist()

        # 分层累计收益
        decile_cum = {}
        for k3, vals in decile_rets.items():
            arr = np.array([x if x is not None else 0 for x in vals])
            decile_cum[k3] = np.cumsum(arr).round(6).tolist()

        # 成本后净alpha（单边 0.15% 费率）
        cost_rate = 0.0015
        to_arr = np.array([x if x is not None else 0 for x in daily_turnover])
        net_alpha = (ls_arr - to_arr * cost_rate * 2)
        net_alpha_cum = np.cumsum(net_alpha).round(6).tolist()

        # 存储
        date_strs = [str(d)[:10] for d in dates]
        job.train_history["signal_curves"] = {
            "dates": date_strs,
            "rank_ic": daily_rank_ic,
            "rank_ic_ma20": rank_ic_ma20,
            "rank_ic_ma60": rank_ic_ma60,
            "rank_icir": rank_icir,
            "ls_cum": ls_cum,
            "net_alpha_cum": net_alpha_cum,
            "turnover": daily_turnover,
            "decile_cum": decile_cum,
        }
        logger.info(f"Signal curves computed: {len(dates)} days")

    def _compute_hf_metrics(self, model, dataset, job: TrainJob):
        """计算高频专用指标：单位换手收益、成本分解、分桶成交后收益、信号半衰期、容量曲线"""
        import pandas as pd
        import numpy as np
        from scipy.stats import spearmanr
        from qlib.data.dataset.handler import DataHandlerLP
        from qlib.data import D

        # 成本参数（A股高频口径）
        FEE_RATE = 0.0003       # 手续费 单边万3
        SLIPPAGE_RATE = 0.0005  # 滑点 单边5bp
        IMPACT_COEF = 0.1       # 冲击系数（平方根冲击模型）

        pred = model.predict(dataset)
        if isinstance(pred, pd.Series):
            pred = pred.to_frame("score")
        label_df = dataset.prepare("test", col_set="label", data_key=DataHandlerLP.DK_I)
        label_series = label_df.iloc[:, 0] if isinstance(label_df, pd.DataFrame) else label_df

        df = pd.DataFrame({"pred": pred.iloc[:, 0], "label": label_series}).dropna()
        if df.empty:
            return

        # 按 bar 级别横截面分组（每个 datetime = 一个横截面）
        cs_dts = sorted(df.index.get_level_values(1).unique())
        cs_data = {dt: grp.droplevel(1) for dt, grp in df.groupby(level=1) if len(grp) >= 10}
        if len(cs_data) < 5:
            return
        cs_dts = sorted(cs_data.keys())
        n_bars = len(cs_dts)

        stocks = sorted(df.index.get_level_values(0).unique())
        stock_pos = {s: i for i, s in enumerate(stocks)}
        n_stocks = len(stocks)
        k = max(int(n_stocks * 0.1), 1)

        rank_ic_list = []
        ls_ret_list = []
        top_mask = np.zeros((n_bars, n_stocks), dtype=bool)
        decile_sum = np.zeros((n_bars, 10))
        decile_cnt = np.zeros((n_bars, 10), dtype=int)

        for i, dt in enumerate(cs_dts):
            day = cs_data[dt]
            p = day["pred"].values
            l = day["label"].values
            # RankIC
            ic, _ = spearmanr(p, l)
            rank_ic_list.append(float(ic) if not np.isnan(ic) else 0.0)
            # Long-Short
            order = np.argsort(p)
            ls_ret_list.append(float(l[order[-k:]].mean() - l[order[:k]].mean()))
            # Top-k 持仓
            for s in day.index[order[-k:]]:
                pos = stock_pos.get(s)
                if pos is not None:
                    top_mask[i, pos] = True
            # 分桶收益
            ranks = pd.Series(p).rank(method="first").values
            bins = np.minimum((ranks / (len(p) + 1) * 10).astype(int), 9)
            for b in range(10):
                m = bins == b
                decile_cnt[i, b] = int(m.sum())
                decile_sum[i, b] = float(l[m].sum()) if m.any() else 0.0

        # 换手率（bar 级别）— 原始信号换手
        turnover_list = [None]
        for i in range(1, n_bars):
            prev, cur = top_mask[i - 1], top_mask[i]
            if prev.any() and cur.any():
                turnover_list.append(round(float(1.0 - (prev & cur).sum() / max(cur.sum(), 1)), 4))
            else:
                turnover_list.append(None)

        # 持仓缓冲：模拟实际执行（每 REBALANCE_INTERVAL bars 调仓，仅替换跌出 top 2k 的持仓）
        REBALANCE_INTERVAL = 5  # 每 5 bars 调仓一次
        BUFFER_ZONE = 2  # 持仓保护带：跌出 top k*BUFFER_ZONE 才移除
        buffered_turnover_list = [None]
        held = top_mask[0].copy() if n_bars > 0 else np.zeros(n_stocks, dtype=bool)
        buffered_k = int(held.sum())
        for i in range(1, n_bars):
            if i % REBALANCE_INTERVAL == 0:
                signal_top = top_mask[i]
                # 保护带：当前持仓只要仍在 top k*BUFFER_ZONE 内就保留
                order_i = np.argsort(cs_data[cs_dts[i]]["pred"].values)
                buffer_k = min(buffered_k * BUFFER_ZONE, n_stocks)
                signal_buffer = np.zeros(n_stocks, dtype=bool)
                for s in cs_data[cs_dts[i]].index[order_i[-buffer_k:]]:
                    pos = stock_pos.get(s)
                    if pos is not None:
                        signal_buffer[pos] = True
                # 保留仍在 buffer 区内的持仓，替换跌出的
                keep = held & signal_buffer
                n_to_replace = buffered_k - keep.sum()
                if n_to_replace > 0:
                    # 从 signal_top 中补充未持有的
                    candidates = signal_top & (~held)
                    cand_idx = np.where(candidates)[0][:n_to_replace]
                    new_held = keep.copy()
                    new_held[cand_idx] = True
                    # 如果候选不足，从 buffer 区补充
                    if new_held.sum() < buffered_k:
                        extra = signal_buffer & (~new_held)
                        extra_idx = np.where(extra)[0][:buffered_k - int(new_held.sum())]
                        new_held[extra_idx] = True
                    to = float(1.0 - keep.sum() / max(buffered_k, 1))
                    held = new_held
                else:
                    to = 0.0
                buffered_turnover_list.append(round(to, 4))
            else:
                buffered_turnover_list.append(0.0)  # 非调仓 bar 不交易

        ls_arr = np.array(ls_ret_list)
        to_arr = np.array([t if t is not None else 0.0 for t in turnover_list])
        avg_to = float(to_arr[1:].mean()) if n_bars > 1 else 0.0
        # 缓冲后平均换手（按调仓 bar 平均）
        buf_to_arr = np.array([t if t is not None else 0.0 for t in buffered_turnover_list])
        rebal_count = max(int(np.sum(buf_to_arr > 0)), 1)
        avg_buf_to = float(buf_to_arr.sum() / rebal_count)  # 每次调仓的平均换手
        avg_buf_to_per_bar = float(buf_to_arr.mean())  # 摊薄到每 bar

        # 1. 单位换手收益（bp per 1% turnover）— 使用缓冲后换手
        mean_ls_bp = float(ls_arr.mean()) * 1e4
        edge_per_to = round(mean_ls_bp / (avg_buf_to * 100), 4) if avg_buf_to > 1e-8 else None

        # 2. 成本分解（基于缓冲后换手率，摊薄到每 bar）
        fee_cost = avg_buf_to_per_bar * FEE_RATE * 2
        slip_cost = avg_buf_to_per_bar * SLIPPAGE_RATE * 2
        impact_cost = IMPACT_COEF * (avg_buf_to_per_bar ** 2)
        cost_breakdown = {
            "fee": round(fee_cost * 1e4, 4),
            "slippage": round(slip_cost * 1e4, 4),
            "impact": round(impact_cost * 1e4, 4),
            "gross_alpha_bp": round(mean_ls_bp, 4),
            "net_alpha_bp": round((mean_ls_bp - (fee_cost + slip_cost + impact_cost) * 1e4), 4),
            "raw_turnover": round(avg_to, 4),
            "buffered_turnover": round(avg_buf_to, 4),
            "rebalance_interval": REBALANCE_INTERVAL,
        }

        # 3. 分桶成交后收益（bp/bar，扣除执行成本）
        with np.errstate(divide="ignore", invalid="ignore"):
            decile_avg = np.where(decile_cnt > 0, decile_sum / np.maximum(decile_cnt, 1), 0.0)
        exec_cost_per_bar = (FEE_RATE + SLIPPAGE_RATE) * 2  # 单次建仓双边成本
        decile_net_bp = [round(float(decile_avg[:, b].mean()) * 1e4 - exec_cost_per_bar * 1e4, 4) for b in range(10)]

        # 4. 信号半衰期：加载原始收盘价计算多 horizon 前向收益
        test_start = str(cs_dts[0])[:10]
        test_end = str(cs_dts[-1])[:10]
        instruments = list(stocks)
        horizons = [1, 2, 5, 10, 20]
        half_life = {"horizons": horizons, "top_decile": [], "ls": []}
        avg_vol_per_bar = 5e7  # 默认假设

        try:
            raw_df = D.features(instruments, ["$close"], start_time=test_start, end_time=test_end, freq="1min")
            close_wide = raw_df.reset_index().pivot(index="datetime", columns="instrument", values=raw_df.columns[0])
            common_dts = [dt for dt in cs_dts if dt in close_wide.index]
            close_mat = close_wide.loc[common_dts, stocks].values
            dt_pos = {dt: i for i, dt in enumerate(common_dts)}

            for h in horizons:
                top_rets, ls_rets = [], []
                for i, dt in enumerate(cs_dts):
                    cp = dt_pos.get(dt)
                    if cp is None or cp + h >= len(common_dts):
                        continue
                    p0 = close_mat[cp]
                    p1 = close_mat[cp + h]
                    valid = np.isfinite(p0) & np.isfinite(p1) & (p0 > 0)
                    if valid.sum() < 10:
                        continue
                    fwd = np.where(valid, p1 / np.where(p0 > 0, p0, 1) - 1, np.nan)
                    tops = top_mask[i] & valid
                    bots = (~top_mask[i]) & valid
                    if tops.sum() > 0:
                        tr = float(np.nanmean(np.where(tops, fwd, np.nan)))
                        if np.isfinite(tr):
                            top_rets.append(tr)
                    if tops.sum() > 0 and bots.sum() > 0:
                        br = float(np.nanmean(np.where(bots, fwd, np.nan)))
                        if np.isfinite(br):
                            ls_rets.append(tr - br)
                half_life["top_decile"].append(round(float(np.mean(top_rets)) * 1e4, 4) if top_rets else None)
                half_life["ls"].append(round(float(np.mean(ls_rets)) * 1e4, 4) if ls_rets else None)

            # 5. 容量曲线：加载成交量估算市场容量
            try:
                vol_df = D.features(instruments, ["If(IsNull($volume), 0, $volume)"],
                                    start_time=test_start, end_time=test_end, freq="1min")
                vol_wide = vol_df.reset_index().pivot(index="datetime", columns="instrument", values=vol_df.columns[0])
                vol_mat = vol_wide.reindex(index=close_wide.index, columns=stocks).values
                price_mat = close_wide[stocks].values
                with np.errstate(divide="ignore", invalid="ignore"):
                    tval = np.where(np.isfinite(vol_mat) & np.isfinite(price_mat), vol_mat * price_mat, np.nan)
                avg_vol_per_bar = float(np.nanmean(np.nansum(tval, axis=1)))
                if not np.isfinite(avg_vol_per_bar) or avg_vol_per_bar <= 0:
                    avg_vol_per_bar = 5e7
            except Exception:
                pass
        except Exception as hl_err:
            logger.warning(f"半衰期/容量计算跳过: {hl_err}")

        aum_levels = [0.1, 0.5, 1, 5, 10, 50, 100, 500]  # 亿元
        capacity = {"aum": aum_levels, "net_alpha_bp": []}
        for aum in aum_levels:
            participation = (aum * 1e8 / n_stocks) / max(avg_vol_per_bar, 1.0)
            cost = (FEE_RATE + SLIPPAGE_RATE) * 2 + IMPACT_COEF * np.sqrt(max(participation, 0))
            capacity["net_alpha_bp"].append(round(mean_ls_bp - cost * 1e4, 4))

        job.train_history["hf_metrics"] = {
            "n_bars": n_bars,
            "n_stocks": n_stocks,
            "avg_turnover": round(avg_buf_to, 4),
            "raw_turnover": round(avg_to, 4),
            "rebalance_interval": REBALANCE_INTERVAL,
            "edge_per_turnover_bp": edge_per_to,
            "cost_breakdown": cost_breakdown,
            "decile_net_bp": decile_net_bp,
            "half_life": half_life,
            "capacity": capacity,
            "rank_ic_ma": pd.Series(rank_ic_list).rolling(20, min_periods=1).mean().round(6).tolist(),
            "ls_cum": np.cumsum(ls_arr).round(6).tolist(),
            "bars_idx": list(range(n_bars)),
        }
        logger.info(f"HF metrics computed: {n_bars} bars x {n_stocks} stocks")

    def _fill_feature_nan(self, dataset) -> int:
        """拦截 dataset.prepare()，在返回数据前填充 NaN（PyTorch/Linear 模型需要）"""
        original_prepare = dataset.prepare
        fill_count = [0]

        def _fill_df(df):
            import pandas as pd
            if isinstance(df, pd.DataFrame) and not df.empty:
                nan_count = int(df.isna().sum().sum())
                if nan_count > 0:
                    fill_count[0] += nan_count
                    return df.ffill().bfill().fillna(0)
            return df

        def patched_prepare(*args, **kwargs):
            result = original_prepare(*args, **kwargs)
            # prepare() 可能返回单个 DataFrame 或 DataFrame 列表
            if isinstance(result, list):
                return [_fill_df(item) for item in result]
            return _fill_df(result)

        dataset.prepare = patched_prepare
        logger.info("Patched dataset.prepare() to auto-fill NaN (handles list & single DataFrame)")
        return -1  # -1 表示已启用自动填充模式

    @staticmethod
    def _get_handler_df(dataset):
        """获取 handler 的内部 DataFrame（兼容 .df 和 ._data）"""
        handler = getattr(dataset, 'handler', None)
        if handler is None:
            return None
        # Alpha158/Alpha360 存在 _data 属性
        if hasattr(handler, '_data'):
            import pandas as pd
            d = handler._data
            if isinstance(d, pd.DataFrame) and not d.empty:
                return d
        # 其他 handler 可能用 .df
        if hasattr(handler, 'df'):
            return handler.df
        return None

    @staticmethod
    def _set_handler_df(dataset, new_df):
        """设置 handler 的内部 DataFrame"""
        handler = getattr(dataset, 'handler', None)
        if handler is None:
            return
        if hasattr(handler, '_data'):
            handler._data = new_df
        elif hasattr(handler, 'df'):
            handler.df = new_df

    def get_job(self, job_id: str) -> Optional[TrainJob]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[TrainJob]:
        return list(self._jobs.values())

    def delete_job(self, job_id: str) -> bool:
        """删除训练任务（内存 + 持久化）"""
        job = self._jobs.pop(job_id, None)
        if self._store:
            try:
                self._store.delete_job(job_id)
            except Exception:
                pass
        return job is not None


# 全局单例
trainer = Trainer()

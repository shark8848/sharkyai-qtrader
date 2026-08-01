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
        with self._lock:
            return {
                "job_id": self.job_id,
                "status": self.status.value,
                "created_at": self.created_at,
                "finished_at": self.finished_at,
                "error": self.error,
                "metrics": self.metrics,
                "model_path": self.model_path,
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
            "GPU": -1,
        },
    },
    "DNNModelPytorch": {
        "class": "DNNModelPytorch",
        "module_path": "qlib.contrib.model.pytorch_nn",
        "default_kwargs": {
            "lr": 0.001,
            "optimizer": "adam",
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
            "GPU": -1,
        },
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
    """异步训练管理器（支持持久化）"""

    def __init__(self, data_dir: str = None, job_store=None):
        self._jobs: dict[str, TrainJob] = {}
        self._data_dir = data_dir or str(Path.home() / ".qlib" / "qlib_data" / "cn_data")
        self._qlib_initialized = False
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
            self._persist_job(job)

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

        # 清理 NaN 标签（仅 CatBoost 需要，其 RMSE 不允许目标列含 NaN）
        if config.model_class == "CatBoostModel":
            job.update_progress(37, "正在清洗数据（移除 NaN 标签）...")
            nan_count = self._clean_dataset_nan(dataset)
            if nan_count > 0:
                job.update_progress(38, f"已移除 {nan_count} 条 NaN 标签数据")
            else:
                job.update_progress(38, "数据清洗完成，无 NaN 标签")
        elif config.model_class == "LinearModel":
            # LinearModel 内部 dropna() 会删除任何含 NaN 的行，
            # Alpha158/360 的 CSZScoreNorm 处理器引入大量 NaN，需拦截 prepare()
            job.update_progress(37, "正在预处理 NaN（LinearModel 要求）...")
            self._fill_feature_nan(dataset)
            job.update_progress(38, "已启用自动 NaN 填充（拦截 prepare 调用）")
        else:
            job.update_progress(38, "跳过 NaN 清洗（树模型内置处理）")

        # 训练
        job.update_progress(40, "开始训练模型 ...")
        with R.start(experiment_name=f"qtrader_{job.job_id}"):
            model.fit(dataset)
            job.update_progress(55, "模型训练完成，生成预测信号 ...")

            recorder = R.get_recorder()
            sr = SignalRecord(model, dataset, recorder)
            sr.generate()
            job.update_progress(65, "预测信号生成完成")

            sar = SigAnaRecord(recorder)
            sar.generate()
            job.update_progress(75, "信号分析完成")

            # 组合回测分析（可能因 qlib 版本兼容性问题失败，不影响模型训练结果）
            job.update_progress(76, "正在执行组合回测分析 ...")
            try:
                port_analysis_config = {
                    "executor": {
                        "class": "SimulatorExecutor",
                        "module_path": "qlib.backtest.executor",
                        "kwargs": {
                            "time_per_step": "day",
                            "generate_portfolio_metrics": True,
                        },
                    },
                    "strategy": {
                        "class": "TopkDropoutStrategy",
                        "module_path": "qlib.contrib.strategy.signal_strategy",
                        "kwargs": {
                            "signal": (model, dataset),
                            "topk": 50,
                            "n_drop": 5,
                        },
                    },
                    "backtest": {
                        "start_time": config.test_range[0],
                        "end_time": config.test_range[1],
                        "account": 100000000,
                        "benchmark": "SH000300",
                        "exchange_kwargs": {
                            "freq": "day",
                            "limit_threshold": 0.095,
                            "deal_price": "close",
                            "open_cost": 0.0005,
                            "close_cost": 0.0015,
                            "min_cost": 5,
                        },
                    },
                }
                par = PortAnaRecord(recorder, port_analysis_config, "day")
                par.generate()
                job.update_progress(90, "组合回测分析完成")
            except Exception as bt_err:
                logger.warning(f"组合回测分析失败（不影响模型训练）: {bt_err}")
                job.update_progress(90, f"组合回测跳过（{type(bt_err).__name__}），模型训练已完成")

        # 提取真实回测指标
        metrics = self._extract_metrics(recorder)

        # 保存模型权重
        job.update_progress(95, "保存模型 ...")
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

    def _fill_feature_nan(self, dataset) -> int:
        """拦截 dataset.prepare()，在返回数据前填充 NaN（LinearModel 需要）"""
        original_prepare = dataset.prepare
        fill_count = [0]

        def patched_prepare(*args, **kwargs):
            result = original_prepare(*args, **kwargs)
            import pandas as pd
            if isinstance(result, pd.DataFrame) and not result.empty:
                nan_count = int(result.isna().sum().sum())
                if nan_count > 0:
                    fill_count[0] += nan_count
                    result = result.ffill().bfill().fillna(0)
            return result

        dataset.prepare = patched_prepare
        logger.info("Patched dataset.prepare() to auto-fill NaN for LinearModel")
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

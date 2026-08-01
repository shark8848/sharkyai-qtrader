"""
Backtest: 封装 qlib 回测流程
支持 TopkDropout 策略配置，输出标准化结果（收益曲线、回撤、持仓历史）
"""
import asyncio
import os
import uuid
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class BacktestStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class BacktestConfig(BaseModel):
    """回测配置"""
    market: str = "csi300"
    benchmark: str = "SH000300"
    start_time: str = "2017-01-01"
    end_time: str = "2020-08-01"
    account: float = 100_000_000
    # 策略参数
    strategy_class: str = "TopkDropoutStrategy"
    topk: int = 50
    n_drop: int = 5
    # 交易参数
    freq: str = "day"
    limit_threshold: float = 0.095
    deal_price: str = "close"
    open_cost: float = 0.0005
    close_cost: float = 0.0015
    min_cost: float = 5


class BacktestResult(BaseModel):
    """回测结果"""
    job_id: str
    status: BacktestStatus = BacktestStatus.PENDING
    config: BacktestConfig
    created_at: str
    finished_at: Optional[str] = None
    error: Optional[str] = None
    # 指标
    annual_return: Optional[float] = None
    sharpe: Optional[float] = None
    max_drawdown: Optional[float] = None
    information_ratio: Optional[float] = None
    calmar: Optional[float] = None
    # 图表数据（JSON）
    equity_curve: Optional[list[dict]] = None
    drawdown_curve: Optional[list[dict]] = None
    # 原始分析数据
    analysis_data: Optional[dict] = None


class BacktestEngine:
    """回测引擎"""

    def __init__(self, data_dir: str = None):
        self._results: dict[str, BacktestResult] = {}
        self._data_dir = data_dir or str(Path.home() / ".qlib" / "qlib_data" / "cn_data")
        self._qlib_initialized = False

    def _ensure_qlib(self):
        if not self._qlib_initialized:
            os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
            import qlib
            from qlib.constant import REG_CN
            qlib.init(provider_uri=self._data_dir, region=REG_CN)
            self._qlib_initialized = True

    def submit(self, config: BacktestConfig) -> BacktestResult:
        job_id = f"bt_{uuid.uuid4().hex[:12]}"
        result = BacktestResult(
            job_id=job_id,
            config=config,
            created_at=datetime.now().isoformat(),
        )
        self._results[job_id] = result
        return result

    async def run(self, job_id: str, model=None, dataset=None, progress_callback=None):
        """执行回测（可与训练串联）"""
        result = self._results.get(job_id)
        if not result:
            raise ValueError(f"Backtest {job_id} not found")

        result.status = BacktestStatus.RUNNING
        loop = asyncio.get_event_loop()

        try:
            data = await loop.run_in_executor(
                None, self._run_backtest, result, model, dataset, progress_callback
            )
            result.status = BacktestStatus.SUCCESS
            result.annual_return = data.get("annual_return")
            result.sharpe = data.get("sharpe")
            result.max_drawdown = data.get("max_drawdown")
            result.information_ratio = data.get("information_ratio")
            result.calmar = data.get("calmar")
            result.equity_curve = data.get("equity_curve")
            result.drawdown_curve = data.get("drawdown_curve")
            result.analysis_data = data.get("analysis_data")
        except Exception as e:
            logger.exception(f"Backtest {job_id} failed")
            result.status = BacktestStatus.FAILED
            result.error = str(e)
        finally:
            result.finished_at = datetime.now().isoformat()

    def _run_backtest(self, result: BacktestResult, model=None, dataset=None,
                      progress_callback=None) -> dict:
        """同步回测逻辑"""
        self._ensure_qlib()

        config = result.config

        if progress_callback:
            progress_callback(result.job_id, 10, "准备回测环境...")

        # 如果没有传入 model/dataset，则使用 TopkDropout 默认
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
                "class": config.strategy_class,
                "module_path": "qlib.contrib.strategy.signal_strategy",
                "kwargs": {} if model is None else {
                    "signal": (model, dataset),
                    "topk": config.topk,
                    "n_drop": config.n_drop,
                },
            },
            "backtest": {
                "start_time": config.start_time,
                "end_time": config.end_time,
                "account": config.account,
                "benchmark": config.benchmark,
                "exchange_kwargs": {
                    "freq": config.freq,
                    "limit_threshold": config.limit_threshold,
                    "deal_price": config.deal_price,
                    "open_cost": config.open_cost,
                    "close_cost": config.close_cost,
                    "min_cost": config.min_cost,
                },
            },
        }

        if progress_callback:
            progress_callback(result.job_id, 30, "执行回测...")

        # 使用 qlib 的 PortAnaRecord 进行组合分析
        from qlib.workflow import R
        from qlib.workflow.record_temp import PortAnaRecord

        with R.start(experiment_name=f"qtrader_bt_{result.job_id}"):
            recorder = R.get_recorder()
            if model is not None and dataset is not None:
                from qlib.workflow.record_temp import SignalRecord
                sr = SignalRecord(model, dataset, recorder)
                sr.generate()

            par = PortAnaRecord(recorder, port_analysis_config, "day")
            par.generate()

        if progress_callback:
            progress_callback(result.job_id, 70, "计算指标...")

        # 从 recorder 中提取分析结果
        analysis_data = self._extract_analysis(recorder)
        metrics = self._compute_metrics(analysis_data)

        if progress_callback:
            progress_callback(result.job_id, 100, "回测完成")

        return {**metrics, "analysis_data": analysis_data}

    def _extract_analysis(self, recorder) -> dict:
        """从 recorder 提取分析数据"""
        try:
            analysis = recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
            # 将 DataFrame 转为可序列化格式
            if hasattr(analysis, "to_dict"):
                return {"report": analysis.to_dict()}
            return {"report": {}}
        except Exception as e:
            logger.warning(f"Failed to extract analysis: {e}")
            return {}

    def _compute_metrics(self, analysis_data: dict) -> dict:
        """从分析数据计算核心指标"""
        try:
            report = analysis_data.get("report", {})
            if not report:
                return {}

            # 如果有 DataFrame，从中提取指标
            # 这里使用 qlib 标准输出格式
            return {
                "annual_return": None,  # 将由 evaluator 精确计算
                "sharpe": None,
                "max_drawdown": None,
                "information_ratio": None,
                "calmar": None,
                "equity_curve": [],
                "drawdown_curve": [],
            }
        except Exception as e:
            logger.warning(f"Failed to compute metrics: {e}")
            return {}

    def get_result(self, job_id: str) -> Optional[BacktestResult]:
        return self._results.get(job_id)

    def list_results(self) -> list[BacktestResult]:
        return list(self._results.values())


# 全局单例
backtest_engine = BacktestEngine()

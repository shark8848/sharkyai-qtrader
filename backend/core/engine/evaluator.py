"""
Evaluator: 计算核心量化指标 + 生成前端图表 JSON
指标: 年化收益、Sharpe、最大回撤、信息比率、Calmar
图表: 收益曲线、回撤曲线（Plotly 格式 JSON）
"""
import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class Evaluator:
    """量化策略评估器"""

    @staticmethod
    def compute_metrics(
        returns: pd.Series,
        benchmark_returns: Optional[pd.Series] = None,
        risk_free_rate: float = 0.03,
        periods_per_year: int = 252,
    ) -> dict:
        """
        计算核心量化指标

        Args:
            returns: 日收益率序列 (index=datetime)
            benchmark_returns: 基准日收益率序列（可选）
            risk_free_rate: 无风险利率（年化）
            periods_per_year: 年化天数

        Returns:
            包含各指标的字典
        """
        if returns.empty:
            return {}

        # 年化收益
        total_return = (1 + returns).prod() - 1
        n_years = len(returns) / periods_per_year
        annual_return = (1 + total_return) ** (1 / max(n_years, 0.01)) - 1

        # 年化波动率
        annual_vol = returns.std() * np.sqrt(periods_per_year)

        # Sharpe
        excess_return = annual_return - risk_free_rate
        sharpe = excess_return / annual_vol if annual_vol > 0 else 0

        # 最大回撤
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()

        # Calmar
        calmar = annual_return / abs(max_drawdown) if max_drawdown != 0 else 0

        # 信息比率（如果有基准）
        ir = None
        if benchmark_returns is not None and not benchmark_returns.empty:
            aligned = returns.align(benchmark_returns, join="inner")
            active = aligned[0] - aligned[1]
            tracking_error = active.std() * np.sqrt(periods_per_year)
            benchmark_annual = (1 + aligned[1]).prod() ** (1 / max(n_years, 0.01)) - 1
            ir = (annual_return - benchmark_annual) / tracking_error if tracking_error > 0 else 0

        return {
            "total_return": round(float(total_return), 6),
            "annual_return": round(float(annual_return), 6),
            "annual_volatility": round(float(annual_vol), 6),
            "sharpe": round(float(sharpe), 4),
            "max_drawdown": round(float(max_drawdown), 6),
            "calmar": round(float(calmar), 4),
            "information_ratio": round(float(ir), 4) if ir is not None else None,
            "risk_free_rate": risk_free_rate,
        }

    @staticmethod
    def generate_equity_chart(
        returns: pd.Series,
        benchmark_returns: Optional[pd.Series] = None,
    ) -> dict:
        """
        生成 Plotly 格式的收益曲线 + 回撤曲线 JSON

        Returns:
            {"equity": plotly_figure_dict, "drawdown": plotly_figure_dict}
        """
        if returns.empty:
            return {}

        cumulative = (1 + returns).cumprod()
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / running_max

        dates = [d.strftime("%Y-%m-%d") for d in returns.index]

        equity_traces = [
            {
                "x": dates,
                "y": [round(float(v), 6) for v in cumulative],
                "type": "scatter",
                "mode": "lines",
                "name": "策略净值",
                "line": {"color": "#1890ff"},
            },
        ]

        if benchmark_returns is not None and not benchmark_returns.empty:
            bench_cum = (1 + benchmark_returns).cumprod()
            equity_traces.append({
                "x": [d.strftime("%Y-%m-%d") for d in benchmark_returns.index],
                "y": [round(float(v), 6) for v in bench_cum],
                "type": "scatter",
                "mode": "lines",
                "name": "基准净值",
                "line": {"color": "#999", "dash": "dash"},
            })

        equity_figure = {
            "data": equity_traces,
            "layout": {
                "title": "策略净值曲线",
                "xaxis": {"title": "日期"},
                "yaxis": {"title": "净值"},
                "hovermode": "x unified",
                "height": 400,
                "margin": {"l": 50, "r": 20, "t": 50, "b": 50},
            },
        }

        drawdown_figure = {
            "data": [{
                "x": dates,
                "y": [round(float(v), 6) for v in drawdown],
                "type": "scatter",
                "mode": "lines",
                "name": "回撤",
                "fill": "tozeroy",
                "line": {"color": "#ff4d4f"},
            }],
            "layout": {
                "title": "回撤曲线",
                "xaxis": {"title": "日期"},
                "yaxis": {"title": "回撤比例", "tickformat": ".1%"},
                "hovermode": "x unified",
                "height": 300,
                "margin": {"l": 50, "r": 20, "t": 50, "b": 50},
            },
        }

        return {
            "equity": equity_figure,
            "drawdown": drawdown_figure,
        }

    @staticmethod
    def compare_strategies(
        strategy_results: dict[str, pd.Series],
        benchmark_returns: Optional[pd.Series] = None,
    ) -> list[dict]:
        """
        多策略对比

        Args:
            strategy_results: {策略名: 日收益率 Series}
            benchmark_returns: 基准收益率

        Returns:
            各策略指标对比列表
        """
        evaluator = Evaluator()
        comparison = []
        for name, returns in strategy_results.items():
            metrics = evaluator.compute_metrics(returns, benchmark_returns)
            metrics["strategy_name"] = name
            comparison.append(metrics)
        return comparison

    @staticmethod
    def generate_comparison_chart(
        strategy_results: dict[str, pd.Series],
    ) -> dict:
        """生成多策略对比图表"""
        traces = []
        colors = ["#1890ff", "#52c41a", "#faad14", "#ff4d4f", "#722ed1"]

        for i, (name, returns) in enumerate(strategy_results.items()):
            cumulative = (1 + returns).cumprod()
            traces.append({
                "x": [d.strftime("%Y-%m-%d") for d in returns.index],
                "y": [round(float(v), 6) for v in cumulative],
                "type": "scatter",
                "mode": "lines",
                "name": name,
                "line": {"color": colors[i % len(colors)]},
            })

        return {
            "data": traces,
            "layout": {
                "title": "策略对比 - 净值曲线",
                "xaxis": {"title": "日期"},
                "yaxis": {"title": "净值"},
                "hovermode": "x unified",
                "height": 450,
                "margin": {"l": 50, "r": 20, "t": 50, "b": 50},
            },
        }


# 全局单例
evaluator = Evaluator()

"""
策略执行引擎
- 接收模型信号（来自训练模块的预测分数）
- 信号 -> 目标持仓 -> 差异订单 -> 风控过滤 -> 执行下单
- 支持定时调仓（每日收盘前 N 分钟自动执行）
"""
import asyncio
import logging
from datetime import datetime, time
from typing import Optional

from .broker_base import Broker, Order, OrderSide, OrderStatus
from .risk_manager import RiskManager
from .order_manager import OrderManager

logger = logging.getLogger(__name__)


class SignalItem:
    """交易信号"""
    def __init__(self, symbol: str, score: float, target_weight: float = 0):
        self.symbol = symbol
        self.score = score
        self.target_weight = target_weight


class StrategyEngine:
    """策略执行引擎"""

    def __init__(
        self,
        broker: Broker,
        risk_manager: RiskManager,
        order_manager: OrderManager,
    ):
        self._broker = broker
        self._risk_manager = risk_manager
        self._order_manager = order_manager
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._logs: list[dict] = []

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self, signals: list[SignalItem] = None, rebalance_time: str = "14:45"):
        """启动策略引擎"""
        if self._running:
            logger.warning("Strategy engine already running")
            return

        self._running = True
        self._log("策略引擎启动")

        if signals:
            await self.execute_signals(signals)
        else:
            # 定时调仓模式
            self._task = asyncio.create_task(self._rebalance_loop(rebalance_time))

    async def stop(self):
        """停止策略引擎"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._log("策略引擎停止")
        logger.info("Strategy engine stopped")

    async def execute_signals(self, signals: list[SignalItem]):
        """执行交易信号"""
        if not await self._broker.is_connected():
            self._log("券商未连接，跳过执行")
            return

        self._log(f"收到 {len(signals)} 个交易信号")

        # 按分数排序
        signals.sort(key=lambda s: s.score, reverse=True)

        # 获取当前持仓和资金
        positions = await self._broker.get_positions()
        balance = await self._broker.get_balance()
        current_symbols = {p.symbol for p in positions}

        # 1. 先卖出不在目标中的持仓
        target_symbols = {s.symbol for s in signals if s.target_weight > 0}
        to_sell = current_symbols - target_symbols

        for symbol in to_sell:
            pos = next(p for p in positions if p.symbol == symbol)
            if pos.amount > 0 and pos.available > 0:
                order = await self._safe_sell(symbol, pos.current_price, pos.available, balance, positions)
                if order:
                    self._log(f"卖出 {symbol} {pos.available}股 @ {pos.current_price}")

        # 2. 买入新标的
        to_buy = [s for s in signals if s.symbol not in current_symbols and s.target_weight > 0]

        for signal in to_buy[:20]:  # 最多买20只
            # 计算目标金额
            target_amount_value = balance.total * signal.target_weight
            # 取整到100股
            amount = int(target_amount_value / signal.score) // 100 * 100
            if amount < 100:
                continue

            order = await self._safe_buy(signal.symbol, signal.score, amount, balance, positions)
            if order:
                self._log(f"买入 {signal.symbol} {amount}股 @ {signal.score}")

        self._log(f"信号执行完成，共处理 {len(to_sell) + len(to_buy)} 笔")

    async def _safe_buy(self, symbol, price, amount, balance, positions) -> Optional[Order]:
        """带风控的买入"""
        check = self._risk_manager.check_order(
            symbol, OrderSide.BUY, price, amount, balance, positions
        )
        if not check.passed:
            self._log(f"[风控拒绝] 买入 {symbol}: {check.reason}")
            return None

        order = await self._order_manager.place_order(symbol, OrderSide.BUY, price, amount)
        if order.status == OrderStatus.FILLED:
            self._risk_manager.record_trade()
        return order

    async def _safe_sell(self, symbol, price, amount, balance, positions) -> Optional[Order]:
        """带风控的卖出"""
        check = self._risk_manager.check_order(
            symbol, OrderSide.SELL, price, amount, balance, positions
        )
        if not check.passed:
            self._log(f"[风控拒绝] 卖出 {symbol}: {check.reason}")
            return None

        order = await self._order_manager.place_order(symbol, OrderSide.SELL, price, amount)
        if order.status == OrderStatus.FILLED:
            self._risk_manager.record_trade()
        return order

    async def _rebalance_loop(self, rebalance_time: str):
        """定时调仓循环"""
        hour, minute = map(int, rebalance_time.split(":"))
        target_time = time(hour, minute)

        while self._running:
            now = datetime.now()
            if now.time() >= target_time and now.weekday() < 5:
                self._log(f"定时调仓触发 {now.strftime('%Y-%m-%d %H:%M')}")
                # TODO: 从训练模块获取最新信号
                # 这里只是框架
                await asyncio.sleep(60)  # 避免重复触发
            await asyncio.sleep(10)

    def _log(self, message: str):
        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "message": message,
        }
        self._logs.append(entry)
        logger.info(f"[Strategy] {message}")

    def get_logs(self, limit: int = 50) -> list[dict]:
        return self._logs[-limit:]

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "log_count": len(self._logs),
        }

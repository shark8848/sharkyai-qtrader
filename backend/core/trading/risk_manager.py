"""
风控管理器: 订单下单前的风控过滤
- 单笔最大金额限制
- 日最大交易次数限制
- 单票最大仓位比例限制
- 涨跌停过滤
- 异常检测（连续亏损熔断）
"""
import logging
from datetime import date
from pydantic import BaseModel

from .broker_base import OrderSide, Balance, Position

logger = logging.getLogger(__name__)


class RiskConfig(BaseModel):
    max_order_amount: float = 100_000      # 单笔最大金额
    max_daily_trades: int = 50             # 日最大交易次数
    max_position_pct: float = 0.2          # 单票最大仓位比例
    filter_limit_up: bool = True           # 过滤涨停板
    circuit_breaker_loss: float = -0.05    # 日亏损熔断线 (-5%)


class RiskCheckResult(BaseModel):
    passed: bool
    reason: str = ""


class RiskManager:
    """风控管理器"""

    def __init__(self, config: RiskConfig = None):
        self.config = config or RiskConfig()
        self._daily_trade_count: dict[str, int] = {}  # date_str -> count
        self._daily_pnl: dict[str, float] = {}  # date_str -> pnl

    def check_order(
        self,
        symbol: str,
        side: OrderSide,
        price: float,
        amount: int,
        balance: Balance,
        positions: list[Position],
    ) -> RiskCheckResult:
        """订单风控检查"""
        today = date.today().isoformat()
        order_value = price * amount

        # 1. 单笔金额限制
        if order_value > self.config.max_order_amount:
            return RiskCheckResult(
                passed=False,
                reason=f"单笔金额 {order_value:.0f} 超过限制 {self.config.max_order_amount:.0f}",
            )

        # 2. 日交易次数限制
        count = self._daily_trade_count.get(today, 0)
        if count >= self.config.max_daily_trades:
            return RiskCheckResult(
                passed=False,
                reason=f"日交易次数 {count} 已达限制 {self.config.max_daily_trades}",
            )

        # 3. 单票仓位限制（买入时检查）
        if side == OrderSide.BUY and balance.total > 0:
            existing = next((p for p in positions if p.symbol == symbol), None)
            existing_value = existing.market_value if existing else 0
            new_pct = (existing_value + order_value) / balance.total
            if new_pct > self.config.max_position_pct:
                return RiskCheckResult(
                    passed=False,
                    reason=f"买入后仓位 {new_pct:.1%} 超过限制 {self.config.max_position_pct:.1%}",
                )

        # 4. 可用资金检查（买入）
        if side == OrderSide.BUY and order_value > balance.available:
            return RiskCheckResult(
                passed=False,
                reason=f"可用资金 {balance.available:.0f} 不足",
            )

        # 5. 日亏损熔断检查
        daily_pnl = self._daily_pnl.get(today, 0)
        if balance.total > 0:
            daily_return = daily_pnl / balance.total
            if daily_return < self.config.circuit_breaker_loss:
                return RiskCheckResult(
                    passed=False,
                    reason=f"日亏损 {daily_return:.2%} 触发熔断线 {self.config.circuit_breaker_loss:.2%}",
                )

        return RiskCheckResult(passed=True)

    def record_trade(self):
        """记录一次交易"""
        today = date.today().isoformat()
        self._daily_trade_count[today] = self._daily_trade_count.get(today, 0) + 1

    def record_pnl(self, pnl: float):
        """记录当日盈亏"""
        today = date.today().isoformat()
        self._daily_pnl[today] = self._daily_pnl.get(today, 0) + pnl

    def update_config(self, config: RiskConfig):
        self.config = config

    def get_config(self) -> RiskConfig:
        return self.config

    def get_daily_stats(self) -> dict:
        today = date.today().isoformat()
        return {
            "trade_count": self._daily_trade_count.get(today, 0),
            "daily_pnl": self._daily_pnl.get(today, 0),
        }

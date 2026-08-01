"""
SimBroker: 内存撮合引擎，模拟真实交易环境
用于策略验证和 UI 开发调试
"""
import uuid
import logging
from datetime import datetime

from .broker_base import Broker, Order, OrderSide, OrderStatus, Position, Balance

logger = logging.getLogger(__name__)


class SimBroker(Broker):
    """模拟交易券商"""

    def __init__(self, initial_cash: float = 1_000_000):
        self._connected = False
        self._cash = initial_cash
        self._initial_cash = initial_cash
        self._positions: dict[str, Position] = {}  # symbol -> Position
        self._orders: list[Order] = []
        self._today_orders: list[Order] = []
        self._today_bought: dict[str, int] = {}  # symbol -> amount bought today (T+1)

    @property
    def name(self) -> str:
        return "SimBroker"

    async def connect(self) -> bool:
        self._connected = True
        logger.info("SimBroker connected")
        return True

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("SimBroker disconnected")

    async def is_connected(self) -> bool:
        return self._connected

    async def get_balance(self) -> Balance:
        market_value = sum(p.market_value for p in self._positions.values())
        return Balance(
            total=self._cash + market_value,
            available=self._cash,
            market_value=market_value,
            frozen=0,
        )

    async def get_positions(self) -> list[Position]:
        return [p for p in self._positions.values() if p.amount > 0]

    async def buy(self, symbol: str, price: float, amount: int) -> Order:
        """买入: 立即撮合成交"""
        self._ensure_connected()

        # 验证数量为100整数倍
        if amount % 100 != 0:
            return Order(
                order_id=self._gen_id(),
                symbol=symbol, side=OrderSide.BUY,
                price=price, amount=amount,
                status=OrderStatus.REJECTED,
                remark="买入数量必须为100的整数倍",
                created_at=self._now(), updated_at=self._now(),
            )

        cost = price * amount
        if cost > self._cash:
            return Order(
                order_id=self._gen_id(),
                symbol=symbol, side=OrderSide.BUY,
                price=price, amount=amount,
                status=OrderStatus.REJECTED,
                remark="资金不足",
                created_at=self._now(), updated_at=self._now(),
            )

        # 成交
        order = Order(
            order_id=self._gen_id(),
            symbol=symbol, side=OrderSide.BUY,
            price=price, amount=amount,
            filled=amount, filled_price=price,
            status=OrderStatus.FILLED,
            created_at=self._now(), updated_at=self._now(),
        )

        # 更新持仓和资金
        self._cash -= cost
        if symbol in self._positions:
            pos = self._positions[symbol]
            total_cost = pos.cost_price * pos.amount + cost
            pos.amount += amount
            pos.cost_price = total_cost / pos.amount if pos.amount > 0 else 0
            pos.current_price = price
            pos.market_value = pos.amount * price
        else:
            self._positions[symbol] = Position(
                symbol=symbol, name=symbol,
                amount=amount, available=0,  # T+1 今日不可卖
                cost_price=price, current_price=price,
                market_value=amount * price,
            )

        # 记录今日买入（T+1 限制）
        self._today_bought[symbol] = self._today_bought.get(symbol, 0) + amount
        self._today_orders.append(order)
        self._orders.append(order)

        logger.info(f"BUY {symbol} {amount}@{price}, order_id={order.order_id}")
        return order

    async def sell(self, symbol: str, price: float, amount: int) -> Order:
        """卖出: 立即撮合成交"""
        self._ensure_connected()

        pos = self._positions.get(symbol)
        if not pos or pos.amount <= 0:
            return Order(
                order_id=self._gen_id(),
                symbol=symbol, side=OrderSide.SELL,
                price=price, amount=amount,
                status=OrderStatus.REJECTED,
                remark="无持仓",
                created_at=self._now(), updated_at=self._now(),
            )

        # T+1: 可卖数量 = 持仓 - 今日买入
        available = pos.amount - self._today_bought.get(symbol, 0)
        if amount > available:
            return Order(
                order_id=self._gen_id(),
                symbol=symbol, side=OrderSide.SELL,
                price=price, amount=amount,
                status=OrderStatus.REJECTED,
                remark=f"可卖数量不足: {available}",
                created_at=self._now(), updated_at=self._now(),
            )

        # 成交
        order = Order(
            order_id=self._gen_id(),
            symbol=symbol, side=OrderSide.SELL,
            price=price, amount=amount,
            filled=amount, filled_price=price,
            status=OrderStatus.FILLED,
            created_at=self._now(), updated_at=self._now(),
        )

        # 更新持仓和资金
        revenue = price * amount
        self._cash += revenue
        pos.amount -= amount
        pos.available = max(0, pos.available - amount)
        pos.current_price = price
        pos.market_value = pos.amount * price
        pos.pnl = (price - pos.cost_price) * pos.amount
        pos.pnl_pct = (price / pos.cost_price - 1) if pos.cost_price > 0 else 0

        # 清除空仓
        if pos.amount == 0:
            del self._positions[symbol]

        self._today_orders.append(order)
        self._orders.append(order)

        logger.info(f"SELL {symbol} {amount}@{price}, order_id={order.order_id}")
        return order

    async def get_orders(self) -> list[Order]:
        return self._today_orders

    async def cancel_order(self, order_id: str) -> bool:
        # SimBroker 立即成交，不支持撤单
        logger.warning(f"SimBroker: cancel_order {order_id} - 已成交订单不可撤单")
        return False

    def new_trading_day(self):
        """新的交易日：重置 T+1 限制"""
        self._today_orders = []
        self._today_bought = {}
        # 更新可卖数量
        for pos in self._positions.values():
            pos.available = pos.amount

    def _ensure_connected(self):
        if not self._connected:
            raise RuntimeError("SimBroker not connected")

    def _gen_id(self) -> str:
        return f"SIM{uuid.uuid4().hex[:10].upper()}"

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

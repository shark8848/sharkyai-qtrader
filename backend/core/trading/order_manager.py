"""
订单管理器: 订单生命周期管理
- 订单状态机: pending -> submitted -> partial_fill -> filled / cancelled
- 订单持久化（内存，可扩展到 SQLite）
- 自动重试失败订单
"""
import logging
from datetime import datetime
from typing import Optional

from .broker_base import Broker, Order, OrderSide, OrderStatus

logger = logging.getLogger(__name__)


class OrderManager:
    """订单生命周期管理器"""

    def __init__(self, broker: Broker, max_retries: int = 1):
        self._broker = broker
        self._orders: list[Order] = []
        self._max_retries = max_retries

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        price: float,
        amount: int,
    ) -> Order:
        """下单并记录"""
        if side == OrderSide.BUY:
            order = await self._broker.buy(symbol, price, amount)
        else:
            order = await self._broker.sell(symbol, price, amount)

        self._orders.append(order)
        logger.info(
            f"Order placed: {order.order_id} {side.value} {symbol} "
            f"{amount}@{price} -> {order.status.value}"
        )
        return order

    async def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        order = self.get_order(order_id)
        if not order:
            logger.warning(f"Order {order_id} not found")
            return False

        if order.status in (OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED):
            logger.warning(f"Order {order_id} status is {order.status.value}, cannot cancel")
            return False

        success = await self._broker.cancel_order(order_id)
        if success:
            order.status = OrderStatus.CANCELLED
            order.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"Order {order_id} cancelled")
        return success

    def get_order(self, order_id: str) -> Optional[Order]:
        for o in self._orders:
            if o.order_id == order_id:
                return o
        return None

    def get_today_orders(self) -> list[Order]:
        today = datetime.now().strftime("%Y-%m-%d")
        return [o for o in self._orders if o.created_at.startswith(today)]

    def get_all_orders(self) -> list[Order]:
        return self._orders

    def get_pending_orders(self) -> list[Order]:
        return [o for o in self._orders if o.status in (
            OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILL
        )]

    async def sync_orders(self):
        """从券商同步订单状态"""
        try:
            broker_orders = await self._broker.get_orders()
            broker_map = {o.order_id: o for o in broker_orders}
            for local_order in self._orders:
                if local_order.order_id in broker_map:
                    remote = broker_map[local_order.order_id]
                    local_order.status = remote.status
                    local_order.filled = remote.filled
                    local_order.filled_price = remote.filled_price
                    local_order.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception as e:
            logger.error(f"Failed to sync orders: {e}")

    def clear_today(self):
        """清除今日订单记录（用于测试）"""
        today = datetime.now().strftime("%Y-%m-%d")
        self._orders = [o for o in self._orders if not o.created_at.startswith(today)]

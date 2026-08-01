"""
Broker 抽象基类: 定义券商交易接口统一协议
所有 Broker（SimBroker / 东方财富 / miniQMT）必须实现此接口
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL_FILL = "partial_fill"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class Order(BaseModel):
    order_id: str
    symbol: str
    side: OrderSide
    price: float
    amount: int
    filled: int = 0
    filled_price: float = 0
    status: OrderStatus = OrderStatus.PENDING
    created_at: str = ""
    updated_at: str = ""
    remark: str = ""


class Position(BaseModel):
    symbol: str
    name: str = ""
    amount: int = 0
    available: int = 0  # T+1 可卖数量
    cost_price: float = 0
    current_price: float = 0
    pnl: float = 0
    pnl_pct: float = 0
    market_value: float = 0


class Balance(BaseModel):
    total: float = 0          # 总资产
    available: float = 0      # 可用资金
    market_value: float = 0   # 持仓市值
    frozen: float = 0         # 冻结资金


class Broker(ABC):
    """券商交易接口抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """券商名称"""
        ...

    @abstractmethod
    async def connect(self) -> bool:
        """连接券商，返回是否成功"""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接"""
        ...

    @abstractmethod
    async def is_connected(self) -> bool:
        """是否已连接"""
        ...

    @abstractmethod
    async def get_balance(self) -> Balance:
        """查询资金"""
        ...

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """查询持仓"""
        ...

    @abstractmethod
    async def buy(self, symbol: str, price: float, amount: int) -> Order:
        """买入"""
        ...

    @abstractmethod
    async def sell(self, symbol: str, price: float, amount: int) -> Order:
        """卖出"""
        ...

    @abstractmethod
    async def get_orders(self) -> list[Order]:
        """查询当日委托"""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        ...

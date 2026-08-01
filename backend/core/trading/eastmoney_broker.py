"""
东方财富 Broker: 对接东方财富 jvQuant REST API
方案: 分配柜台 -> 登录获取 ticket -> 交易操作
适合 Linux 服务器部署，无需 Windows 客户端
"""
import logging
from typing import Optional
import httpx

from .broker_base import Broker, Order, OrderSide, OrderStatus, Position, Balance

logger = logging.getLogger(__name__)


class EastMoneyBroker(Broker):
    """东方财富交易接口（jvQuant REST API）"""

    def __init__(self, gateway: str = "", token: str = ""):
        self._gateway = gateway
        self._token = token
        self._connected = False
        self._ticket: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def name(self) -> str:
        return "EastMoney"

    async def connect(self) -> bool:
        """登录获取交易 ticket"""
        if not self._gateway or not self._token:
            logger.error("EastMoney gateway or token not configured")
            return False

        try:
            self._client = httpx.AsyncClient(
                base_url=self._gateway,
                timeout=30.0,
                headers={"Authorization": f"Bearer {self._token}"},
            )
            # 登录获取 ticket
            resp = await self._client.post("/api/auth/login", json={
                "token": self._token,
            })
            if resp.status_code == 200:
                data = resp.json()
                self._ticket = data.get("ticket")
                self._connected = True
                logger.info("EastMoney broker connected")
                return True
            else:
                logger.error(f"EastMoney login failed: {resp.text}")
                return False
        except Exception as e:
            logger.error(f"EastMoney connect failed: {e}")
            return False

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
        self._connected = False
        self._ticket = None
        logger.info("EastMoney broker disconnected")

    async def is_connected(self) -> bool:
        return self._connected

    async def get_balance(self) -> Balance:
        self._ensure_connected()
        try:
            resp = await self._client.get("/api/account/balance", params={
                "ticket": self._ticket,
            })
            if resp.status_code == 200:
                data = resp.json()
                return Balance(
                    total=data.get("total", 0),
                    available=data.get("available", 0),
                    market_value=data.get("market_value", 0),
                    frozen=data.get("frozen", 0),
                )
        except Exception as e:
            logger.error(f"get_balance failed: {e}")
        return Balance()

    async def get_positions(self) -> list[Position]:
        self._ensure_connected()
        try:
            resp = await self._client.get("/api/account/positions", params={
                "ticket": self._ticket,
            })
            if resp.status_code == 200:
                data = resp.json()
                return [
                    Position(
                        symbol=p.get("symbol", ""),
                        name=p.get("name", ""),
                        amount=p.get("amount", 0),
                        available=p.get("available", 0),
                        cost_price=p.get("cost_price", 0),
                        current_price=p.get("current_price", 0),
                        pnl=p.get("pnl", 0),
                        pnl_pct=p.get("pnl_pct", 0),
                        market_value=p.get("market_value", 0),
                    )
                    for p in data.get("positions", [])
                ]
        except Exception as e:
            logger.error(f"get_positions failed: {e}")
        return []

    async def buy(self, symbol: str, price: float, amount: int) -> Order:
        self._ensure_connected()
        return await self._place_order(symbol, OrderSide.BUY, price, amount)

    async def sell(self, symbol: str, price: float, amount: int) -> Order:
        self._ensure_connected()
        return await self._place_order(symbol, OrderSide.SELL, price, amount)

    async def _place_order(self, symbol: str, side: OrderSide, price: float, amount: int) -> Order:
        try:
            resp = await self._client.post("/api/trade/order", json={
                "ticket": self._ticket,
                "symbol": symbol,
                "side": side.value,
                "price": price,
                "amount": amount,
            })
            if resp.status_code == 200:
                data = resp.json()
                return Order(
                    order_id=data.get("order_id", ""),
                    symbol=symbol,
                    side=side,
                    price=price,
                    amount=amount,
                    status=OrderStatus.SUBMITTED,
                )
            else:
                return Order(
                    order_id="",
                    symbol=symbol, side=side,
                    price=price, amount=amount,
                    status=OrderStatus.REJECTED,
                    remark=resp.text,
                )
        except Exception as e:
            logger.error(f"place_order failed: {e}")
            return Order(
                order_id="", symbol=symbol, side=side,
                price=price, amount=amount,
                status=OrderStatus.REJECTED,
                remark=str(e),
            )

    async def get_orders(self) -> list[Order]:
        self._ensure_connected()
        try:
            resp = await self._client.get("/api/trade/orders", params={
                "ticket": self._ticket,
            })
            if resp.status_code == 200:
                data = resp.json()
                return [
                    Order(
                        order_id=o.get("order_id", ""),
                        symbol=o.get("symbol", ""),
                        side=OrderSide(o.get("side", "buy")),
                        price=o.get("price", 0),
                        amount=o.get("amount", 0),
                        filled=o.get("filled", 0),
                        status=OrderStatus(o.get("status", "pending")),
                    )
                    for o in data.get("orders", [])
                ]
        except Exception as e:
            logger.error(f"get_orders failed: {e}")
        return []

    async def cancel_order(self, order_id: str) -> bool:
        self._ensure_connected()
        try:
            resp = await self._client.post(f"/api/trade/cancel/{order_id}", params={
                "ticket": self._ticket,
            })
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"cancel_order failed: {e}")
            return False

    def _ensure_connected(self):
        if not self._connected:
            raise RuntimeError("EastMoney broker not connected")

"""Trading management API routes."""
import logging
from pydantic import BaseModel

from fastapi import APIRouter, HTTPException

from qtrader.backend.config import settings
from qtrader.backend.core.trading.broker_base import Broker, OrderSide
from qtrader.backend.core.trading.sim_broker import SimBroker
from qtrader.backend.core.trading.risk_manager import RiskManager, RiskConfig
from qtrader.backend.core.trading.order_manager import OrderManager
from qtrader.backend.core.trading.strategy import StrategyEngine

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# 全局交易引擎实例
# ---------------------------------------------------------------------------

_broker: Broker | None = None
_risk_manager: RiskManager | None = None
_order_manager: OrderManager | None = None
_strategy_engine: StrategyEngine | None = None


def _init_trading_engine():
    """初始化交易引擎"""
    global _broker, _risk_manager, _order_manager, _strategy_engine

    # 根据配置选择 broker
    if settings.broker_type == "eastmoney":
        from qtrader.backend.core.trading.eastmoney_broker import EastMoneyBroker
        _broker = EastMoneyBroker(
            gateway=settings.eastmoney_gateway,
            token=settings.eastmoney_token,
        )
    else:
        _broker = SimBroker()

    _risk_manager = RiskManager(RiskConfig(
        max_order_amount=settings.max_order_amount,
        max_daily_trades=settings.max_daily_trades,
        max_position_pct=settings.max_position_ratio,
        filter_limit_up=settings.enable_limit_filter,
    ))
    _order_manager = OrderManager(_broker)
    _strategy_engine = StrategyEngine(_broker, _risk_manager, _order_manager)

    logger.info(f"Trading engine initialized with {settings.broker_type} broker")


def _get_engine():
    if _strategy_engine is None:
        _init_trading_engine()
    return _broker, _risk_manager, _order_manager, _strategy_engine


# ---------------------------------------------------------------------------
# Broker 连接
# ---------------------------------------------------------------------------

@router.post("/connect")
async def connect_broker():
    """连接券商"""
    broker, _, _, _ = _get_engine()
    success = await broker.connect()
    if success:
        return {"message": f"已连接 {broker.name}", "status": "connected", "broker": broker.name}
    raise HTTPException(status_code=500, detail="连接失败")


@router.get("/status")
async def get_broker_status():
    """券商状态"""
    broker, _, _, strategy = _get_engine()
    connected = await broker.is_connected()
    return {
        "connected": connected,
        "broker": broker.name if connected else None,
        "strategy": strategy.get_status(),
    }


# ---------------------------------------------------------------------------
# 资金与持仓
# ---------------------------------------------------------------------------

@router.get("/balance")
async def get_balance():
    """查询资金"""
    broker, _, _, _ = _get_engine()
    if not await broker.is_connected():
        raise HTTPException(status_code=400, detail="券商未连接")
    balance = await broker.get_balance()
    return balance.model_dump()


@router.get("/positions")
async def get_positions():
    """查询持仓"""
    broker, _, _, _ = _get_engine()
    if not await broker.is_connected():
        raise HTTPException(status_code=400, detail="券商未连接")
    positions = await broker.get_positions()
    return [p.model_dump() for p in positions]


# ---------------------------------------------------------------------------
# 下单
# ---------------------------------------------------------------------------

class OrderRequest(BaseModel):
    symbol: str
    side: str  # buy | sell
    price: float
    amount: int


@router.post("/order")
async def place_order(req: OrderRequest):
    """下单"""
    broker, risk_mgr, order_mgr, _ = _get_engine()
    if not await broker.is_connected():
        raise HTTPException(status_code=400, detail="券商未连接")

    side = OrderSide.BUY if req.side == "buy" else OrderSide.SELL

    # 风控检查
    balance = await broker.get_balance()
    positions = await broker.get_positions()
    check = risk_mgr.check_order(req.symbol, side, req.price, req.amount, balance, positions)
    if not check.passed:
        raise HTTPException(status_code=403, detail=f"风控拒绝: {check.reason}")

    order = await order_mgr.place_order(req.symbol, side, req.price, req.amount)
    risk_mgr.record_trade()
    return order.model_dump()


@router.get("/orders")
async def get_orders():
    """查询今日委托"""
    _, _, order_mgr, _ = _get_engine()
    orders = order_mgr.get_today_orders()
    return [o.model_dump() for o in orders]


@router.post("/cancel/{order_id}")
async def cancel_order(order_id: str):
    """撤单"""
    _, _, order_mgr, _ = _get_engine()
    success = await order_mgr.cancel_order(order_id)
    if success:
        return {"order_id": order_id, "status": "cancelled"}
    raise HTTPException(status_code=400, detail="撤单失败")


# ---------------------------------------------------------------------------
# 策略引擎
# ---------------------------------------------------------------------------

@router.post("/strategy/start")
async def start_strategy():
    """启动自动策略"""
    _, _, _, strategy = _get_engine()
    await strategy.start()
    return {"message": "策略已启动", "status": "running"}


@router.post("/strategy/stop")
async def stop_strategy():
    """停止自动策略"""
    _, _, _, strategy = _get_engine()
    await strategy.stop()
    return {"message": "策略已停止", "status": "stopped"}


@router.get("/strategy/logs")
async def get_strategy_logs(limit: int = 50):
    """策略运行日志"""
    _, _, _, strategy = _get_engine()
    return strategy.get_logs(limit)


# ---------------------------------------------------------------------------
# 风控配置
# ---------------------------------------------------------------------------

@router.get("/risk/config")
async def get_risk_config():
    """获取风控配置"""
    _, risk_mgr, _, _ = _get_engine()
    return risk_mgr.get_config().model_dump()


@router.put("/risk/config")
async def update_risk_config(config: RiskConfig):
    """更新风控配置"""
    _, risk_mgr, _, _ = _get_engine()
    risk_mgr.update_config(config)
    return {"message": "风控配置已更新", "config": config.model_dump()}


@router.get("/risk/stats")
async def get_risk_stats():
    """风控统计"""
    _, risk_mgr, _, _ = _get_engine()
    return risk_mgr.get_daily_stats()

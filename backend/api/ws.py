"""WebSocket endpoints for real-time data push."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectionManager:
    """管理 WebSocket 连接，支持频道订阅"""

    def __init__(self):
        self._connections: dict[WebSocket, set[str]] = {}  # ws -> subscribed channels

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self._connections[websocket] = set()
        logger.info(f"WebSocket connected (total: {len(self._connections)})")

    def disconnect(self, websocket: WebSocket):
        self._connections.pop(websocket, None)
        logger.info(f"WebSocket disconnected (total: {len(self._connections)})")

    async def subscribe(self, websocket: WebSocket, channels: list[str]):
        """订阅频道"""
        if websocket in self._connections:
            self._connections[websocket].update(channels)
        await websocket.send_json({
            "type": "subscribed",
            "channels": list(self._connections.get(websocket, [])),
        })

    async def unsubscribe(self, websocket: WebSocket, channels: list[str]):
        """取消订阅"""
        if websocket in self._connections:
            self._connections[websocket] -= set(channels)

    async def push(self, channel: str, data: dict):
        """向特定频道推送消息"""
        message = {"type": channel, "data": data}
        dead = []
        for ws, channels in self._connections.items():
            if channel in channels:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def broadcast(self, message: dict):
        """广播消息给所有连接"""
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


# 全局连接管理器
ws_manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """主 WebSocket 端点

    客户端消息格式:
    - {"type": "subscribe", "channels": ["quotes", "orders", "training"]}
    - {"type": "unsubscribe", "channels": ["quotes"]}
    - {"type": "ping"}

    服务端推送:
    - {"type": "quotes", "data": {...}}        实时行情
    - {"type": "orders", "data": {...}}        订单状态变更
    - {"type": "training", "data": {...}}      训练进度
    - {"type": "position", "data": {...}}      持仓变更
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "subscribe":
                channels = msg.get("channels", [])
                await ws_manager.subscribe(websocket, channels)

            elif msg_type == "unsubscribe":
                channels = msg.get("channels", [])
                await ws_manager.unsubscribe(websocket, channels)

            else:
                await websocket.send_json({"type": "echo", "data": msg})

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# 辅助函数（供其他模块调用以推送消息）
# ---------------------------------------------------------------------------

async def push_training_progress(job_id: str, progress: int, message: str):
    """推送训练进度"""
    await ws_manager.push("training", {
        "job_id": job_id,
        "progress": progress,
        "message": message,
    })


async def push_order_update(order: dict):
    """推送订单状态变更"""
    await ws_manager.push("orders", order)


async def push_position_update(positions: list):
    """推送持仓更新"""
    await ws_manager.push("position", {"positions": positions})


async def push_quote(quotes: dict):
    """推送实时行情"""
    await ws_manager.push("quotes", quotes)

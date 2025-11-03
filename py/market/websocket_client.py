"""
Binance WebSocket 客户端
"""

import asyncio
import json
from typing import Dict, Callable, Optional
from loguru import logger
import websockets
from websockets.exceptions import ConnectionClosed


class WebSocketClient:
    """Binance WebSocket 客户端"""

    def __init__(self, url: str = "wss://fstream.binance.com/ws"):
        self.url = url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.subscribers: Dict[str, asyncio.Queue] = {}
        self.reconnect = True
        self.running = False

    async def connect(self):
        """连接到 WebSocket"""
        try:
            self.ws = await websockets.connect(self.url)
            logger.success(f"✓ WebSocket 连接成功: {self.url}")
            self.running = True
            return True
        except Exception as e:
            logger.error(f"❌ WebSocket 连接失败: {e}")
            return False

    async def subscribe(self, stream: str):
        """订阅流"""
        if not self.ws:
            raise Exception("WebSocket 未连接")

        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": [stream],
            "id": int(asyncio.get_event_loop().time())
        }

        await self.ws.send(json.dumps(subscribe_msg))
        logger.info(f"📡 订阅流: {stream}")

    async def unsubscribe(self, stream: str):
        """取消订阅流"""
        if not self.ws:
            return

        unsubscribe_msg = {
            "method": "UNSUBSCRIBE",
            "params": [stream],
            "id": int(asyncio.get_event_loop().time())
        }

        await self.ws.send(json.dumps(unsubscribe_msg))
        logger.info(f"🔕 取消订阅: {stream}")

    def add_subscriber(self, stream: str, buffer_size: int = 100) -> asyncio.Queue:
        """添加订阅者"""
        if stream not in self.subscribers:
            self.subscribers[stream] = asyncio.Queue(maxsize=buffer_size)
        return self.subscribers[stream]

    def remove_subscriber(self, stream: str):
        """移除订阅者"""
        if stream in self.subscribers:
            del self.subscribers[stream]

    async def read_messages(self):
        """读取消息循环"""
        while self.running:
            try:
                if not self.ws:
                    await asyncio.sleep(1)
                    continue

                message = await self.ws.recv()
                await self._handle_message(message)

            except ConnectionClosed:
                logger.warning("⚠️  WebSocket 连接关闭")
                if self.reconnect:
                    await self._reconnect()
                else:
                    break

            except Exception as e:
                logger.error(f"❌ 读取消息失败: {e}")
                await asyncio.sleep(1)

    async def _handle_message(self, message: str):
        """处理收到的消息"""
        try:
            data = json.loads(message)

            # 忽略订阅确认消息
            if "result" in data or "id" in data:
                return

            # 提取流名称
            stream = data.get("stream")
            if not stream:
                return

            # 分发到订阅者
            if stream in self.subscribers:
                queue = self.subscribers[stream]
                try:
                    queue.put_nowait(data.get("data"))
                except asyncio.QueueFull:
                    logger.warning(f"⚠️  订阅者队列已满: {stream}")

        except json.JSONDecodeError:
            logger.warning(f"⚠️  无法解析消息: {message}")
        except Exception as e:
            logger.error(f"❌ 处理消息失败: {e}")

    async def _reconnect(self):
        """重新连接"""
        logger.info("🔄 尝试重新连接...")
        await asyncio.sleep(3)

        try:
            await self.connect()
            # 重新订阅所有流
            for stream in self.subscribers.keys():
                await self.subscribe(stream)
        except Exception as e:
            logger.error(f"❌ 重新连接失败: {e}")
            if self.reconnect:
                await self._reconnect()

    async def close(self):
        """关闭连接"""
        self.reconnect = False
        self.running = False

        if self.ws:
            await self.ws.close()
            self.ws = None

        # 清空所有队列
        for stream, queue in self.subscribers.items():
            while not queue.empty():
                try:
                    queue.get_nowait()
                except:
                    pass

        logger.info("👋 WebSocket 连接已关闭")

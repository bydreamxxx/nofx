"""
Binance WebSocket 客户端
"""

import asyncio
import json
from typing import Dict, Callable, Optional
from loguru import logger
import websockets
from websockets.exceptions import ConnectionClosed

from utils.http_config import get_http_proxy


class WebSocketClient:
    """Binance WebSocket 客户端"""

    def __init__(self, url: str = "wss://fstream.binance.com/stream"):
        self.url = url
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.subscribers: Dict[str, asyncio.Queue] = {}
        self.reconnect = True
        self.running = False
        self.ping_interval = 60  # 每60秒发送一次ping
        self.ping_timeout = 10   # ping超时时间

    async def connect(self):
        """连接到 WebSocket"""
        try:
            proxy = get_http_proxy()
            self.ws = await websockets.connect(
                self.url,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout,
                proxy=proxy
            )
            logger.success(f"✓ WebSocket 连接成功: {self.url}")
            self.running = True
            return True
        except Exception as e:
            logger.error(f"❌ WebSocket 连接失败: {e}")
            return False

    async def subscribe(self, streams):
        """
        订阅流

        Args:
            streams: 可以是单个流字符串，或流列表
        """
        if not self.ws:
            raise Exception("WebSocket 未连接")

        # 统一处理为列表
        if isinstance(streams, str):
            streams = [streams]

        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": streams,  # 直接传入流列表
            "id": int(asyncio.get_event_loop().time())
        }

        await self.ws.send(json.dumps(subscribe_msg))
        logger.info(f"📡 订阅 {len(streams)} 个流")

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

            except ConnectionClosed as e:
                logger.warning(f"⚠️  WebSocket 连接关闭: {e}")
                if self.reconnect:
                    await self._reconnect()
                else:
                    break

            except asyncio.CancelledError:
                logger.info("📴 消息读取任务被取消")
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
                    # 队列满时，移除最旧的数据，添加新数据
                    try:
                        queue.get_nowait()  # 丢弃最旧的
                        queue.put_nowait(data.get("data"))  # 添加最新的
                        logger.debug(f"🔄 队列满，丢弃旧数据: {stream}")
                    except:
                        pass

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
            # 重新批量订阅所有流
            all_streams = list(self.subscribers.keys())
            if all_streams:
                # 分批订阅（每次最多200个流）
                batch_size = 200
                for i in range(0, len(all_streams), batch_size):
                    batch = all_streams[i:i + batch_size]
                    await self.subscribe(batch)
                    await asyncio.sleep(0.1)  # 避免过快
                logger.info(f"✓ 重新订阅了 {len(all_streams)} 个流")
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

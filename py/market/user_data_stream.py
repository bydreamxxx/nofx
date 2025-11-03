"""
币安用户数据流 WebSocket 客户端
实时接收账户、订单、持仓更新
"""

import asyncio
from typing import Optional, Dict, List, Any, Callable
from loguru import logger
import websockets
import json
from websockets.exceptions import ConnectionClosed
import httpx
from httpx_retry import AsyncRetryTransport, RetryPolicy

from utils.http_config import get_http_proxy


class UserDataStream:
    """币安用户数据流 WebSocket 客户端"""

    def __init__(self, api_key: str, secret_key: str, testnet: bool = False):
        self.api_key = api_key
        self.secret_key = secret_key
        self.testnet = testnet

        # 端点配置
        if testnet:
            self.rest_base = "https://testnet.binancefuture.com"
            self.ws_base = "wss://stream.binancefuture.com/ws"
        else:
            self.rest_base = "https://fapi.binance.com"
            self.ws_base = "wss://fstream.binance.com/ws"

        # WebSocket 连接
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.listen_key: Optional[str] = None
        self.running = False

        # 数据缓存
        self.account_data: Optional[Dict[str, Any]] = None
        self.positions: List[Dict[str, Any]] = []
        self.orders: List[Dict[str, Any]] = []

        # 后台任务
        self.tasks: List[asyncio.Task] = []

        # 回调函数
        self.on_account_update: Optional[Callable] = None
        self.on_order_update: Optional[Callable] = None
        self.on_position_update: Optional[Callable] = None

    async def _get_listen_key(self) -> str:
        """获取 listenKey"""
        try:
            proxy = get_http_proxy()
            async with httpx.AsyncClient(
                proxy=proxy,
                http2=True,
                transport=AsyncRetryTransport(
                    policy=RetryPolicy().with_max_retries(3).with_min_delay(1).with_multiplier(2)
                ),
                timeout=10.0
            ) as client:
                url = f"{self.rest_base}/fapi/v1/listenKey"
                headers = {"X-MBX-APIKEY": self.api_key}

                response = await client.post(url, headers=headers)
                data = response.json()

                listen_key = data.get("listenKey")
                if not listen_key:
                    raise Exception("无法获取 listenKey")

                logger.success(f"✓ 获取到 listenKey: {listen_key[:10]}...")
                return listen_key

        except Exception as e:
            logger.error(f"❌ 获取 listenKey 失败: {e}")
            raise

    async def _keep_alive_listen_key(self):
        """保持 listenKey 活跃（每 30 分钟刷新一次）"""
        while self.running:
            try:
                await asyncio.sleep(30 * 60)  # 30 分钟

                if not self.listen_key:
                    continue

                proxy = get_http_proxy()
                async with httpx.AsyncClient(
                    proxy=proxy,
                    http2=True,
                    transport=AsyncRetryTransport(
                        policy=RetryPolicy().with_max_retries(3).with_min_delay(1).with_multiplier(2)
                    ),
                    timeout=10.0
                ) as client:
                    url = f"{self.rest_base}/fapi/v1/listenKey"
                    headers = {"X-MBX-APIKEY": self.api_key}

                    response = await client.put(url, headers=headers)

                    if response.status_code == 200:
                        logger.debug("✓ listenKey 已刷新")
                    else:
                        logger.warning(f"⚠️  刷新 listenKey 失败: {response.text}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 刷新 listenKey 失败: {e}")

    async def connect(self):
        """连接到用户数据流"""
        try:
            # 获取 listenKey
            self.listen_key = await self._get_listen_key()

            # 连接 WebSocket
            proxy = get_http_proxy()
            ws_url = f"{self.ws_base}/{self.listen_key}"

            self.ws = await websockets.connect(
                ws_url,
                ping_interval=60,
                ping_timeout=10,
                proxy=proxy
            )

            logger.success(f"✓ 用户数据流 WebSocket 连接成功")
            self.running = True

            # 启动保活任务
            keep_alive_task = asyncio.create_task(self._keep_alive_listen_key())
            self.tasks.append(keep_alive_task)

            return True

        except Exception as e:
            logger.error(f"❌ 用户数据流 WebSocket 连接失败: {e}")
            return False

    async def _handle_message(self, message: str):
        """处理收到的消息"""
        try:
            data = json.loads(message)
            event_type = data.get("e")

            if event_type == "ACCOUNT_UPDATE":
                # 账户更新事件
                await self._handle_account_update(data)

            elif event_type == "ORDER_TRADE_UPDATE":
                # 订单更新事件
                await self._handle_order_update(data)

        except json.JSONDecodeError:
            logger.warning(f"⚠️  无法解析消息: {message}")
        except Exception as e:
            logger.error(f"❌ 处理消息失败: {e}")

    async def _handle_account_update(self, data: Dict):
        """处理账户更新"""
        try:
            update_data = data.get("a", {})

            # 更新余额
            balances = update_data.get("B", [])
            for balance in balances:
                if balance.get("a") == "USDT":
                    self.account_data = {
                        "totalWalletBalance": float(balance.get("wb", 0)),
                        "availableBalance": float(balance.get("cw", 0)),
                        "totalUnrealizedProfit": 0.0  # 这个需要从持仓计算
                    }

            # 更新持仓
            positions = update_data.get("P", [])
            self.positions = []
            total_unrealized_profit = 0.0

            for pos in positions:
                pos_amt = float(pos.get("pa", 0))
                if pos_amt == 0:
                    continue

                unrealized_pnl = float(pos.get("up", 0))
                total_unrealized_profit += unrealized_pnl

                pos_map = {
                    "symbol": pos.get("s"),
                    "positionAmt": pos_amt,
                    "entryPrice": float(pos.get("ep", 0)),
                    "markPrice": float(pos.get("mp", 0)),
                    "unRealizedProfit": unrealized_pnl,
                    "leverage": int(pos.get("l", 1)),
                    "liquidationPrice": 0.0,  # WebSocket 不提供，需要单独计算
                    "side": "long" if pos_amt > 0 else "short"
                }
                self.positions.append(pos_map)

            # 更新总未实现盈亏
            if self.account_data:
                self.account_data["totalUnrealizedProfit"] = total_unrealized_profit

            logger.debug(f"✓ 账户更新: 余额={self.account_data.get('totalWalletBalance', 0):.2f}, "
                        f"持仓数={len(self.positions)}")

            # 调用回调
            if self.on_account_update:
                await self.on_account_update(self.account_data)

            if self.on_position_update:
                await self.on_position_update(self.positions)

        except Exception as e:
            logger.error(f"❌ 处理账户更新失败: {e}")

    async def _handle_order_update(self, data: Dict):
        """处理订单更新"""
        try:
            order_data = data.get("o", {})

            order = {
                "orderId": order_data.get("i"),
                "symbol": order_data.get("s"),
                "side": order_data.get("S"),
                "type": order_data.get("o"),
                "status": order_data.get("X"),
                "price": float(order_data.get("p", 0)),
                "quantity": float(order_data.get("q", 0)),
                "executedQty": float(order_data.get("z", 0)),
                "avgPrice": float(order_data.get("ap", 0)),
                "positionSide": order_data.get("ps"),
            }

            logger.info(f"📋 订单更新: {order['symbol']} {order['side']} {order['status']}")

            # 调用回调
            if self.on_order_update:
                await self.on_order_update(order)

        except Exception as e:
            logger.error(f"❌ 处理订单更新失败: {e}")

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
                logger.warning(f"⚠️  用户数据流连接关闭: {e}")
                if self.running:
                    await self._reconnect()
                else:
                    break

            except asyncio.CancelledError:
                logger.info("📴 用户数据流读取任务被取消")
                break

            except Exception as e:
                logger.error(f"❌ 读取用户数据流消息失败: {e}")
                await asyncio.sleep(1)

    async def _reconnect(self):
        """重新连接"""
        logger.info("🔄 尝试重新连接用户数据流...")
        await asyncio.sleep(3)

        try:
            await self.connect()
        except Exception as e:
            logger.error(f"❌ 重新连接失败: {e}")
            if self.running:
                await self._reconnect()

    async def start(self):
        """启动用户数据流"""
        logger.info("🚀 启动用户数据流...")

        # 连接
        await self.connect()

        # 启动消息读取循环
        read_task = asyncio.create_task(self.read_messages())
        self.tasks.append(read_task)

        logger.success("✅ 用户数据流已启动")

    async def stop(self):
        """停止用户数据流"""
        logger.info("⏹  正在停止用户数据流...")

        self.running = False

        # 取消所有任务
        for task in self.tasks:
            task.cancel()

        # 等待任务完成
        await asyncio.gather(*self.tasks, return_exceptions=True)

        # 关闭 WebSocket
        if self.ws:
            await self.ws.close()
            self.ws = None

        # 删除 listenKey
        if self.listen_key:
            try:
                proxy = get_http_proxy()
                async with httpx.AsyncClient(
                    proxy=proxy,
                    http2=True,
                    timeout=5.0
                ) as client:
                    url = f"{self.rest_base}/fapi/v1/listenKey"
                    headers = {"X-MBX-APIKEY": self.api_key}
                    await client.delete(url, headers=headers)
                    logger.debug("✓ listenKey 已删除")
            except:
                pass

        logger.success("✅ 用户数据流已停止")

    def get_account_data(self) -> Optional[Dict[str, Any]]:
        """获取缓存的账户数据"""
        return self.account_data

    def get_positions(self) -> List[Dict[str, Any]]:
        """获取缓存的持仓数据"""
        return self.positions.copy()

    def get_orders(self) -> List[Dict[str, Any]]:
        """获取缓存的订单数据"""
        return self.orders.copy()

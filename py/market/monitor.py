"""
市场数据 WebSocket 监控器
"""

import asyncio
from typing import Dict, List, Optional
from loguru import logger
import httpx
from httpx_retry import AsyncRetryTransport, RetryPolicy
from dataclasses import dataclass
from datetime import datetime

from .websocket_client import WebSocketClient
from utils.http_config import get_http_proxy


@dataclass
class Kline:
    """K线数据"""
    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    trades: int
    quote_volume: float
    taker_buy_base_volume: float
    taker_buy_quote_volume: float


class WSMonitor:
    """WebSocket 市场数据监控器"""

    def __init__(self, batch_size: int = 150):
        # 使用 /stream 端点以支持动态订阅
        self.ws_client = WebSocketClient("wss://fstream.binance.com/stream")
        self.symbols: List[str] = []
        self.kline_data_3m: Dict[str, List[Kline]] = {}
        self.kline_data_4h: Dict[str, List[Kline]] = {}
        self.batch_size = batch_size
        self.running = False
        self.tasks: List[asyncio.Task] = []

    async def initialize(self, coins: Optional[List[str]] = None):
        """初始化监控器"""
        logger.info("🚀 初始化 WebSocket 监控器...")

        # 如果未指定币种，获取所有交易对
        if not coins or len(coins) == 0:
            self.symbols = await self._get_all_perpetual_symbols()
        else:
            self.symbols = [s.upper() if s.upper().endswith("USDT") else f"{s.upper()}USDT" for s in coins]

        logger.success(f"✓ 找到 {len(self.symbols)} 个交易对")

        # 初始化历史数据
        await self._initialize_historical_data()

        return True

    async def _get_all_perpetual_symbols(self) -> List[str]:
        """获取所有永续合约交易对"""
        try:
            proxy = get_http_proxy()
            async with httpx.AsyncClient(
                proxy=proxy,
                http2=True,
                transport=AsyncRetryTransport(policy=RetryPolicy().with_max_retries(3).with_min_delay(1).with_multiplier(2)),
                timeout=10.0
            ) as client:
                response = await client.get("https://fapi.binance.com/fapi/v1/exchangeInfo")
                data = response.json()

                symbols = []
                for symbol_info in data["symbols"]:
                    if (symbol_info["status"] == "TRADING" and
                        symbol_info["contractType"] == "PERPETUAL" and
                        symbol_info["symbol"].endswith("USDT")):
                        symbols.append(symbol_info["symbol"])

                return symbols

        except Exception as e:
            logger.error(f"❌ 获取交易对列表失败: {str(e)} {e}")
            return []

    async def _initialize_historical_data(self):
        """初始化历史K线数据"""
        logger.info("📊 正在加载历史K线数据...")

        # 限制并发数量
        semaphore = asyncio.Semaphore(5)

        async def fetch_symbol_data(symbol: str):
            async with semaphore:
                try:
                    # 获取 3m K线
                    klines_3m = await self._fetch_klines(symbol, "3m", 100)
                    if klines_3m:
                        self.kline_data_3m[symbol] = klines_3m
                        logger.debug(f"✓ 加载 {symbol} 3m K线: {len(klines_3m)} 条")

                    # 获取 4h K线
                    klines_4h = await self._fetch_klines(symbol, "4h", 100)
                    if klines_4h:
                        self.kline_data_4h[symbol] = klines_4h
                        logger.debug(f"✓ 加载 {symbol} 4h K线: {len(klines_4h)} 条")

                except Exception as e:
                    logger.warning(f"⚠️  加载 {symbol} 历史数据失败: {e}")

        # 并发获取所有交易对的历史数据
        await asyncio.gather(*[fetch_symbol_data(s) for s in self.symbols])

        logger.success(f"✅ 历史数据加载完成: 3m={len(self.kline_data_3m)} 4h={len(self.kline_data_4h)}")

    async def _fetch_klines(self, symbol: str, interval: str, limit: int = 100) -> List[Kline]:
        """获取K线数据"""
        try:
            proxy = get_http_proxy()
            async with httpx.AsyncClient(
                proxy=proxy,
                http2=True,
                transport=AsyncRetryTransport(policy=RetryPolicy().with_max_retries(3).with_min_delay(1).with_multiplier(2)),
                timeout=10.0
            ) as client:
                url = "https://fapi.binance.com/fapi/v1/klines"
                params = {
                    "symbol": symbol,
                    "interval": interval,
                    "limit": limit
                }

                response = await client.get(url, params=params)
                data = response.json()

                klines = []
                for item in data:
                    kline = Kline(
                        open_time=item[0],
                        close_time=item[6],
                        open=float(item[1]),
                        high=float(item[2]),
                        low=float(item[3]),
                        close=float(item[4]),
                        volume=float(item[5]),
                        trades=item[8],
                        quote_volume=float(item[7]),
                        taker_buy_base_volume=float(item[9]),
                        taker_buy_quote_volume=float(item[10])
                    )
                    klines.append(kline)

                return klines

        except Exception as e:
            logger.error(f"❌ 获取 {symbol} {interval} K线失败: {e}")
            return []

    async def start(self, coins: Optional[List[str]] = None):
        """启动监控器"""
        logger.info("🚀 启动 WebSocket 实时监控...")

        # 初始化
        await self.initialize(coins)

        # 连接 WebSocket
        await self.ws_client.connect()

        # 订阅所有交易对
        await self._subscribe_all()

        # 启动消息读取循环
        self.running = True
        read_task = asyncio.create_task(self.ws_client.read_messages())
        self.tasks.append(read_task)

        logger.success("✅ WebSocket 监控器已启动")

    async def _subscribe_all(self):
        """订阅所有交易对"""
        logger.info("📡 开始订阅所有交易对...")

        # 币安 WebSocket 限制：每个连接最多 1024 个流
        total_streams = len(self.symbols) * 2  # 每个币种订阅 3m 和 4h
        if total_streams > 1024:
            logger.warning(f"⚠️  总流数量 {total_streams} 超过限制 1024，将只订阅前 {512} 个币种")
            self.symbols = self.symbols[:512]

        # 分批订阅（避免一次性订阅太多）
        for i in range(0, len(self.symbols), self.batch_size):
            batch = self.symbols[i:i + self.batch_size]

            # 订阅 3m 和 4h K线
            for interval in ["3m", "4h"]:
                streams = [f"{s.lower()}@kline_{interval}" for s in batch]

                # 为每个流添加订阅者队列和处理任务
                for stream in streams:
                    queue = self.ws_client.add_subscriber(stream, 500)  # 增加队列大小到500
                    # 启动处理任务
                    task = asyncio.create_task(self._handle_kline_stream(stream, queue, interval))
                    self.tasks.append(task)

                # 批量订阅流（传入流列表）
                try:
                    await self.ws_client.subscribe(streams)  # 直接传入列表
                    logger.debug(f"✓ 订阅批次 {i // self.batch_size + 1} ({interval}): {len(streams)} 个流")
                except Exception as e:
                    logger.error(f"❌ 订阅失败: {e}")

            await asyncio.sleep(0.1)  # 避免请求过快

        logger.success(f"✅ 所有交易对订阅完成: {len(self.symbols)} 个币种，共 {len(self.symbols) * 2} 个流")

    async def _handle_kline_stream(self, stream: str, queue: asyncio.Queue, interval: str):
        """处理K线数据流"""
        last_queue_warn_time = 0
        while self.running:
            try:
                # 从队列获取数据（非阻塞，快速消费）
                data = await asyncio.wait_for(queue.get(), timeout=1.0)

                # 检查队列积压情况（每10秒最多警告一次）
                queue_size = queue.qsize()
                if queue_size > 400:  # 队列使用超过80%
                    current_time = asyncio.get_event_loop().time()
                    if current_time - last_queue_warn_time > 10:
                        logger.warning(f"⚠️  队列积压: {stream} ({queue_size}/500)")
                        last_queue_warn_time = current_time

                # 解析 K线数据
                symbol = data["s"]
                k = data["k"]

                kline = Kline(
                    open_time=k["t"],
                    close_time=k["T"],
                    open=float(k["o"]),
                    high=float(k["h"]),
                    low=float(k["l"]),
                    close=float(k["c"]),
                    volume=float(k["v"]),
                    trades=k["n"],
                    quote_volume=float(k["q"]),
                    taker_buy_base_volume=float(k["V"]),
                    taker_buy_quote_volume=float(k["Q"])
                )

                # 更新K线数据（同步操作，非常快）
                self._update_kline_data(symbol, kline, interval)

            except asyncio.TimeoutError:
                continue
            except KeyError as e:
                logger.error(f"❌ 数据格式错误 {stream}: 缺少字段 {e}")
            except Exception as e:
                logger.error(f"❌ 处理K线数据失败 {stream}: {e}")
                await asyncio.sleep(0.1)  # 短暂延迟，避免错误循环

    def _update_kline_data(self, symbol: str, kline: Kline, interval: str):
        """更新K线数据"""
        # 选择数据存储
        data_map = self.kline_data_3m if interval == "3m" else self.kline_data_4h

        # 获取或创建币种数据
        if symbol not in data_map:
            data_map[symbol] = []

        klines = data_map[symbol]

        # 检查是否是新K线
        if len(klines) > 0 and klines[-1].open_time == kline.open_time:
            # 更新当前K线
            klines[-1] = kline
        else:
            # 添加新K线
            klines.append(kline)

            # 保持数据长度（最多100条）
            if len(klines) > 100:
                klines.pop(0)

    def get_current_klines(self, symbol: str, interval: str) -> Optional[List[Kline]]:
        """获取当前K线数据"""
        symbol = symbol.upper()

        # 选择数据源
        data_map = self.kline_data_3m if interval == "3m" else self.kline_data_4h

        # 返回数据
        return data_map.get(symbol)

    async def stop(self):
        """停止监控器"""
        logger.info("⏹  正在停止 WebSocket 监控器...")

        self.running = False

        # 取消所有任务
        for task in self.tasks:
            task.cancel()

        # 等待任务完成
        await asyncio.gather(*self.tasks, return_exceptions=True)

        # 关闭 WebSocket
        await self.ws_client.close()

        logger.success("✅ WebSocket 监控器已停止")


# 全局实例
ws_monitor: Optional[WSMonitor] = None


def get_monitor() -> Optional[WSMonitor]:
    """获取全局监控器实例"""
    return ws_monitor


async def init_monitor(coins: Optional[List[str]] = None, batch_size: int = 150):
    """初始化全局监控器"""
    global ws_monitor
    ws_monitor = WSMonitor(batch_size)
    await ws_monitor.start(coins)
    return ws_monitor

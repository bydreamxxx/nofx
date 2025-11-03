"""
币种池管理模块

提供两种币种池数据源：
1. AI500 评分币种池（外部API）
2. OI Top 持仓量增长Top20（外部API）

支持：
- 默认主流币种列表（BTC、ETH、SOL等）
- API获取失败时自动降级到缓存
- 缓存失败时使用默认币种
- 重试机制
- 去重合并
"""

import os
import json
import httpx
from httpx_retry import AsyncRetryTransport, RetryPolicy
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from loguru import logger
from utils.http_config import get_http_proxy


# 默认主流币种列表
DEFAULT_MAINSTREAM_COINS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "HYPEUSDT",
]


@dataclass
class CoinInfo:
    """币种信息"""
    pair: str  # 交易对符号（例如：BTCUSDT）
    score: float = 0.0  # 当前评分
    start_time: int = 0  # 开始时间（Unix时间戳）
    start_price: float = 0.0  # 开始价格
    last_score: float = 0.0  # 最新评分
    max_score: float = 0.0  # 最高评分
    max_price: float = 0.0  # 最高价格
    increase_percent: float = 0.0  # 涨幅百分比
    is_available: bool = True  # 是否可交易


@dataclass
class OIPosition:
    """持仓量数据"""
    symbol: str
    rank: int = 0
    current_oi: float = 0.0  # 当前持仓量
    oi_delta: float = 0.0  # 持仓量变化
    oi_delta_percent: float = 0.0  # 持仓量变化百分比
    oi_delta_value: float = 0.0  # 持仓量变化价值
    price_delta_percent: float = 0.0  # 价格变化百分比
    net_long: float = 0.0  # 净多仓
    net_short: float = 0.0  # 净空仓


@dataclass
class MergedCoinPool:
    """合并的币种池（AI500 + OI Top）"""
    ai500_coins: List[CoinInfo] = field(default_factory=list)
    oi_top_coins: List[OIPosition] = field(default_factory=list)
    all_symbols: List[str] = field(default_factory=list)
    symbol_sources: Dict[str, List[str]] = field(default_factory=dict)


class CoinPoolManager:
    """币种池管理器"""

    def __init__(
        self,
        use_default_coins: bool = False,
        coin_pool_api_url: str = "",
        oi_top_api_url: str = "",
        cache_dir: str = "coin_pool_cache",
        timeout: float = 30.0,
    ):
        self.use_default_coins = use_default_coins
        self.coin_pool_api_url = coin_pool_api_url
        self.oi_top_api_url = oi_top_api_url
        self.cache_dir = cache_dir
        self.timeout = timeout

        # 确保缓存目录存在
        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

    def normalize_symbol(self, symbol: str) -> str:
        """标准化币种符号"""
        symbol = symbol.strip().upper()
        if not symbol.endswith("USDT"):
            symbol = symbol + "USDT"
        return symbol

    async def get_coin_pool(self) -> List[CoinInfo]:
        """
        获取币种池列表（带重试和缓存机制）

        优先级：
        1. 如果启用默认币种 -> 返回默认列表
        2. 如果配置了API -> 从API获取（失败时重试）
        3. API失败 -> 使用缓存
        4. 缓存失败 -> 使用默认币种
        """
        # 优先检查是否启用默认币种
        if self.use_default_coins:
            logger.info("✓ 已启用默认主流币种列表")
            return self._convert_symbols_to_coins(DEFAULT_MAINSTREAM_COINS)

        # 检查API URL是否配置
        if not self.coin_pool_api_url.strip():
            logger.warning("⚠️  未配置币种池API URL，使用默认主流币种列表")
            return self._convert_symbols_to_coins(DEFAULT_MAINSTREAM_COINS)

        # 尝试从API获取（内层已有重试机制）
        try:
            coins = await self._fetch_coin_pool()
            # 成功获取后保存到缓存
            await self._save_coin_pool_cache(coins)
            return coins

        except Exception as e:
            logger.error(f"❌ API请求失败: {e}")

            # API获取失败，尝试使用缓存
            logger.warning("⚠️  尝试使用历史缓存数据...")
            try:
                cached_coins = await self._load_coin_pool_cache()
                logger.info(f"✓ 使用历史缓存数据（共{len(cached_coins)}个币种）")
                return cached_coins
            except Exception as cache_error:
                logger.warning(f"⚠️  无法加载缓存数据: {cache_error}")

            # 缓存也失败，使用默认主流币种
            logger.warning(f"⚠️  使用默认主流币种列表")
            return self._convert_symbols_to_coins(DEFAULT_MAINSTREAM_COINS)

    async def _fetch_coin_pool(self) -> List[CoinInfo]:
        """实际执行币种池请求"""
        logger.info("🔄 正在请求AI500币种池...")

        proxy = get_http_proxy()
        async with httpx.AsyncClient(
            proxy=proxy,
            transport=AsyncRetryTransport(policy=RetryPolicy().with_max_retries(3).with_min_delay(1).with_multiplier(2)),
            timeout=self.timeout
        ) as client:
            response = await client.get(self.coin_pool_api_url)
            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                raise ValueError("API返回失败状态")

            coin_data = data.get("data", {}).get("coins", [])
            if not coin_data:
                raise ValueError("币种列表为空")

            # 解析币种信息
            coins = []
            for item in coin_data:
                coin = CoinInfo(
                    pair=item.get("pair", ""),
                    score=float(item.get("score", 0)),
                    start_time=int(item.get("start_time", 0)),
                    start_price=float(item.get("start_price", 0)),
                    last_score=float(item.get("last_score", 0)),
                    max_score=float(item.get("max_score", 0)),
                    max_price=float(item.get("max_price", 0)),
                    increase_percent=float(item.get("increase_percent", 0)),
                    is_available=True,
                )
                coins.append(coin)

            logger.info(f"✓ 成功获取{len(coins)}个币种")
            return coins

    async def _save_coin_pool_cache(self, coins: List[CoinInfo]) -> None:
        """保存币种池到缓存文件"""
        cache_data = {
            "coins": [
                {
                    "pair": c.pair,
                    "score": c.score,
                    "start_time": c.start_time,
                    "start_price": c.start_price,
                    "last_score": c.last_score,
                    "max_score": c.max_score,
                    "max_price": c.max_price,
                    "increase_percent": c.increase_percent,
                }
                for c in coins
            ],
            "fetched_at": datetime.now().isoformat(),
            "source_type": "api",
        }

        cache_path = os.path.join(self.cache_dir, "latest.json")
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        logger.info(f"💾 已保存币种池缓存（{len(coins)}个币种）")

    async def _load_coin_pool_cache(self) -> List[CoinInfo]:
        """从缓存文件加载币种池"""
        cache_path = os.path.join(self.cache_dir, "latest.json")

        if not os.path.exists(cache_path):
            raise FileNotFoundError("缓存文件不存在")

        with open(cache_path, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        # 检查缓存年龄
        fetched_at_str = cache_data.get("fetched_at", "")
        if fetched_at_str:
            fetched_at = datetime.fromisoformat(fetched_at_str)
            cache_age = datetime.now() - fetched_at

            if cache_age > timedelta(hours=24):
                logger.warning(
                    f"⚠️  缓存数据较旧（{cache_age.total_seconds() / 3600:.1f}小时前），但仍可使用"
                )
            else:
                logger.info(
                    f"📂 缓存数据时间: {fetched_at.strftime('%Y-%m-%d %H:%M:%S')}（{cache_age.total_seconds() / 60:.1f}分钟前）"
                )

        # 解析币种
        coins = []
        for item in cache_data.get("coins", []):
            coin = CoinInfo(
                pair=item.get("pair", ""),
                score=float(item.get("score", 0)),
                start_time=int(item.get("start_time", 0)),
                start_price=float(item.get("start_price", 0)),
                last_score=float(item.get("last_score", 0)),
                max_score=float(item.get("max_score", 0)),
                max_price=float(item.get("max_price", 0)),
                increase_percent=float(item.get("increase_percent", 0)),
                is_available=True,
            )
            coins.append(coin)

        return coins

    async def get_available_coins(self) -> List[str]:
        """获取可用的币种列表（过滤不可用的）"""
        coins = await self.get_coin_pool()

        symbols = []
        for coin in coins:
            if coin.is_available:
                symbol = self.normalize_symbol(coin.pair)
                symbols.append(symbol)

        if not symbols:
            raise ValueError("没有可用的币种")

        return symbols

    async def get_top_rated_coins(self, limit: int) -> List[str]:
        """获取评分最高的N个币种（按评分从大到小排序）"""
        coins = await self.get_coin_pool()

        # 过滤可用的币种
        available_coins = [c for c in coins if c.is_available]

        if not available_coins:
            raise ValueError("没有可用的币种")

        # 按Score降序排序
        available_coins.sort(key=lambda x: x.score, reverse=True)

        # 取前N个
        max_count = min(limit, len(available_coins))
        symbols = [
            self.normalize_symbol(available_coins[i].pair) for i in range(max_count)
        ]

        return symbols

    def _convert_symbols_to_coins(self, symbols: List[str]) -> List[CoinInfo]:
        """将币种符号列表转换为CoinInfo列表"""
        return [
            CoinInfo(pair=symbol, score=0, is_available=True) for symbol in symbols
        ]

    # ========== OI Top（持仓量增长Top20）数据 ==========

    async def get_oi_top_positions(self) -> List[OIPosition]:
        """
        获取持仓量增长Top20数据（带重试和缓存）

        返回空列表如果：
        - 未配置API URL
        - API和缓存都失败
        """
        # 检查API URL是否配置
        if not self.oi_top_api_url.strip():
            logger.warning("⚠️  未配置OI Top API URL，跳过OI Top数据获取")
            return []

        # 尝试从API获取（内层已有重试机制）
        try:
            positions = await self._fetch_oi_top()
            # 成功获取后保存到缓存
            await self._save_oi_top_cache(positions)
            return positions

        except Exception as e:
            logger.error(f"❌ OI Top API请求失败: {e}")

            # API获取失败，尝试使用缓存
            logger.warning("⚠️  尝试使用历史缓存数据...")
            try:
                cached_positions = await self._load_oi_top_cache()
                logger.info(f"✓ 使用历史OI Top缓存数据（共{len(cached_positions)}个币种）")
                return cached_positions
            except Exception as cache_error:
                logger.warning(f"⚠️  无法加载OI Top缓存数据: {cache_error}")

            # 缓存也失败，返回空列表（OI Top是可选的）
            logger.warning(f"⚠️  跳过OI Top数据")
            return []

    async def _fetch_oi_top(self) -> List[OIPosition]:
        """实际执行OI Top请求"""
        logger.info("🔄 正在请求OI Top数据...")

        proxy = get_http_proxy()
        async with httpx.AsyncClient(
            proxy=proxy,
            transport=AsyncRetryTransport(policy=RetryPolicy().with_max_retries(3).with_min_delay(1).with_multiplier(2)),
            timeout=self.timeout
        ) as client:
            response = await client.get(self.oi_top_api_url)
            response.raise_for_status()
            data = response.json()

            if not data.get("success"):
                raise ValueError("OI Top API返回失败状态")

            positions_data = data.get("data", {}).get("positions", [])
            time_range = data.get("data", {}).get("time_range", "")

            if not positions_data:
                raise ValueError("OI Top持仓列表为空")

            # 解析持仓信息
            positions = []
            for item in positions_data:
                pos = OIPosition(
                    symbol=item.get("symbol", ""),
                    rank=int(item.get("rank", 0)),
                    current_oi=float(item.get("current_oi", 0)),
                    oi_delta=float(item.get("oi_delta", 0)),
                    oi_delta_percent=float(item.get("oi_delta_percent", 0)),
                    oi_delta_value=float(item.get("oi_delta_value", 0)),
                    price_delta_percent=float(item.get("price_delta_percent", 0)),
                    net_long=float(item.get("net_long", 0)),
                    net_short=float(item.get("net_short", 0)),
                )
                positions.append(pos)

            logger.info(f"✓ 成功获取{len(positions)}个OI Top币种（时间范围: {time_range}）")
            return positions

    async def _save_oi_top_cache(self, positions: List[OIPosition]) -> None:
        """保存OI Top数据到缓存"""
        cache_data = {
            "positions": [
                {
                    "symbol": p.symbol,
                    "rank": p.rank,
                    "current_oi": p.current_oi,
                    "oi_delta": p.oi_delta,
                    "oi_delta_percent": p.oi_delta_percent,
                    "oi_delta_value": p.oi_delta_value,
                    "price_delta_percent": p.price_delta_percent,
                    "net_long": p.net_long,
                    "net_short": p.net_short,
                }
                for p in positions
            ],
            "fetched_at": datetime.now().isoformat(),
            "source_type": "api",
        }

        cache_path = os.path.join(self.cache_dir, "oi_top_latest.json")
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        logger.info(f"💾 已保存OI Top缓存（{len(positions)}个币种）")

    async def _load_oi_top_cache(self) -> List[OIPosition]:
        """从缓存加载OI Top数据"""
        cache_path = os.path.join(self.cache_dir, "oi_top_latest.json")

        if not os.path.exists(cache_path):
            raise FileNotFoundError("OI Top缓存文件不存在")

        with open(cache_path, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        # 检查缓存年龄
        fetched_at_str = cache_data.get("fetched_at", "")
        if fetched_at_str:
            fetched_at = datetime.fromisoformat(fetched_at_str)
            cache_age = datetime.now() - fetched_at

            if cache_age > timedelta(hours=24):
                logger.warning(
                    f"⚠️  OI Top缓存数据较旧（{cache_age.total_seconds() / 3600:.1f}小时前），但仍可使用"
                )
            else:
                logger.info(
                    f"📂 OI Top缓存数据时间: {fetched_at.strftime('%Y-%m-%d %H:%M:%S')}（{cache_age.total_seconds() / 60:.1f}分钟前）"
                )

        # 解析持仓
        positions = []
        for item in cache_data.get("positions", []):
            pos = OIPosition(
                symbol=item.get("symbol", ""),
                rank=int(item.get("rank", 0)),
                current_oi=float(item.get("current_oi", 0)),
                oi_delta=float(item.get("oi_delta", 0)),
                oi_delta_percent=float(item.get("oi_delta_percent", 0)),
                oi_delta_value=float(item.get("oi_delta_value", 0)),
                price_delta_percent=float(item.get("price_delta_percent", 0)),
                net_long=float(item.get("net_long", 0)),
                net_short=float(item.get("net_short", 0)),
            )
            positions.append(pos)

        return positions

    async def get_oi_top_symbols(self) -> List[str]:
        """获取OI Top的币种符号列表"""
        positions = await self.get_oi_top_positions()
        return [self.normalize_symbol(p.symbol) for p in positions]

    async def get_merged_coin_pool(self, ai500_limit: int = 20) -> MergedCoinPool:
        """
        获取合并后的币种池（AI500 + OI Top，去重）

        Args:
            ai500_limit: AI500取前N个评分最高的币种

        Returns:
            合并后的币种池，包含来源标记
        """
        # 1. 获取AI500数据
        try:
            ai500_symbols = await self.get_top_rated_coins(ai500_limit)
        except Exception as e:
            logger.warning(f"⚠️  获取AI500数据失败: {e}")
            ai500_symbols = []

        # 2. 获取OI Top数据
        try:
            oi_top_symbols = await self.get_oi_top_symbols()
        except Exception as e:
            logger.warning(f"⚠️  获取OI Top数据失败: {e}")
            oi_top_symbols = []

        # 3. 合并并去重
        symbol_set = set()
        symbol_sources: Dict[str, List[str]] = {}

        # 添加AI500币种
        for symbol in ai500_symbols:
            symbol_set.add(symbol)
            if symbol not in symbol_sources:
                symbol_sources[symbol] = []
            symbol_sources[symbol].append("ai500")

        # 添加OI Top币种
        for symbol in oi_top_symbols:
            symbol_set.add(symbol)
            if symbol not in symbol_sources:
                symbol_sources[symbol] = []
            symbol_sources[symbol].append("oi_top")

        # 转换为列表
        all_symbols = list(symbol_set)

        # 获取完整数据
        try:
            ai500_coins = await self.get_coin_pool()
        except Exception:
            ai500_coins = []

        try:
            oi_top_positions = await self.get_oi_top_positions()
        except Exception:
            oi_top_positions = []

        merged = MergedCoinPool(
            ai500_coins=ai500_coins,
            oi_top_coins=oi_top_positions,
            all_symbols=all_symbols,
            symbol_sources=symbol_sources,
        )

        logger.info(
            f"📊 币种池合并完成: AI500={len(ai500_symbols)}, OI_Top={len(oi_top_symbols)}, 总计(去重)={len(all_symbols)}"
        )

        return merged

    async def _async_sleep(self, seconds: float) -> None:
        """异步睡眠（避免导入asyncio）"""
        import asyncio

        await asyncio.sleep(seconds)

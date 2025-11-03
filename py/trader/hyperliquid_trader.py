"""
Hyperliquid 交易器实现

Hyperliquid 是一个去中心化的永续合约交易所
需要使用以太坊私钥进行签名
"""

import asyncio
import httpx
from httpx_retry import AsyncRetryTransport, RetryPolicy
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from eth_account import Account
from eth_account.messages import encode_defunct
from loguru import logger
from utils.http_config import get_http_proxy

from .interface import Trader


class HyperliquidTrader(Trader):
    """Hyperliquid 交易器"""

    def __init__(
        self, private_key: str, wallet_address: str, testnet: bool = False
    ):
        """
        初始化 Hyperliquid 交易器

        Args:
            private_key: 以太坊私钥（带或不带0x前缀）
            wallet_address: 钱包地址
            testnet: 是否使用测试网
        """
        self.wallet_address = wallet_address
        self.testnet = testnet

        # 处理私钥格式
        if private_key.startswith('0x'):
            private_key = private_key[2:]

        # 创建账户
        self.account = Account.from_key(private_key)

        # API 端点
        if testnet:
            self.base_url = "https://api.hyperliquid-testnet.xyz"
        else:
            self.base_url = "https://api.hyperliquid.xyz"

        # 缓存
        self.balance_cache: Optional[Dict[str, Any]] = None
        self.balance_cache_time: Optional[datetime] = None
        self.cache_duration = timedelta(seconds=15)

        # Meta 信息缓存
        self.meta_cache: Optional[Dict[str, Any]] = None

        logger.info(f"✅ Hyperliquid 交易器初始化成功 (testnet={testnet}, wallet={wallet_address})")

    async def _sign_request(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """签名请求"""
        import json
        from eth_utils import keccak

        # 构建签名数据
        action_str = json.dumps(action, separators=(',', ':'))
        message_hash = keccak(text=action_str)

        # 使用私钥签名
        signature = self.account.signHash(message_hash)

        return {
            "action": action,
            "signature": {
                "r": hex(signature.r),
                "s": hex(signature.s),
                "v": signature.v
            },
            "nonce": int(datetime.now().timestamp() * 1000)
        }

    async def _post_request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """发送 POST 请求"""
        url = f"{self.base_url}{endpoint}"

        proxy = get_http_proxy()
        async with httpx.AsyncClient(
            proxy=proxy,
            transport=AsyncRetryTransport(policy=RetryPolicy().with_max_retries(3).with_min_delay(1).with_multiplier(2)),
            timeout=30.0
        ) as client:
            response = await client.post(url, json=data)
            response.raise_for_status()
            return response.json()

    async def _get_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """发送 GET 请求"""
        url = f"{self.base_url}{endpoint}"

        proxy = get_http_proxy()
        async with httpx.AsyncClient(
            proxy=proxy,
            transport=AsyncRetryTransport(policy=RetryPolicy().with_max_retries(3).with_min_delay(1).with_multiplier(2)),
            timeout=30.0
        ) as client:
            response = await client.post(url, json=params or {})  # Hyperliquid 使用 POST
            response.raise_for_status()
            return response.json()

    async def get_meta(self) -> Dict[str, Any]:
        """获取交易所元数据（包含精度等信息）"""
        if self.meta_cache:
            return self.meta_cache

        data = await self._get_request("/info", {"type": "meta"})
        self.meta_cache = data
        return data

    async def get_balance(self) -> Dict[str, Any]:
        """获取账户余额"""
        # 检查缓存
        if self.balance_cache and self.balance_cache_time:
            if datetime.now() - self.balance_cache_time < self.cache_duration:
                return self.balance_cache

        logger.info("🔄 正在调用 Hyperliquid API 获取账户余额...")

        # 获取账户状态
        user_state = await self._get_request(
            "/info",
            {"type": "clearinghouseState", "user": self.wallet_address}
        )

        # 解析余额
        margin_summary = user_state.get("marginSummary", {})

        # 计算总未实现盈亏（从所有持仓）
        total_unrealized_pnl = 0.0
        asset_positions = user_state.get("assetPositions", [])
        for asset_pos in asset_positions:
            position = asset_pos.get("position", {})
            unrealized_pnl = float(position.get("unrealizedPnl", 0))
            total_unrealized_pnl += unrealized_pnl

        account_value = float(margin_summary.get("accountValue", 0))
        total_margin_used = float(margin_summary.get("totalMarginUsed", 0))

        # 计算钱包余额（账户价值 - 未实现盈亏）
        total_wallet_balance = account_value - total_unrealized_pnl
        available_balance = account_value - total_margin_used

        result = {
            "totalWalletBalance": total_wallet_balance,
            "totalUnrealizedProfit": total_unrealized_pnl,
            "availableBalance": available_balance,
            "balance": account_value
        }

        # 更新缓存
        self.balance_cache = result
        self.balance_cache_time = datetime.now()

        logger.info(f"✅ 账户余额: {account_value:.4f} USDC")
        return result

    async def get_positions(self) -> List[Dict[str, Any]]:
        """获取持仓信息"""
        logger.info("🔄 正在获取持仓信息...")

        user_state = await self._get_request(
            "/info",
            {"type": "clearinghouseState", "user": self.wallet_address}
        )

        positions = []
        asset_positions = user_state.get("assetPositions", [])

        for asset_pos in asset_positions:
            position = asset_pos.get("position", {})
            szi = float(position.get("szi", 0))

            if abs(szi) < 0.00001:  # 忽略极小持仓
                continue

            coin = position.get("coin", "")
            entry_px = float(position.get("entryPx", 0))
            position_value = float(position.get("positionValue", 0))
            unrealized_pnl = float(position.get("unrealizedPnl", 0))
            liquidation_px = float(position.get("liquidationPx", 0))
            leverage = asset_pos.get("position", {}).get("leverage", {}).get("value", 1)

            # 获取标记价格
            mark_px = entry_px  # 简化处理，实际应该从 market data 获取

            positions.append({
                "symbol": f"{coin}USDT",  # 转换为统一格式
                "side": "long" if szi > 0 else "short",
                "positionAmt": abs(szi),
                "entryPrice": entry_px,
                "markPrice": mark_px,
                "unRealizedProfit": unrealized_pnl,
                "liquidationPrice": liquidation_px if liquidation_px > 0 else 0,
                "leverage": int(leverage)
            })

        logger.info(f"✅ 找到 {len(positions)} 个持仓")
        return positions

    async def open_long(self, symbol: str, quantity: float, leverage: int) -> Dict[str, Any]:
        """开多仓"""
        logger.info(f"📈 开多仓: {symbol} 数量={quantity} 杠杆={leverage}x")

        # Hyperliquid 使用 coin 名称（不带 USDT）
        coin = symbol.replace("USDT", "")

        # 构建订单
        action = {
            "type": "order",
            "orders": [{
                "coin": coin,
                "is_buy": True,
                "sz": quantity,
                "limit_px": 0,  # 市价单
                "order_type": {"limit": {"tif": "Ioc"}},  # Immediate or Cancel
                "reduce_only": False
            }],
            "grouping": "na"
        }

        # 签名并发送
        signed_request = await self._sign_request(action)
        result = await self._post_request("/exchange", signed_request)

        logger.info(f"✅ 开多仓成功: {result}")
        return result

    async def open_short(self, symbol: str, quantity: float, leverage: int) -> Dict[str, Any]:
        """开空仓"""
        logger.info(f"📉 开空仓: {symbol} 数量={quantity} 杠杆={leverage}x")

        coin = symbol.replace("USDT", "")

        action = {
            "type": "order",
            "orders": [{
                "coin": coin,
                "is_buy": False,
                "sz": quantity,
                "limit_px": 0,
                "order_type": {"limit": {"tif": "Ioc"}},
                "reduce_only": False
            }],
            "grouping": "na"
        }

        signed_request = await self._sign_request(action)
        result = await self._post_request("/exchange", signed_request)

        logger.info(f"✅ 开空仓成功: {result}")
        return result

    async def close_long(self, symbol: str, quantity: float) -> Dict[str, Any]:
        """平多仓"""
        logger.info(f"🔻 平多仓: {symbol} 数量={quantity}")

        coin = symbol.replace("USDT", "")

        action = {
            "type": "order",
            "orders": [{
                "coin": coin,
                "is_buy": False,  # 平多用卖单
                "sz": quantity,
                "limit_px": 0,
                "order_type": {"limit": {"tif": "Ioc"}},
                "reduce_only": True
            }],
            "grouping": "na"
        }

        signed_request = await self._sign_request(action)
        result = await self._post_request("/exchange", signed_request)

        logger.info(f"✅ 平多仓成功: {result}")
        return result

    async def close_short(self, symbol: str, quantity: float) -> Dict[str, Any]:
        """平空仓"""
        logger.info(f"🔺 平空仓: {symbol} 数量={quantity}")

        coin = symbol.replace("USDT", "")

        action = {
            "type": "order",
            "orders": [{
                "coin": coin,
                "is_buy": True,  # 平空用买单
                "sz": quantity,
                "limit_px": 0,
                "order_type": {"limit": {"tif": "Ioc"}},
                "reduce_only": True
            }],
            "grouping": "na"
        }

        signed_request = await self._sign_request(action)
        result = await self._post_request("/exchange", signed_request)

        logger.info(f"✅ 平空仓成功: {result}")
        return result

    async def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """设置杠杆"""
        logger.info(f"⚙️ 设置杠杆: {symbol} = {leverage}x")

        coin = symbol.replace("USDT", "")

        action = {
            "type": "updateLeverage",
            "coin": coin,
            "is_cross": True,  # 全仓模式
            "leverage": leverage
        }

        signed_request = await self._sign_request(action)
        result = await self._post_request("/exchange", signed_request)

        logger.info(f"✅ 杠杆设置成功")
        return result

    async def set_stop_loss_take_profit(
        self, symbol: str, side: str, stop_loss: float, take_profit: float
    ) -> Dict[str, Any]:
        """设置止损止盈"""
        logger.info(f"🎯 设置止损止盈: {symbol} SL={stop_loss} TP={take_profit}")

        # Hyperliquid 的止损止盈需要通过触发订单实现
        # 这里简化处理，实际应该创建两个触发订单
        logger.warning("⚠️ Hyperliquid 止损止盈功能需要手动实现触发订单")

        return {"status": "not_implemented"}

    async def format_quantity(self, symbol: str, quantity: float) -> float:
        """格式化数量到交易所精度"""
        # 获取 meta 信息
        meta = await self.get_meta()

        # 查找对应的 coin
        coin = symbol.replace("USDT", "")
        universe = meta.get("universe", [])

        for asset in universe:
            if asset.get("name") == coin:
                sz_decimals = asset.get("szDecimals", 0)
                # 按精度四舍五入
                formatted = round(quantity, sz_decimals)
                logger.info(f"📏 数量格式化: {quantity} -> {formatted} (精度={sz_decimals})")
                return formatted

        # 默认返回原值
        return quantity

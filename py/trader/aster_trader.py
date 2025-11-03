"""
Aster DEX 交易器实现

Aster 是一个与 Binance API 兼容的去中心化交易所
使用 Web3 钱包身份验证（EIP-712 签名）
"""

import asyncio
import httpx
from httpx_retry import AsyncRetryTransport, RetryPolicy
import hashlib
import hmac
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from eth_account import Account
from eth_account.messages import encode_structured_data
from loguru import logger
from utils.http_config import get_http_proxy

from .interface import Trader


class AsterTrader(Trader):
    """Aster DEX 交易器"""

    def __init__(
        self, private_key: str, wallet_address: str, testnet: bool = False
    ):
        """
        初始化 Aster 交易器

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
            self.base_url = "https://testnet-api.aster.exchange"
        else:
            self.base_url = "https://api.aster.exchange"

        # 缓存
        self.balance_cache: Optional[Dict[str, Any]] = None
        self.balance_cache_time: Optional[datetime] = None
        self.cache_duration = timedelta(seconds=15)

        # Exchange info 缓存
        self.exchange_info_cache: Optional[Dict[str, Any]] = None

        logger.info(f"✅ Aster DEX 交易器初始化成功 (testnet={testnet}, wallet={wallet_address})")

    def _generate_eip712_signature(self, endpoint: str, params: Dict[str, Any]) -> str:
        """
        生成 EIP-712 签名用于身份验证

        Args:
            endpoint: API 端点
            params: 请求参数

        Returns:
            签名字符串
        """
        # 构建 EIP-712 结构化数据
        timestamp = int(time.time() * 1000)

        structured_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                ],
                "AsterRequest": [
                    {"name": "endpoint", "type": "string"},
                    {"name": "timestamp", "type": "uint256"},
                    {"name": "params", "type": "string"},
                ]
            },
            "primaryType": "AsterRequest",
            "domain": {
                "name": "Aster DEX",
                "version": "1",
                "chainId": 1 if not self.testnet else 5,  # Mainnet or Goerli
            },
            "message": {
                "endpoint": endpoint,
                "timestamp": timestamp,
                "params": str(sorted(params.items())),
            }
        }

        # 使用私钥签名
        encoded_data = encode_structured_data(structured_data)
        signed_message = self.account.sign_message(encoded_data)

        return signed_message.signature.hex()

    async def _request(
        self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, signed: bool = False
    ) -> Dict[str, Any]:
        """
        发送 HTTP 请求

        Args:
            method: HTTP 方法 (GET, POST, DELETE 等)
            endpoint: API 端点
            params: 请求参数
            signed: 是否需要签名

        Returns:
            响应 JSON
        """
        url = f"{self.base_url}{endpoint}"
        params = params or {}

        headers = {
            "Content-Type": "application/json"
        }

        # 如果需要签名，添加 Web3 认证头
        if signed:
            timestamp = str(int(time.time() * 1000))
            signature = self._generate_eip712_signature(endpoint, params)

            headers["X-ASTER-WALLET"] = self.wallet_address
            headers["X-ASTER-TIMESTAMP"] = timestamp
            headers["X-ASTER-SIGNATURE"] = signature

        proxy = get_http_proxy()
        async with httpx.AsyncClient(
            proxy=proxy,
            transport=AsyncRetryTransport(policy=RetryPolicy().with_max_retries(3).with_min_delay(1).with_multiplier(2)),
            timeout=30.0
        ) as client:
            if method == "GET":
                response = await client.get(url, params=params, headers=headers)
            elif method == "POST":
                response = await client.post(url, json=params, headers=headers)
            elif method == "DELETE":
                response = await client.delete(url, params=params, headers=headers)
            else:
                raise ValueError(f"不支持的 HTTP 方法: {method}")

            response.raise_for_status()
            return response.json()

    async def get_exchange_info(self) -> Dict[str, Any]:
        """获取交易所信息（缓存）"""
        if self.exchange_info_cache:
            return self.exchange_info_cache

        data = await self._request("GET", "/fapi/v1/exchangeInfo")
        self.exchange_info_cache = data
        return data

    async def get_balance(self) -> Dict[str, Any]:
        """获取账户余额"""
        # 检查缓存
        if self.balance_cache and self.balance_cache_time:
            if datetime.now() - self.balance_cache_time < self.cache_duration:
                return self.balance_cache

        logger.info("🔄 正在调用 Aster API 获取账户余额...")

        # 获取账户信息（需要签名）
        account_info = await self._request("GET", "/fapi/v2/account", signed=True)

        # 解析余额（与 Binance 格式相同）
        total_wallet_balance = float(account_info.get("totalWalletBalance", 0))
        total_unrealized_profit = float(account_info.get("totalUnrealizedProfit", 0))
        available_balance = float(account_info.get("availableBalance", 0))
        balance = total_wallet_balance + total_unrealized_profit

        result = {
            "totalWalletBalance": total_wallet_balance,
            "totalUnrealizedProfit": total_unrealized_profit,
            "availableBalance": available_balance,
            "balance": balance
        }

        # 更新缓存
        self.balance_cache = result
        self.balance_cache_time = datetime.now()

        logger.info(f"✅ 账户余额: {balance:.4f} USDT")
        return result

    async def get_positions(self) -> List[Dict[str, Any]]:
        """获取持仓信息"""
        logger.info("🔄 正在获取持仓信息...")

        # 获取持仓（需要签名）
        positions_data = await self._request("GET", "/fapi/v2/positionRisk", signed=True)

        positions = []
        for pos in positions_data:
            position_amt = float(pos.get("positionAmt", 0))

            # 过滤空持仓
            if abs(position_amt) < 0.00001:
                continue

            symbol = pos.get("symbol", "")
            entry_price = float(pos.get("entryPrice", 0))
            mark_price = float(pos.get("markPrice", 0))
            unrealized_profit = float(pos.get("unRealizedProfit", 0))
            liquidation_price = float(pos.get("liquidationPrice", 0))
            leverage = int(pos.get("leverage", 1))

            positions.append({
                "symbol": symbol,
                "side": "long" if position_amt > 0 else "short",
                "positionAmt": abs(position_amt),
                "entryPrice": entry_price,
                "markPrice": mark_price,
                "unRealizedProfit": unrealized_profit,
                "liquidationPrice": liquidation_price if liquidation_price > 0 else 0,
                "leverage": leverage
            })

        logger.info(f"✅ 找到 {len(positions)} 个持仓")
        return positions

    async def open_long(self, symbol: str, quantity: float, leverage: int) -> Dict[str, Any]:
        """开多仓"""
        logger.info(f"📈 开多仓: {symbol} 数量={quantity} 杠杆={leverage}x")

        # 1. 设置杠杆
        await self.set_leverage(symbol, leverage)

        # 2. 下市价单
        params = {
            "symbol": symbol,
            "side": "BUY",
            "positionSide": "BOTH",  # 单向持仓模式
            "type": "MARKET",
            "quantity": quantity,
        }

        result = await self._request("POST", "/fapi/v1/order", params=params, signed=True)

        logger.info(f"✅ 开多仓成功: {result}")
        return result

    async def open_short(self, symbol: str, quantity: float, leverage: int) -> Dict[str, Any]:
        """开空仓"""
        logger.info(f"📉 开空仓: {symbol} 数量={quantity} 杠杆={leverage}x")

        # 1. 设置杠杆
        await self.set_leverage(symbol, leverage)

        # 2. 下市价单
        params = {
            "symbol": symbol,
            "side": "SELL",
            "positionSide": "BOTH",
            "type": "MARKET",
            "quantity": quantity,
        }

        result = await self._request("POST", "/fapi/v1/order", params=params, signed=True)

        logger.info(f"✅ 开空仓成功: {result}")
        return result

    async def close_long(self, symbol: str, quantity: float) -> Dict[str, Any]:
        """平多仓"""
        logger.info(f"🔻 平多仓: {symbol} 数量={quantity}")

        params = {
            "symbol": symbol,
            "side": "SELL",
            "positionSide": "BOTH",
            "type": "MARKET",
            "quantity": quantity,
            "reduceOnly": "true"
        }

        result = await self._request("POST", "/fapi/v1/order", params=params, signed=True)

        logger.info(f"✅ 平多仓成功: {result}")
        return result

    async def close_short(self, symbol: str, quantity: float) -> Dict[str, Any]:
        """平空仓"""
        logger.info(f"🔺 平空仓: {symbol} 数量={quantity}")

        params = {
            "symbol": symbol,
            "side": "BUY",
            "positionSide": "BOTH",
            "type": "MARKET",
            "quantity": quantity,
            "reduceOnly": "true"
        }

        result = await self._request("POST", "/fapi/v1/order", params=params, signed=True)

        logger.info(f"✅ 平空仓成功: {result}")
        return result

    async def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """设置杠杆"""
        logger.info(f"⚙️ 设置杠杆: {symbol} = {leverage}x")

        params = {
            "symbol": symbol,
            "leverage": leverage
        }

        result = await self._request("POST", "/fapi/v1/leverage", params=params, signed=True)

        logger.info(f"✅ 杠杆设置成功")
        return result

    async def set_stop_loss_take_profit(
        self, symbol: str, side: str, stop_loss: float, take_profit: float
    ) -> Dict[str, Any]:
        """设置止损止盈"""
        logger.info(f"🎯 设置止损止盈: {symbol} SL={stop_loss} TP={take_profit}")

        results = []

        # 止损单
        if stop_loss > 0:
            sl_side = "SELL" if side == "long" else "BUY"
            sl_params = {
                "symbol": symbol,
                "side": sl_side,
                "positionSide": "BOTH",
                "type": "STOP_MARKET",
                "stopPrice": stop_loss,
                "closePosition": "true"
            }
            sl_result = await self._request("POST", "/fapi/v1/order", params=sl_params, signed=True)
            results.append(sl_result)
            logger.info(f"✅ 止损单已设置: {stop_loss}")

        # 止盈单
        if take_profit > 0:
            tp_side = "SELL" if side == "long" else "BUY"
            tp_params = {
                "symbol": symbol,
                "side": tp_side,
                "positionSide": "BOTH",
                "type": "TAKE_PROFIT_MARKET",
                "stopPrice": take_profit,
                "closePosition": "true"
            }
            tp_result = await self._request("POST", "/fapi/v1/order", params=tp_params, signed=True)
            results.append(tp_result)
            logger.info(f"✅ 止盈单已设置: {take_profit}")

        return {"stop_loss": results[0] if len(results) > 0 else None,
                "take_profit": results[1] if len(results) > 1 else None}

    async def format_quantity(self, symbol: str, quantity: float) -> float:
        """格式化数量到交易所精度"""
        # 获取交易所信息
        exchange_info = await self.get_exchange_info()

        # 查找对应的交易对
        for s in exchange_info.get("symbols", []):
            if s.get("symbol") == symbol:
                filters = s.get("filters", [])

                # 查找 LOT_SIZE 过滤器
                for f in filters:
                    if f.get("filterType") == "LOT_SIZE":
                        step_size = float(f.get("stepSize", 1))

                        # 计算精度
                        import math
                        if step_size >= 1:
                            precision = 0
                        else:
                            precision = int(round(-math.log10(step_size)))

                        # 格式化数量
                        formatted = round(quantity / step_size) * step_size
                        formatted = round(formatted, precision)

                        logger.info(f"📏 数量格式化: {quantity} -> {formatted} (精度={precision})")
                        return formatted

        # 默认保留4位小数
        logger.warning(f"⚠️ 未找到 {symbol} 的精度信息，使用默认精度")
        return round(quantity, 4)

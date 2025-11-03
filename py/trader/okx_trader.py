"""
OKX 交易器实现

使用 CCXT 库简化 OKX 交易所集成
支持永续合约交易
"""

import asyncio
import ccxt.async_support as ccxt
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from loguru import logger

from .interface import Trader


class OKXTrader(Trader):
    """OKX 交易器"""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str,
        testnet: bool = False
    ):
        """
        初始化 OKX 交易器

        Args:
            api_key: API 密钥
            api_secret: API 秘密
            passphrase: API 口令
            testnet: 是否使用测试网
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.testnet = testnet

        # 创建 CCXT 实例
        self.exchange = ccxt.okx({
            'apiKey': api_key,
            'secret': api_secret,
            'password': passphrase,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',  # 使用永续合约
            }
        })

        # 测试网配置
        if testnet:
            self.exchange.set_sandbox_mode(True)

        # 缓存
        self.balance_cache: Optional[Dict[str, Any]] = None
        self.balance_cache_time: Optional[datetime] = None
        self.cache_duration = timedelta(seconds=15)

        # Markets 缓存
        self.markets_cache: Optional[Dict[str, Any]] = None

        logger.info(f"✅ OKX 交易器初始化成功 (testnet={testnet})")

    async def _load_markets(self) -> Dict[str, Any]:
        """加载市场信息（缓存）"""
        if self.markets_cache is None:
            self.markets_cache = await self.exchange.load_markets()
        return self.markets_cache

    def _convert_symbol_to_okx(self, symbol: str) -> str:
        """
        将标准格式 symbol 转换为 OKX 格式
        BTCUSDT -> BTC/USDT:USDT
        """
        if symbol.endswith("USDT"):
            base = symbol[:-4]
            return f"{base}/USDT:USDT"
        return symbol

    def _convert_symbol_from_okx(self, okx_symbol: str) -> str:
        """
        将 OKX 格式 symbol 转换为标准格式
        BTC/USDT:USDT -> BTCUSDT
        """
        if "/" in okx_symbol:
            base = okx_symbol.split("/")[0]
            return f"{base}USDT"
        return okx_symbol

    async def get_balance(self) -> Dict[str, Any]:
        """获取账户余额"""
        # 检查缓存
        if self.balance_cache and self.balance_cache_time:
            if datetime.now() - self.balance_cache_time < self.cache_duration:
                return self.balance_cache

        logger.info("🔄 正在调用 OKX API 获取账户余额...")

        # 获取余额
        balance_data = await self.exchange.fetch_balance()

        # 解析 USDT 余额
        usdt_balance = balance_data.get("USDT", {})
        total_wallet_balance = float(usdt_balance.get("total", 0))
        free_balance = float(usdt_balance.get("free", 0))
        used_balance = float(usdt_balance.get("used", 0))

        # 获取未实现盈亏
        positions = await self.get_positions()
        total_unrealized_profit = sum(p.get("unRealizedProfit", 0) for p in positions)

        result = {
            "totalWalletBalance": total_wallet_balance,
            "totalUnrealizedProfit": total_unrealized_profit,
            "availableBalance": free_balance,
            "balance": total_wallet_balance + total_unrealized_profit
        }

        # 更新缓存
        self.balance_cache = result
        self.balance_cache_time = datetime.now()

        logger.info(f"✅ 账户余额: {result['balance']:.4f} USDT")
        return result

    async def get_positions(self) -> List[Dict[str, Any]]:
        """获取持仓信息"""
        logger.info("🔄 正在获取持仓信息...")

        # 获取所有持仓
        positions_data = await self.exchange.fetch_positions()

        positions = []
        for pos in positions_data:
            contracts = float(pos.get("contracts", 0))

            # 过滤空持仓
            if abs(contracts) < 0.0001:
                continue

            symbol = self._convert_symbol_from_okx(pos.get("symbol", ""))
            side = pos.get("side", "")  # "long" or "short"
            entry_price = float(pos.get("entryPrice", 0))
            mark_price = float(pos.get("markPrice", 0))
            unrealized_pnl = float(pos.get("unrealizedPnl", 0))
            liquidation_price = float(pos.get("liquidationPrice", 0))
            leverage = float(pos.get("leverage", 1))

            positions.append({
                "symbol": symbol,
                "side": side,
                "positionAmt": abs(contracts),
                "entryPrice": entry_price,
                "markPrice": mark_price,
                "unRealizedProfit": unrealized_pnl,
                "liquidationPrice": liquidation_price if liquidation_price > 0 else 0,
                "leverage": int(leverage)
            })

        logger.info(f"✅ 找到 {len(positions)} 个持仓")
        return positions

    async def open_long(self, symbol: str, quantity: float, leverage: int) -> Dict[str, Any]:
        """开多仓"""
        logger.info(f"📈 开多仓: {symbol} 数量={quantity} 杠杆={leverage}x")

        # 1. 设置杠杆
        await self.set_leverage(symbol, leverage)

        # 2. 转换 symbol 格式
        okx_symbol = self._convert_symbol_to_okx(symbol)

        # 3. 下市价单
        order = await self.exchange.create_market_buy_order(
            symbol=okx_symbol,
            amount=quantity,
            params={'tdMode': 'cross'}  # 全仓模式
        )

        logger.info(f"✅ 开多仓成功: {order['id']}")
        return order

    async def open_short(self, symbol: str, quantity: float, leverage: int) -> Dict[str, Any]:
        """开空仓"""
        logger.info(f"📉 开空仓: {symbol} 数量={quantity} 杠杆={leverage}x")

        # 1. 设置杠杆
        await self.set_leverage(symbol, leverage)

        # 2. 转换 symbol 格式
        okx_symbol = self._convert_symbol_to_okx(symbol)

        # 3. 下市价单
        order = await self.exchange.create_market_sell_order(
            symbol=okx_symbol,
            amount=quantity,
            params={'tdMode': 'cross'}
        )

        logger.info(f"✅ 开空仓成功: {order['id']}")
        return order

    async def close_long(self, symbol: str, quantity: float) -> Dict[str, Any]:
        """平多仓"""
        logger.info(f"🔻 平多仓: {symbol} 数量={quantity}")

        okx_symbol = self._convert_symbol_to_okx(symbol)

        # 平多仓用卖单
        order = await self.exchange.create_market_sell_order(
            symbol=okx_symbol,
            amount=quantity,
            params={
                'tdMode': 'cross',
                'reduceOnly': True
            }
        )

        logger.info(f"✅ 平多仓成功: {order['id']}")
        return order

    async def close_short(self, symbol: str, quantity: float) -> Dict[str, Any]:
        """平空仓"""
        logger.info(f"🔺 平空仓: {symbol} 数量={quantity}")

        okx_symbol = self._convert_symbol_to_okx(symbol)

        # 平空仓用买单
        order = await self.exchange.create_market_buy_order(
            symbol=okx_symbol,
            amount=quantity,
            params={
                'tdMode': 'cross',
                'reduceOnly': True
            }
        )

        logger.info(f"✅ 平空仓成功: {order['id']}")
        return order

    async def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """设置杠杆"""
        logger.info(f"⚙️ 设置杠杆: {symbol} = {leverage}x")

        okx_symbol = self._convert_symbol_to_okx(symbol)

        try:
            result = await self.exchange.set_leverage(
                leverage=leverage,
                symbol=okx_symbol,
                params={'mgnMode': 'cross'}  # 全仓模式
            )
            logger.info(f"✅ 杠杆设置成功")
            return result
        except Exception as e:
            logger.warning(f"⚠️ 设置杠杆失败: {e}")
            # 某些情况下杠杆可能已经设置好，继续执行
            return {"success": False, "error": str(e)}

    async def set_stop_loss_take_profit(
        self, symbol: str, side: str, stop_loss: float, take_profit: float
    ) -> Dict[str, Any]:
        """设置止损止盈"""
        logger.info(f"🎯 设置止损止盈: {symbol} SL={stop_loss} TP={take_profit}")

        okx_symbol = self._convert_symbol_to_okx(symbol)

        results = []

        try:
            # 止损单
            if stop_loss > 0:
                sl_order = await self.exchange.create_order(
                    symbol=okx_symbol,
                    type='stop',
                    side='sell' if side == 'long' else 'buy',
                    amount=0,  # 0 表示全部平仓
                    price=None,
                    params={
                        'stopLossPrice': stop_loss,
                        'reduceOnly': True,
                        'tdMode': 'cross'
                    }
                )
                results.append(sl_order)
                logger.info(f"✅ 止损单已设置: {stop_loss}")

            # 止盈单
            if take_profit > 0:
                tp_order = await self.exchange.create_order(
                    symbol=okx_symbol,
                    type='stop',
                    side='sell' if side == 'long' else 'buy',
                    amount=0,
                    price=None,
                    params={
                        'takeProfitPrice': take_profit,
                        'reduceOnly': True,
                        'tdMode': 'cross'
                    }
                )
                results.append(tp_order)
                logger.info(f"✅ 止盈单已设置: {take_profit}")

            return {
                "stop_loss": results[0] if len(results) > 0 else None,
                "take_profit": results[1] if len(results) > 1 else None
            }

        except Exception as e:
            logger.error(f"❌ 设置止损止盈失败: {e}")
            return {"error": str(e)}

    async def format_quantity(self, symbol: str, quantity: float) -> float:
        """格式化数量到交易所精度"""
        # 加载市场信息
        await self._load_markets()

        okx_symbol = self._convert_symbol_to_okx(symbol)

        # 获取市场精度
        market = self.markets_cache.get(okx_symbol)
        if market:
            precision = market.get('precision', {})
            amount_precision = precision.get('amount', 8)

            # 格式化数量
            formatted = round(quantity, amount_precision)
            logger.info(f"📏 数量格式化: {quantity} -> {formatted} (精度={amount_precision})")
            return formatted

        # 默认保留4位小数
        logger.warning(f"⚠️ 未找到 {symbol} 的精度信息，使用默认精度")
        return round(quantity, 4)

    async def close(self):
        """关闭交易所连接"""
        await self.exchange.close()
        logger.info("✅ OKX 交易器已关闭")

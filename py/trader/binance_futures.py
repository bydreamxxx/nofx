"""
币安期货交易器实现
"""

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from binance.client import Client as BinanceClient
from binance.exceptions import BinanceAPIException
from loguru import logger

from .interface import Trader


class BinanceFuturesTrader(Trader):
    """币安合约交易器"""

    def __init__(self, api_key: str, secret_key: str, testnet: bool = False):
        self.client = BinanceClient(api_key, secret_key, testnet=testnet)

        # 缓存配置
        self.cache_duration = timedelta(seconds=15)

        # 余额缓存
        self.cached_balance: Optional[Dict[str, Any]] = None
        self.balance_cache_time: Optional[datetime] = None

        # 持仓缓存
        self.cached_positions: Optional[List[Dict[str, Any]]] = None
        self.positions_cache_time: Optional[datetime] = None

        # 交易所信息缓存（精度信息）
        self.exchange_info: Optional[Dict] = None

    async def get_balance(self) -> Dict[str, Any]:
        """获取账户余额（带缓存）"""
        # 检查缓存
        if self.cached_balance and self.balance_cache_time:
            age = datetime.now() - self.balance_cache_time
            if age < self.cache_duration:
                logger.debug(f"✓ 使用缓存的账户余额（缓存时间: {age.total_seconds():.1f}秒前）")
                return self.cached_balance

        # 缓存过期，调用 API
        logger.debug("🔄 缓存过期，正在调用币安API获取账户余额...")

        try:
            # 使用 asyncio.to_thread 将同步调用转为异步
            account = await asyncio.to_thread(self.client.futures_account)

            result = {
                "totalWalletBalance": float(account['totalWalletBalance']),
                "availableBalance": float(account['availableBalance']),
                "totalUnrealizedProfit": float(account['totalUnrealizedProfit']),
            }

            logger.debug(
                f"✓ 币安API返回: 总余额={result['totalWalletBalance']}, "
                f"可用={result['availableBalance']}, "
                f"未实现盈亏={result['totalUnrealizedProfit']}"
            )

            # 更新缓存
            self.cached_balance = result
            self.balance_cache_time = datetime.now()

            return result

        except BinanceAPIException as e:
            logger.error(f"❌ 币安API调用失败: {e}")
            raise Exception(f"获取账户信息失败: {e}")

    async def get_positions(self) -> List[Dict[str, Any]]:
        """获取所有持仓（带缓存）"""
        # 检查缓存
        if self.cached_positions and self.positions_cache_time:
            age = datetime.now() - self.positions_cache_time
            if age < self.cache_duration:
                logger.debug(f"✓ 使用缓存的持仓信息（缓存时间: {age.total_seconds():.1f}秒前）")
                return self.cached_positions

        # 缓存过期，调用 API
        logger.debug("🔄 缓存过期，正在调用币安API获取持仓信息...")

        try:
            positions = await asyncio.to_thread(self.client.futures_position_information)

            result = []
            for pos in positions:
                pos_amt = float(pos['positionAmt'])
                if pos_amt == 0:
                    continue  # 跳过无持仓的

                pos_map = {
                    "symbol": pos['symbol'],
                    "positionAmt": pos_amt,
                    "entryPrice": float(pos['entryPrice']),
                    "markPrice": float(pos['markPrice']),
                    "unRealizedProfit": float(pos['unRealizedProfit']),
                    "leverage": int(pos['leverage']),
                    "liquidationPrice": float(pos.get('liquidationPrice', 0)),
                    "side": "long" if pos_amt > 0 else "short"
                }

                result.append(pos_map)

            # 更新缓存
            self.cached_positions = result
            self.positions_cache_time = datetime.now()

            return result

        except BinanceAPIException as e:
            logger.error(f"❌ 获取持仓失败: {e}")
            raise Exception(f"获取持仓失败: {e}")

    async def set_margin_mode(self, symbol: str, is_cross_margin: bool) -> None:
        """设置仓位模式"""
        margin_type = "CROSSED" if is_cross_margin else "ISOLATED"
        margin_mode_str = "全仓" if is_cross_margin else "逐仓"

        try:
            await asyncio.to_thread(
                self.client.futures_change_margin_type,
                symbol=symbol,
                marginType=margin_type
            )
            logger.info(f"  ✓ {symbol} 仓位模式已设置为 {margin_mode_str}")

        except BinanceAPIException as e:
            error_msg = str(e)

            # 如果已经是目标模式，不报错
            if "No need to change margin type" in error_msg:
                logger.debug(f"  ✓ {symbol} 仓位模式已是 {margin_mode_str}")
                return

            # 如果有持仓无法更改，也不报错
            if "Margin type cannot be changed if there exists position" in error_msg:
                logger.warning(f"  ⚠️ {symbol} 有持仓，无法更改仓位模式，继续使用当前模式")
                return

            logger.warning(f"  ⚠️ 设置仓位模式失败: {e}")
            # 不抛出异常，让交易继续

    async def set_leverage(self, symbol: str, leverage: int) -> None:
        """设置杠杆"""
        # 先获取当前杠杆
        current_leverage = 0
        positions = await self.get_positions()

        for pos in positions:
            if pos["symbol"] == symbol:
                current_leverage = pos.get("leverage", 0)
                break

        # 如果已经是目标杠杆，跳过
        if current_leverage == leverage and current_leverage > 0:
            logger.debug(f"  ✓ {symbol} 杠杆已是 {leverage}x，无需切换")
            return

        # 切换杠杆
        try:
            await asyncio.to_thread(
                self.client.futures_change_leverage,
                symbol=symbol,
                leverage=leverage
            )
            logger.info(f"  ✓ {symbol} 杠杆已设置为 {leverage}x")

            # 切换杠杆后等待5秒（避免冷却期错误）
            logger.debug("  ⏱ 等待5秒冷却期...")
            await asyncio.sleep(5)

        except BinanceAPIException as e:
            logger.error(f"  ❌ 设置杠杆失败: {e}")
            raise Exception(f"设置杠杆失败: {e}")

    async def get_market_price(self, symbol: str) -> float:
        """获取市场价格"""
        try:
            ticker = await asyncio.to_thread(
                self.client.futures_symbol_ticker,
                symbol=symbol
            )
            return float(ticker['price'])

        except BinanceAPIException as e:
            logger.error(f"❌ 获取{symbol}价格失败: {e}")
            raise Exception(f"获取市场价格失败: {e}")

    async def open_long(
        self, symbol: str, quantity: float, leverage: int
    ) -> Dict[str, Any]:
        """开多仓"""
        # 先取消该币种的所有委托单（清理旧的止损止盈单）
        try:
            await self.cancel_all_orders(symbol)
        except Exception as e:
            logger.warning(f"  ⚠️ 取消旧委托单失败（可能没有委托单）: {e}")

        # 设置杠杆
        await self.set_leverage(symbol, leverage)

        # 格式化数量
        formatted_qty = await self.format_quantity(symbol, quantity)

        try:
            order = await asyncio.to_thread(
                self.client.futures_create_order,
                symbol=symbol,
                side='BUY',
                positionSide='LONG',
                type='MARKET',
                quantity=formatted_qty
            )

            logger.success(f"✓ 开多仓成功: {symbol} {formatted_qty} @ {leverage}x")

            return {
                "orderId": order['orderId'],
                "symbol": symbol,
                "side": "long",
                "quantity": float(order['origQty']),
                "price": float(order.get('avgPrice', 0)),
            }

        except BinanceAPIException as e:
            logger.error(f"❌ 开多仓失败: {e}")
            raise Exception(f"开多仓失败: {e}")

    async def open_short(
        self, symbol: str, quantity: float, leverage: int
    ) -> Dict[str, Any]:
        """开空仓"""
        # 先取消该币种的所有委托单（清理旧的止损止盈单）
        try:
            await self.cancel_all_orders(symbol)
        except Exception as e:
            logger.warning(f"  ⚠️ 取消旧委托单失败（可能没有委托单）: {e}")

        # 设置杠杆
        await self.set_leverage(symbol, leverage)

        # 格式化数量
        formatted_qty = await self.format_quantity(symbol, quantity)

        try:
            order = await asyncio.to_thread(
                self.client.futures_create_order,
                symbol=symbol,
                side='SELL',
                positionSide='SHORT',
                type='MARKET',
                quantity=formatted_qty
            )

            logger.success(f"✓ 开空仓成功: {symbol} {formatted_qty} @ {leverage}x")

            return {
                "orderId": order['orderId'],
                "symbol": symbol,
                "side": "short",
                "quantity": float(order['origQty']),
                "price": float(order.get('avgPrice', 0)),
            }

        except BinanceAPIException as e:
            logger.error(f"❌ 开空仓失败: {e}")
            raise Exception(f"开空仓失败: {e}")

    async def close_long(self, symbol: str, quantity: float = 0.0) -> Dict[str, Any]:
        """平多仓"""
        # 如果 quantity=0，获取当前持仓全部平掉
        if quantity == 0:
            positions = await self.get_positions()
            for pos in positions:
                if pos["symbol"] == symbol and pos["side"] == "long":
                    quantity = abs(pos["positionAmt"])
                    break

            if quantity == 0:
                raise Exception(f"{symbol} 没有多仓持仓")

        # 格式化数量
        formatted_qty = await self.format_quantity(symbol, quantity)

        try:
            order = await asyncio.to_thread(
                self.client.futures_create_order,
                symbol=symbol,
                side='SELL',
                positionSide='LONG',
                type='MARKET',
                quantity=formatted_qty
            )

            logger.success(f"✓ 平多仓成功: {symbol} {formatted_qty}")

            # 平仓后取消该币种的所有挂单（止损止盈单）
            try:
                await self.cancel_all_orders(symbol)
            except Exception as e:
                logger.warning(f"  ⚠️ 取消挂单失败: {e}")

            return {
                "orderId": order['orderId'],
                "symbol": symbol,
                "side": "long",
                "quantity": float(order['origQty']),
                "price": float(order.get('avgPrice', 0)),
            }

        except BinanceAPIException as e:
            logger.error(f"❌ 平多仓失败: {e}")
            raise Exception(f"平多仓失败: {e}")

    async def close_short(self, symbol: str, quantity: float = 0.0) -> Dict[str, Any]:
        """平空仓"""
        # 如果 quantity=0，获取当前持仓全部平掉
        if quantity == 0:
            positions = await self.get_positions()
            for pos in positions:
                if pos["symbol"] == symbol and pos["side"] == "short":
                    quantity = abs(pos["positionAmt"])
                    break

            if quantity == 0:
                raise Exception(f"{symbol} 没有空仓持仓")

        # 格式化数量
        formatted_qty = await self.format_quantity(symbol, quantity)

        try:
            order = await asyncio.to_thread(
                self.client.futures_create_order,
                symbol=symbol,
                side='BUY',
                positionSide='SHORT',
                type='MARKET',
                quantity=formatted_qty
            )

            logger.success(f"✓ 平空仓成功: {symbol} {formatted_qty}")

            # 平仓后取消该币种的所有挂单（止损止盈单）
            try:
                await self.cancel_all_orders(symbol)
            except Exception as e:
                logger.warning(f"  ⚠️ 取消挂单失败: {e}")

            return {
                "orderId": order['orderId'],
                "symbol": symbol,
                "side": "short",
                "quantity": float(order['origQty']),
                "price": float(order.get('avgPrice', 0)),
            }

        except BinanceAPIException as e:
            logger.error(f"❌ 平空仓失败: {e}")
            raise Exception(f"平空仓失败: {e}")

    async def set_stop_loss(
        self,
        symbol: str,
        position_side: str,
        quantity: float,
        stop_price: float
    ) -> None:
        """设置止损单"""
        side = "SELL" if position_side.upper() == "LONG" else "BUY"
        formatted_qty = await self.format_quantity(symbol, quantity)

        try:
            await asyncio.to_thread(
                self.client.futures_create_order,
                symbol=symbol,
                side=side,
                positionSide=position_side.upper(),
                type='STOP_MARKET',
                quantity=formatted_qty,
                stopPrice=stop_price,
                workingType='CONTRACT_PRICE',  # 使用合约价格触发
                closePosition=True  # 触发时平掉整个持仓
            )

            logger.info(f"  ✓ 止损单已设置: {symbol} @ {stop_price}")

        except BinanceAPIException as e:
            logger.warning(f"  ⚠️ 设置止损失败: {e}")

    async def set_take_profit(
        self,
        symbol: str,
        position_side: str,
        quantity: float,
        take_profit_price: float
    ) -> None:
        """设置止盈单"""
        side = "SELL" if position_side.upper() == "LONG" else "BUY"
        formatted_qty = await self.format_quantity(symbol, quantity)

        try:
            await asyncio.to_thread(
                self.client.futures_create_order,
                symbol=symbol,
                side=side,
                positionSide=position_side.upper(),
                type='TAKE_PROFIT_MARKET',
                quantity=formatted_qty,
                stopPrice=take_profit_price,
                workingType='CONTRACT_PRICE',  # 使用合约价格触发
                closePosition=True  # 触发时平掉整个持仓
            )

            logger.info(f"  ✓ 止盈单已设置: {symbol} @ {take_profit_price}")

        except BinanceAPIException as e:
            logger.warning(f"  ⚠️ 设置止盈失败: {e}")

    async def cancel_all_orders(self, symbol: str) -> None:
        """取消该币种的所有挂单"""
        try:
            await asyncio.to_thread(
                self.client.futures_cancel_all_open_orders,
                symbol=symbol
            )
            logger.info(f"  ✓ 已取消 {symbol} 的所有挂单")

        except BinanceAPIException as e:
            logger.warning(f"  ⚠️ 取消挂单失败: {e}")

    async def format_quantity(self, symbol: str, quantity: float) -> str:
        """格式化数量到正确的精度"""
        # 获取交易所信息
        if not self.exchange_info:
            self.exchange_info = await asyncio.to_thread(
                self.client.futures_exchange_info
            )

        # 查找该币种的精度信息
        for s in self.exchange_info['symbols']:
            if s['symbol'] == symbol:
                for filter in s['filters']:
                    if filter['filterType'] == 'LOT_SIZE':
                        step_size = float(filter['stepSize'])
                        # 计算精度位数
                        precision = len(str(step_size).rstrip('0').split('.')[-1])
                        # 格式化数量
                        return f"{quantity:.{precision}f}"

        # 如果没找到，使用默认精度
        return f"{quantity:.3f}"

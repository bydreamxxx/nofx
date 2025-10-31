"""
交易器统一接口
支持多个交易平台（币安、Hyperliquid、Aster等）
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class Trader(ABC):
    """交易器抽象基类"""

    @abstractmethod
    async def get_balance(self) -> Dict[str, Any]:
        """获取账户余额"""
        pass

    @abstractmethod
    async def get_positions(self) -> List[Dict[str, Any]]:
        """获取所有持仓"""
        pass

    @abstractmethod
    async def open_long(
        self, symbol: str, quantity: float, leverage: int
    ) -> Dict[str, Any]:
        """开多仓"""
        pass

    @abstractmethod
    async def open_short(
        self, symbol: str, quantity: float, leverage: int
    ) -> Dict[str, Any]:
        """开空仓"""
        pass

    @abstractmethod
    async def close_long(
        self, symbol: str, quantity: float = 0.0
    ) -> Dict[str, Any]:
        """
        平多仓

        Args:
            symbol: 交易对
            quantity: 数量（0表示全部平仓）
        """
        pass

    @abstractmethod
    async def close_short(
        self, symbol: str, quantity: float = 0.0
    ) -> Dict[str, Any]:
        """
        平空仓

        Args:
            symbol: 交易对
            quantity: 数量（0表示全部平仓）
        """
        pass

    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: int) -> None:
        """设置杠杆"""
        pass

    @abstractmethod
    async def set_margin_mode(
        self, symbol: str, is_cross_margin: bool
    ) -> None:
        """
        设置仓位模式

        Args:
            symbol: 交易对
            is_cross_margin: True=全仓, False=逐仓
        """
        pass

    @abstractmethod
    async def get_market_price(self, symbol: str) -> float:
        """获取市场价格"""
        pass

    @abstractmethod
    async def set_stop_loss(
        self,
        symbol: str,
        position_side: str,
        quantity: float,
        stop_price: float
    ) -> None:
        """设置止损单"""
        pass

    @abstractmethod
    async def set_take_profit(
        self,
        symbol: str,
        position_side: str,
        quantity: float,
        take_profit_price: float
    ) -> None:
        """设置止盈单"""
        pass

    @abstractmethod
    async def cancel_all_orders(self, symbol: str) -> None:
        """取消该币种的所有挂单"""
        pass

    @abstractmethod
    async def format_quantity(
        self, symbol: str, quantity: float
    ) -> str:
        """格式化数量到正确的精度"""
        pass

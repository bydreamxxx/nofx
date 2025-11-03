"""
市场数据获取和技术指标计算模块
"""

from decimal import Decimal
import httpx
import pandas as pd
import pandas_ta as ta
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class OIData:
    """持仓量数据"""
    latest: float
    average: float


@dataclass
class IntradayData:
    """日内数据（3分钟间隔）"""
    mid_prices: List[float]
    ema20_values: List[float]
    macd_values: List[float]
    rsi7_values: List[float]
    rsi14_values: List[float]


@dataclass
class LongerTermData:
    """长期数据（4小时时间框架）"""
    ema20: float
    ema50: float
    atr3: float
    atr14: float
    current_volume: float
    average_volume: float
    macd_values: List[float]
    rsi14_values: List[float]


@dataclass
class MarketData:
    """市场数据结构"""
    symbol: str
    current_price: float
    price_change_1h: float  # 1小时价格变化百分比
    price_change_4h: float  # 4小时价格变化百分比
    current_ema20: float
    current_macd: float
    current_rsi7: float
    open_interest: Optional[OIData]
    funding_rate: Decimal
    intraday_series: Optional[IntradayData]
    longer_term_context: Optional[LongerTermData]


class MarketDataFetcher:
    """市场数据获取器"""

    def __init__(self):
        self.base_url = "https://fapi.binance.com"

    def normalize_symbol(self, symbol: str) -> str:
        """标准化币种符号"""
        symbol = symbol.upper()
        if not symbol.endswith("USDT"):
            symbol = symbol + "USDT"
        return symbol

    async def get(self, symbol: str) -> MarketData:
        """获取指定代币的市场数据"""
        symbol = self.normalize_symbol(symbol)

        # 获取 K 线数据
        klines_3m = await self._get_klines(symbol, "3m", 40)
        klines_4h = await self._get_klines(symbol, "4h", 60)

        # 计算当前指标（基于 3 分钟最新数据）
        df_3m = pd.DataFrame(klines_3m)
        current_price = df_3m['close'].iloc[-1]
        current_ema20 = self._calculate_ema(df_3m['close'], 20).iloc[-1]
        current_macd = self._calculate_macd(df_3m['close'])
        current_rsi7 = self._calculate_rsi(df_3m['close'], 7).iloc[-1]

        # 计算价格变化百分比
        price_change_1h = 0.0
        if len(df_3m) >= 21:
            price_1h_ago = df_3m['close'].iloc[-21]
            if price_1h_ago > 0:
                price_change_1h = ((current_price - price_1h_ago) / price_1h_ago) * 100

        df_4h = pd.DataFrame(klines_4h)
        price_change_4h = 0.0
        if len(df_4h) >= 2:
            price_4h_ago = df_4h['close'].iloc[-2]
            if price_4h_ago > 0:
                price_change_4h = ((current_price - price_4h_ago) / price_4h_ago) * 100

        # 获取 OI 数据
        oi_data = await self._get_open_interest_history(symbol)

        # 获取 Funding Rate
        funding_rate = await self._get_funding_rate(symbol)

        # 计算日内系列数据
        intraday_data = self._calculate_intraday_series(df_3m)

        # 计算长期数据
        longer_term_data = self._calculate_longer_term_data(df_4h)

        return MarketData(
            symbol=symbol,
            current_price=current_price,
            price_change_1h=price_change_1h,
            price_change_4h=price_change_4h,
            current_ema20=current_ema20,
            current_macd=current_macd,
            current_rsi7=current_rsi7,
            open_interest=oi_data,
            funding_rate=funding_rate,
            intraday_series=intraday_data,
            longer_term_context=longer_term_data,
        )

    async def _get_klines(
        self, symbol: str, interval: str, limit: int
    ) -> List[Dict[str, float]]:
        """从 Binance 获取 K 线数据"""
        url = f"{self.base_url}/fapi/v1/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()

                klines = []
                for item in data:
                    klines.append({
                        "open_time": int(item[0]),
                        "open": float(item[1]),
                        "high": float(item[2]),
                        "low": float(item[3]),
                        "close": float(item[4]),
                        "volume": float(item[5]),
                        "close_time": int(item[6]),
                    })

                return klines

            except Exception as e:
                logger.error(f"获取K线数据失败 {symbol} {interval}: {e}")
                raise

    async def _get_open_interest_history(self, symbol: str) -> Optional[OIData]:
        """获取持仓量数据"""
        url = f"{self.base_url}/futures/data/openInterestHist"
        params = {"symbol": symbol, "period": "5m", "limit": 30}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                latest = 0
                average = 0
                if data and len(data) > 0:
                    # 提取持仓量数值
                    oi_values = [float(item.get('sumOpenInterest', 0)) for item in data]
                    # 最后一个值作为当前持仓量
                    latest = oi_values[-1]
                    # 计算平均持仓量
                    average = float(np.mean(oi_values))
                    logger.info(f"获取持仓量成功 - 当前: {symbol} {oi_values[-1]}, 平均: {average} (基于 {len(data)} 个数据点)")
                return OIData(latest=latest, average=average)
            except Exception as e:
                logger.warning(f"获取OI数据失败 {symbol}: {e}")
                return OIData(latest=0, average=0)
            

    async def _get_funding_rate(self, symbol: str) -> Decimal:
        """获取资金费率"""
        url = f"{self.base_url}/fapi/v1/premiumIndex"
        params = {"symbol": symbol}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, params=params, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                return Decimal(data.get("lastFundingRate", 0))

            except Exception as e:
                logger.warning(f"获取Funding Rate失败 {symbol}: {e}")
                return Decimal(0.0)

    def _calculate_ema(self, series: pd.Series, period: int) -> pd.Series:
        """计算 EMA - 使用 pandas_ta"""
        return ta.ema(series, length=period)

    def _calculate_macd(self, series: pd.Series) -> float:
        """计算 MACD - 使用 pandas_ta"""
        macd_result = ta.macd(series, fast=12, slow=26, signal=9)
        # macd_result 是一个 DataFrame，包含 MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
        return macd_result['MACD_12_26_9'].iloc[-1]

    def _calculate_rsi(self, series: pd.Series, period: int) -> pd.Series:
        """计算 RSI - 使用 pandas_ta"""
        return ta.rsi(series, length=period)

    def _calculate_atr(self, df: pd.DataFrame, period: int) -> float:
        """计算 ATR - 使用 pandas_ta"""
        atr_result = ta.atr(df['high'], df['low'], df['close'], length=period)
        return atr_result.iloc[-1]

    def _calculate_intraday_series(self, df: pd.DataFrame) -> IntradayData:
        """计算日内系列数据"""
        closes = df['close']

        mid_prices = closes.tolist()
        ema20_values = self._calculate_ema(closes, 20).tolist()
        rsi7_values = self._calculate_rsi(closes, 7).tolist()
        rsi14_values = self._calculate_rsi(closes, 14).tolist()

        # 使用 pandas_ta 计算 MACD 系列
        macd_result = ta.macd(closes, fast=12, slow=26, signal=9)
        macd_values = macd_result['MACD_12_26_9'].tolist()

        return IntradayData(
            mid_prices=mid_prices,
            ema20_values=ema20_values,
            macd_values=macd_values,
            rsi7_values=rsi7_values,
            rsi14_values=rsi14_values,
        )

    def _calculate_longer_term_data(self, df: pd.DataFrame) -> LongerTermData:
        """计算长期数据"""
        closes = df['close']
        volumes = df['volume']

        ema20 = self._calculate_ema(closes, 20).iloc[-1]
        ema50 = self._calculate_ema(closes, 50).iloc[-1]
        atr3 = self._calculate_atr(df, 3)
        atr14 = self._calculate_atr(df, 14)
        current_volume = volumes.iloc[-1]
        average_volume = volumes.mean()

        # 使用 pandas_ta 计算 MACD 系列
        macd_result = ta.macd(closes, fast=12, slow=26, signal=9)
        macd_values = macd_result['MACD_12_26_9'].tolist()

        # 计算 RSI14 系列
        rsi14_values = self._calculate_rsi(closes, 14).tolist()

        return LongerTermData(
            ema20=ema20,
            ema50=ema50,
            atr3=atr3,
            atr14=atr14,
            current_volume=current_volume,
            average_volume=average_volume,
            macd_values=macd_values,
            rsi14_values=rsi14_values,
        )


def format_market_data(data: MarketData) -> str:
    """
    格式化市场数据为可读字符串（对齐 Go 版本的 Format 函数）

    Args:
        data: 市场数据对象

    Returns:
        格式化后的字符串
    """
    lines = []

    # 当前价格和指标
    lines.append(
        f"current_price = {data.current_price:.2f}, "
        f"current_ema20 = {data.current_ema20:.3f}, "
        f"current_macd = {data.current_macd:.3f}, "
        f"current_rsi (7 period) = {data.current_rsi7:.3f}\n"
    )

    # 持仓量和资金费率
    lines.append(f"In addition, here is the latest {data.symbol} open interest and funding rate for perps:\n")

    if data.open_interest:
        lines.append(
            f"Open Interest: Latest: {data.open_interest.latest:.2f} "
            f"Average: {data.open_interest.average:.2f}\n"
        )

    lines.append(f"Funding Rate: {data.funding_rate:.8f}\n")

    # 日内系列数据（3分钟）
    if data.intraday_series:
        lines.append("Intraday series (3‑minute intervals, oldest → latest):\n")

        if data.intraday_series.mid_prices:
            lines.append(f"Mid prices: {_format_float_list(data.intraday_series.mid_prices)}\n")

        if data.intraday_series.ema20_values:
            lines.append(f"EMA indicators (20‑period): {_format_float_list(data.intraday_series.ema20_values)}\n")

        if data.intraday_series.macd_values:
            lines.append(f"MACD indicators: {_format_float_list(data.intraday_series.macd_values)}\n")

        if data.intraday_series.rsi7_values:
            lines.append(f"RSI indicators (7‑Period): {_format_float_list(data.intraday_series.rsi7_values)}\n")

        if data.intraday_series.rsi14_values:
            lines.append(f"RSI indicators (14‑Period): {_format_float_list(data.intraday_series.rsi14_values)}\n")

    # 长期数据（4小时）
    if data.longer_term_context:
        lines.append("Longer‑term context (4‑hour timeframe):\n")

        lines.append(
            f"20‑Period EMA: {data.longer_term_context.ema20:.3f} vs. "
            f"50‑Period EMA: {data.longer_term_context.ema50:.3f}\n"
        )

        lines.append(
            f"3‑Period ATR: {data.longer_term_context.atr3:.3f} vs. "
            f"14‑Period ATR: {data.longer_term_context.atr14:.3f}\n"
        )

        lines.append(
            f"Current Volume: {data.longer_term_context.current_volume:.3f} vs. "
            f"Average Volume: {data.longer_term_context.average_volume:.3f}\n"
        )

        if data.longer_term_context.macd_values:
            lines.append(f"MACD indicators: {_format_float_list(data.longer_term_context.macd_values)}\n")

        if data.longer_term_context.rsi14_values:
            lines.append(f"RSI indicators (14‑Period): {_format_float_list(data.longer_term_context.rsi14_values)}\n")

    return "\n".join(lines)


def _format_float_list(values: List[float]) -> str:
    """格式化浮点数列表为字符串"""
    formatted = [f"{v:.3f}" for v in values]
    return "[" + ", ".join(formatted) + "]"

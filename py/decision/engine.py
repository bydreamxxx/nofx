"""
AI 决策引擎模块

核心功能：
1. 构建 System Prompt（固定规则）
2. 构建 User Prompt（动态市场数据）
3. 调用 AI API 获取决策
4. 解析和验证决策
"""

import re
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from loguru import logger

from market import MarketDataFetcher
from market.data import format_market_data
from pool import CoinPoolManager
from mcp import Client as MCPClient


@dataclass
class PositionInfo:
    """持仓信息"""
    symbol: str
    side: str  # "long" or "short"
    entry_price: float
    mark_price: float
    quantity: float
    leverage: int
    unrealized_pnl: float
    unrealized_pnl_pct: float
    liquidation_price: float
    margin_used: float
    update_time: int  # 持仓更新时间戳（毫秒）


@dataclass
class AccountInfo:
    """账户信息"""
    total_equity: float  # 账户净值
    available_balance: float  # 可用余额
    total_pnl: float  # 总盈亏
    total_pnl_pct: float  # 总盈亏百分比
    margin_used: float  # 已用保证金
    margin_used_pct: float  # 保证金使用率
    position_count: int  # 持仓数量


@dataclass
class CandidateCoin:
    """候选币种（来自币种池）"""
    symbol: str
    sources: List[str] = field(default_factory=list)  # "ai500" 和/或 "oi_top"


@dataclass
class OITopData:
    """持仓量增长Top数据（用于AI决策参考）"""
    rank: int
    oi_delta_percent: float  # 持仓量变化百分比（1小时）
    oi_delta_value: float  # 持仓量变化价值
    price_delta_percent: float  # 价格变化百分比
    net_long: float  # 净多仓
    net_short: float  # 净空仓


@dataclass
class Context:
    """交易上下文（传递给AI的完整信息）"""
    current_time: str
    runtime_minutes: int
    call_count: int
    account: AccountInfo
    positions: List[PositionInfo]
    candidate_coins: List[CandidateCoin]
    market_data_map: Dict[str, Any] = field(default_factory=dict)
    oi_top_data_map: Dict[str, OITopData] = field(default_factory=dict)
    performance: Optional[Any] = None  # 历史表现分析
    btc_eth_leverage: int = 5
    altcoin_leverage: int = 5


@dataclass
class Decision:
    """AI的交易决策"""
    symbol: str
    action: str  # "open_long", "open_short", "close_long", "close_short", "hold", "wait"
    leverage: int = 0
    position_size_usd: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    confidence: int = 0  # 信心度 (0-100)
    risk_usd: float = 0.0  # 最大美元风险
    reasoning: str = ""


@dataclass
class FullDecision:
    """AI的完整决策（包含思维链）"""
    user_prompt: str  # 发送给AI的输入prompt
    system_prompt: str = ""  # 系统提示词（发送给AI的系统prompt）
    cot_trace: str = ""  # 思维链分析（AI输出）
    decisions: List[Decision] = field(default_factory=list)  # 具体决策列表
    timestamp: datetime = field(default_factory=datetime.now)


class DecisionEngine:
    """AI 决策引擎"""

    def __init__(
        self,
        mcp_client: MCPClient,
        market_fetcher: MarketDataFetcher,
        coin_pool_manager: Optional[CoinPoolManager] = None,
    ):
        self.mcp_client = mcp_client
        self.market_fetcher = market_fetcher
        self.coin_pool_manager = coin_pool_manager

    async def get_full_decision(
        self,
        ctx: Context,
        custom_prompt: str = "",
        override_base: bool = False,
        template_name: str = ""
    ) -> FullDecision:
        """
        获取AI的完整交易决策（批量分析所有币种和持仓）

        Args:
            ctx: 交易上下文
            custom_prompt: 自定义prompt（可选）
            override_base: 是否覆盖基础prompt
            template_name: 提示词模板名称（默认为 "default"）

        Returns:
            完整决策，包含思维链和决策列表
        """
        # 1. 为所有币种获取市场数据
        await self._fetch_market_data_for_context(ctx)

        # 2. 构建 System Prompt（固定规则）和 User Prompt（动态数据）
        system_prompt = self._build_system_prompt_with_custom(
            ctx.account.total_equity,
            ctx.btc_eth_leverage,
            ctx.altcoin_leverage,
            custom_prompt,
            override_base,
            template_name,
        )
        user_prompt = self._build_user_prompt(ctx)

        # 3. 调用AI API（使用 system + user prompt）
        ai_response = await self.mcp_client.call_with_messages(
            system_prompt, user_prompt
        )

        # 4. 解析AI响应
        decision = self._parse_full_decision_response(
            ai_response,
            ctx.account.total_equity,
            ctx.btc_eth_leverage,
            ctx.altcoin_leverage,
        )

        decision.timestamp = datetime.now()
        decision.user_prompt = user_prompt  # 保存输入prompt
        decision.system_prompt = system_prompt  # 保存系统prompt
        return decision

    async def _fetch_market_data_for_context(self, ctx: Context) -> None:
        """为上下文中的所有币种获取市场数据和OI数据"""
        ctx.market_data_map = {}
        ctx.oi_top_data_map = {}

        # 收集所有需要获取数据的币种
        symbol_set = set()

        # 1. 优先获取持仓币种的数据（这是必须的）
        for pos in ctx.positions:
            symbol_set.add(pos.symbol)

        # 2. 候选币种数量根据账户状态动态调整
        max_candidates = self._calculate_max_candidates(ctx)
        for i, coin in enumerate(ctx.candidate_coins):
            if i >= max_candidates:
                break
            symbol_set.add(coin.symbol)

        # 持仓币种集合（用于判断是否跳过OI检查）
        position_symbols = {pos.symbol for pos in ctx.positions}

        # 获取市场数据
        for symbol in symbol_set:
            try:
                data = await self.market_fetcher.get(symbol)

                # 流动性过滤：持仓价值低于15M USD的币种不做（多空都不做）
                # 但现有持仓必须保留（需要决策是否平仓）
                is_existing_position = symbol in position_symbols
                if (
                    not is_existing_position
                    and data.open_interest
                    and data.current_price > 0
                ):
                    # 计算持仓价值（USD）= 持仓量 × 当前价格
                    oi_value = data.open_interest.latest * data.current_price
                    oi_value_in_millions = oi_value / 1_000_000  # 转换为百万美元单位

                    if oi_value != 0 and oi_value_in_millions < 15:
                        logger.warning(
                            f"⚠️  {symbol} 持仓价值过低({oi_value_in_millions:.2f}M USD < 15M)，跳过此币种 "
                            f"[持仓量:{data.open_interest.latest:.0f} × 价格:{data.current_price:.4f}]"
                        )
                        continue

                ctx.market_data_map[symbol] = data

            except Exception as e:
                # 单个币种失败不影响整体，只记录错误
                logger.warning(f"获取{symbol}市场数据失败: {e}")
                continue

        # 加载OI Top数据（不影响主流程）
        if self.coin_pool_manager:
            try:
                oi_positions = await self.coin_pool_manager.get_oi_top_positions()
                for pos in oi_positions:
                    symbol = pos.symbol
                    ctx.oi_top_data_map[symbol] = OITopData(
                        rank=pos.rank,
                        oi_delta_percent=pos.oi_delta_percent,
                        oi_delta_value=pos.oi_delta_value,
                        price_delta_percent=pos.price_delta_percent,
                        net_long=pos.net_long,
                        net_short=pos.net_short,
                    )
            except Exception as e:
                logger.warning(f"获取OI Top数据失败: {e}")

    def _calculate_max_candidates(self, ctx: Context) -> int:
        """根据账户状态计算需要分析的候选币种数量"""
        # 直接返回候选池的全部币种数量
        # 因为候选池已经在 auto_trader 中筛选过了
        return len(ctx.candidate_coins)

    def _build_system_prompt_with_custom(
        self,
        account_equity: float,
        btc_eth_leverage: int,
        altcoin_leverage: int,
        custom_prompt: str,
        override_base: bool,
        template_name: str = "",
    ) -> str:
        """
        构建包含自定义内容的 System Prompt

        Args:
            account_equity: 账户权益
            btc_eth_leverage: BTC/ETH 杠杆倍数
            altcoin_leverage: 山寨币杠杆倍数
            custom_prompt: 自定义提示词
            override_base: 是否覆盖基础提示词
            template_name: 提示词模板名称

        Returns:
            完整的系统提示词
        """
        # 如果覆盖基础prompt且有自定义prompt，只使用自定义prompt
        if override_base and custom_prompt:
            return custom_prompt

        # 获取基础prompt（使用模板）
        base_prompt = self._build_system_prompt(
            account_equity, btc_eth_leverage, altcoin_leverage, template_name
        )

        # 如果没有自定义prompt，直接返回基础prompt
        if not custom_prompt:
            return base_prompt

        # 添加自定义prompt部分到基础prompt
        result = f"{base_prompt}\n\n"
        result += "# 📌 个性化交易策略\n\n"
        result += custom_prompt
        result += "\n\n"
        result += "注意: 以上个性化策略是对基础规则的补充，不能违背基础风险控制原则。\n"

        return result

    def _build_system_prompt(
        self,
        account_equity: float,
        btc_eth_leverage: int,
        altcoin_leverage: int,
        template_name: str = ""
    ) -> str:
        """
        构建 System Prompt（使用模板+动态部分）

        Args:
            account_equity: 账户权益
            btc_eth_leverage: BTC/ETH 杠杆倍数
            altcoin_leverage: 山寨币杠杆倍数
            template_name: 提示词模板名称（默认为 "default"）

        Returns:
            完整的系统提示词
        """
        parts = []

        # 1. 加载提示词模板（核心交易策略部分）
        if not template_name:
            template_name = "default"  # 默认使用 default 模板

        from decision.prompt_manager import get_prompt_template

        template = get_prompt_template(template_name)
        if not template:
            # 如果模板不存在，记录错误并使用 default
            logger.warning(f"⚠️  提示词模板 '{template_name}' 不存在，使用 default")
            template = get_prompt_template("default")
            if not template:
                # 如果连 default 都不存在，使用内置的简化版本
                logger.error("❌ 无法加载任何提示词模板，使用内置简化版本")
                parts.append("你是专业的加密货币交易AI。请根据市场数据做出交易决策。\n\n")
            else:
                parts.append(template.content)
                parts.append("\n\n")
        else:
            parts.append(template.content)
            parts.append("\n\n")

        # 2. 硬约束（风险控制）- 动态生成
        parts.append("# 硬约束（风险控制）\n\n")
        parts.append("1. 风险回报比: 必须 ≥ 1:3（冒1%风险，赚3%+收益）\n")
        parts.append("2. 最多持仓: 3个币种（质量>数量）\n")
        parts.append(
            f"3. 单币仓位: 山寨{account_equity*0.8:.0f}-{account_equity*1.5:.0f} U({altcoin_leverage}x杠杆) | "
            f"BTC/ETH {account_equity*5:.0f}-{account_equity*10:.0f} U({btc_eth_leverage}x杠杆)\n"
        )
        parts.append("4. 保证金: 总使用率 ≤ 90%\n\n")

        # 3. 输出格式 - 动态生成
        parts.append("# 输出格式\n\n")
        parts.append("**第一步: 思维链（纯文本）**\n")
        parts.append("简洁分析你的思考过程\n\n")
        parts.append("**第二步: JSON决策数组**\n\n")
        parts.append("```json\n[\n")
        parts.append(
            f'  {{"symbol": "BTCUSDT", "action": "open_short", "leverage": {btc_eth_leverage}, '
            f'"position_size_usd": {account_equity*5:.0f}, "stop_loss": 97000, "take_profit": 91000, '
            f'"confidence": 85, "risk_usd": 300, "reasoning": "下跌趋势+MACD死叉"}},\n'
        )
        parts.append('  {"symbol": "ETHUSDT", "action": "close_long", "reasoning": "止盈离场"}\n')
        parts.append("]\n```\n\n")
        parts.append("**字段说明**:\n")
        parts.append("- `action`: open_long | open_short | close_long | close_short | hold | wait\n")
        parts.append("- `confidence`: 0-100（开仓建议≥75）\n")
        parts.append(
            "- 开仓时必填: leverage, position_size_usd, stop_loss, take_profit, confidence, risk_usd, reasoning\n\n"
        )

        return "\n".join(parts)

    def _build_user_prompt(self, ctx: Context) -> str:
        """构建 User Prompt（动态数据）"""
        parts = []

        # 系统状态
        parts.append(
            f"**时间**: {ctx.current_time} | **周期**: #{ctx.call_count} | **运行**: {ctx.runtime_minutes}分钟\n"
        )

        # BTC 市场
        if "BTCUSDT" in ctx.market_data_map:
            btc_data = ctx.market_data_map["BTCUSDT"]
            parts.append(
                f"**BTC**: {btc_data.current_price:.4f} "
                f"(1h: {btc_data.price_change_1h:+.4f}%, 4h: {btc_data.price_change_4h:+.4f}%) | "
                f"MACD: {btc_data.current_macd:.4f} | RSI: {btc_data.current_rsi7:.2f}\n"
            )

        # 账户
        balance_pct = (
            (ctx.account.available_balance / ctx.account.total_equity) * 100
            if ctx.account.total_equity > 0
            else 0
        )
        parts.append(
            f"**账户**: 净值{ctx.account.total_equity:.4f} | "
            f"余额{ctx.account.available_balance:.4f} ({balance_pct:.1f}%) | "
            f"盈亏{ctx.account.total_pnl_pct:+.2f}% | "
            f"保证金{ctx.account.margin_used_pct:.1f}% | "
            f"持仓{ctx.account.position_count}个\n"
        )

        # 持仓（完整市场数据）
        if ctx.positions:
            parts.append("## 当前持仓")
            for i, pos in enumerate(ctx.positions, 1):
                # 计算持仓时长
                holding_duration = ""
                if pos.update_time > 0:
                    duration_ms = datetime.now().timestamp() * 1000 - pos.update_time
                    duration_min = int(duration_ms / (1000 * 60))  # 转换为分钟
                    if duration_min < 60:
                        holding_duration = f" | 持仓时长{duration_min}分钟"
                    else:
                        duration_hour = duration_min // 60
                        duration_min_remainder = duration_min % 60
                        holding_duration = f" | 持仓时长{duration_hour}小时{duration_min_remainder}分钟"

                parts.append(
                    f"{i}. {pos.symbol} {pos.side.upper()} | "
                    f"入场价{pos.entry_price:.4f} 当前价{pos.mark_price:.4f} | "
                    f"盈亏{pos.unrealized_pnl_pct:+.2f}% | "
                    f"杠杆{pos.leverage}x | "
                    f"保证金{pos.margin_used:.0f} | "
                    f"强平价{pos.liquidation_price:.4f}{holding_duration}\n"
                )

                # 市场数据
                if pos.symbol in ctx.market_data_map:
                    market_data = ctx.market_data_map[pos.symbol]
                    parts.append(format_market_data(market_data))
                    parts.append("")
        else:
            parts.append("**当前持仓**: 无\n")

        # 候选币种（完整市场数据）
        parts.append(f"## 候选币种 ({len(ctx.market_data_map)}个)\n")
        displayed_count = 0
        for coin in ctx.candidate_coins:
            if coin.symbol not in ctx.market_data_map:
                continue

            displayed_count += 1
            market_data = ctx.market_data_map[coin.symbol]

            source_tags = ""
            if len(coin.sources) > 1:
                source_tags = " (AI500+OI_Top双重信号)"
            elif len(coin.sources) == 1 and coin.sources[0] == "oi_top":
                source_tags = " (OI_Top持仓增长)"

            parts.append(f"### {displayed_count}. {coin.symbol}{source_tags}\n")
            parts.append(format_market_data(market_data))
            parts.append("")

        # 夏普比率
        if ctx.performance:
            try:
                perf_dict = (
                    ctx.performance if isinstance(ctx.performance, dict) else {}
                )
                sharpe_ratio = perf_dict.get("sharpe_ratio", 0.0)
                parts.append(f"## 📊 夏普比率: {sharpe_ratio:.2f}\n")
            except Exception:
                pass

        parts.append("---\n")
        parts.append("现在请分析并输出决策（思维链 + JSON）")

        return "\n".join(parts)

    def _parse_full_decision_response(
        self,
        ai_response: str,
        account_equity: float,
        btc_eth_leverage: int,
        altcoin_leverage: int,
    ) -> FullDecision:
        """解析AI的完整决策响应"""
        # 1. 提取思维链
        cot_trace = self._extract_cot_trace(ai_response)

        # 2. 提取JSON决策列表
        try:
            decisions = self._extract_decisions(ai_response)
        except Exception as e:
            logger.error(f"提取决策失败: {e}\n\n=== AI思维链分析 ===\n{cot_trace}")
            return FullDecision(user_prompt="", cot_trace=cot_trace, decisions=[])

        # 3. 验证决策
        try:
            self._validate_decisions(
                decisions, account_equity, btc_eth_leverage, altcoin_leverage
            )
        except Exception as e:
            logger.error(f"决策验证失败: {e}\n\n=== AI思维链分析 ===\n{cot_trace}")

        return FullDecision(user_prompt="", cot_trace=cot_trace, decisions=decisions)

    def _extract_cot_trace(self, response: str) -> str:
        """提取思维链分析"""
        # 查找JSON数组的开始位置
        json_start = response.find("[")

        if json_start > 0:
            # 思维链是JSON数组之前的内容
            return response[:json_start].strip()

        # 如果找不到JSON，整个响应都是思维链
        return response.strip()

    def _extract_decisions(self, response: str) -> List[Decision]:
        """提取JSON决策列表"""
        # 直接查找JSON数组 - 找第一个完整的JSON数组
        array_start = response.find("[")
        if array_start == -1:
            raise ValueError("无法找到JSON数组起始")

        # 从 [ 开始，匹配括号找到对应的 ]
        array_end = self._find_matching_bracket(response, array_start)
        if array_end == -1:
            raise ValueError("无法找到JSON数组结束")

        json_content = response[array_start : array_end + 1].strip()

        # 修复常见的JSON格式错误：中文引号
        json_content = self._fix_missing_quotes(json_content)

        # 解析JSON
        try:
            decisions_data = json.loads(json_content)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON解析失败: {e}\nJSON内容: {json_content}")

        # 转换为Decision对象
        decisions = []
        for item in decisions_data:
            decision = Decision(
                symbol=item.get("symbol", ""),
                action=item.get("action", ""),
                leverage=item.get("leverage", 0),
                position_size_usd=item.get("position_size_usd", 0.0),
                stop_loss=item.get("stop_loss", 0.0),
                take_profit=item.get("take_profit", 0.0),
                confidence=item.get("confidence", 0),
                risk_usd=item.get("risk_usd", 0.0),
                reasoning=item.get("reasoning", ""),
            )
            decisions.append(decision)

        return decisions

    def _find_matching_bracket(self, s: str, start: int) -> int:
        """查找匹配的右括号"""
        if start >= len(s) or s[start] != "[":
            return -1

        depth = 0
        for i in range(start, len(s)):
            if s[i] == "[":
                depth += 1
            elif s[i] == "]":
                depth -= 1
                if depth == 0:
                    return i

        return -1

    def _fix_missing_quotes(self, json_str: str) -> str:
        """替换中文引号为英文引号（避免输入法自动转换）"""
        json_str = json_str.replace("\u201c", '"')  # "
        json_str = json_str.replace("\u201d", '"')  # "
        json_str = json_str.replace("\u2018", "'")  # '
        json_str = json_str.replace("\u2019", "'")  # '
        return json_str

    def _validate_decisions(
        self,
        decisions: List[Decision],
        account_equity: float,
        btc_eth_leverage: int,
        altcoin_leverage: int,
    ) -> None:
        """验证所有决策（需要账户信息和杠杆配置）"""
        for i, decision in enumerate(decisions, 1):
            try:
                self._validate_decision(
                    decision, account_equity, btc_eth_leverage, altcoin_leverage
                )
            except Exception as e:
                raise ValueError(f"决策 #{i} 验证失败: {e}")

    def _validate_decision(
        self,
        d: Decision,
        account_equity: float,
        btc_eth_leverage: int,
        altcoin_leverage: int,
    ) -> None:
        """验证单个决策的有效性"""
        # 验证action
        valid_actions = {
            "open_long",
            "open_short",
            "close_long",
            "close_short",
            "hold",
            "wait",
        }

        if d.action not in valid_actions:
            raise ValueError(f"无效的action: {d.action}")

        # 开仓操作必须提供完整参数
        if d.action in ["open_long", "open_short"]:
            # 根据币种使用配置的杠杆上限
            max_leverage = altcoin_leverage  # 山寨币使用配置的杠杆
            max_position_value = account_equity * 1.5  # 山寨币最多1.5倍账户净值
            if d.symbol in ["BTCUSDT", "ETHUSDT"]:
                max_leverage = btc_eth_leverage  # BTC和ETH使用配置的杠杆
                max_position_value = account_equity * 10  # BTC/ETH最多10倍账户净值

            if d.leverage <= 0 or d.leverage > max_leverage:
                raise ValueError(
                    f"杠杆必须在1-{max_leverage}之间（{d.symbol}，当前配置上限{max_leverage}倍）: {d.leverage}"
                )

            if d.position_size_usd <= 0:
                raise ValueError(f"仓位大小必须大于0: {d.position_size_usd:.2f}")

            # 验证仓位价值上限（加1%容差以避免浮点数精度问题）
            tolerance = max_position_value * 0.01  # 1%容差
            if d.position_size_usd > max_position_value + tolerance:
                if d.symbol in ["BTCUSDT", "ETHUSDT"]:
                    raise ValueError(
                        f"BTC/ETH单币种仓位价值不能超过{max_position_value:.0f} USDT（10倍账户净值），"
                        f"实际: {d.position_size_usd:.0f}"
                    )
                else:
                    raise ValueError(
                        f"山寨币单币种仓位价值不能超过{max_position_value:.0f} USDT（1.5倍账户净值），"
                        f"实际: {d.position_size_usd:.0f}"
                    )

            if d.stop_loss <= 0 or d.take_profit <= 0:
                raise ValueError("止损和止盈必须大于0")

            # 验证止损止盈的合理性
            if d.action == "open_long":
                if d.stop_loss >= d.take_profit:
                    raise ValueError("做多时止损价必须小于止盈价")
            else:
                if d.stop_loss <= d.take_profit:
                    raise ValueError("做空时止损价必须大于止盈价")

            # 验证风险回报比（必须≥1:3）
            entry_price = 0.0
            if d.action == "open_long":
                # 做多：入场价在止损和止盈之间
                entry_price = d.stop_loss + (d.take_profit - d.stop_loss) * 0.2
            else:
                # 做空：入场价在止损和止盈之间
                entry_price = d.stop_loss - (d.stop_loss - d.take_profit) * 0.2

            risk_percent = 0.0
            reward_percent = 0.0
            risk_reward_ratio = 0.0

            if d.action == "open_long":
                risk_percent = (entry_price - d.stop_loss) / entry_price * 100
                reward_percent = (d.take_profit - entry_price) / entry_price * 100
                if risk_percent > 0:
                    risk_reward_ratio = reward_percent / risk_percent
            else:
                risk_percent = (d.stop_loss - entry_price) / entry_price * 100
                reward_percent = (entry_price - d.take_profit) / entry_price * 100
                if risk_percent > 0:
                    risk_reward_ratio = reward_percent / risk_percent

            # 硬约束：风险回报比必须≥3.0
            if risk_reward_ratio < 3.0:
                raise ValueError(
                    f"风险回报比过低({risk_reward_ratio:.2f}:1)，必须≥3.0:1 "
                    f"[风险:{risk_percent:.2f}% 收益:{reward_percent:.2f}%] "
                    f"[止损:{d.stop_loss:.4f} 止盈:{d.take_profit:.4f}]"
                )

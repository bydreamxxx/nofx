"""
自动交易控制器

核心功能：
1. 定期扫描市场（每3分钟）
2. 构建交易上下文（账户、持仓、候选币种）
3. 调用AI获取决策
4. 执行决策（开仓、平仓）
5. 记录决策日志
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from loguru import logger

from trader.interface import Trader
from trader.binance_futures import BinanceFuturesTrader
from mcp import Client as MCPClient
from decision import (
    DecisionEngine,
    Context,
    AccountInfo,
    PositionInfo,
    CandidateCoin,
    Decision,
)
from logger import DecisionLogger
from market import MarketDataFetcher
from pool import CoinPoolManager


@dataclass
class AutoTraderConfig:
    """自动交易配置（简化版 - AI全权决策）"""

    # Trader标识
    id: str
    name: str
    ai_model: str  # AI模型: "qwen" 或 "deepseek" 或 "custom"

    # 交易平台选择
    exchange: str = "binance"  # "binance", "hyperliquid", "aster", "okx"

    # 测试网模式
    testnet: bool = False

    # 币安API配置
    binance_api_key: str = ""
    binance_secret_key: str = ""

    # Hyperliquid 配置
    hyperliquid_private_key: str = ""
    hyperliquid_wallet_address: str = ""

    # Aster DEX 配置
    aster_private_key: str = ""
    aster_wallet_address: str = ""

    # OKX 配置
    okx_api_key: str = ""
    okx_api_secret: str = ""
    okx_passphrase: str = ""

    # AI配置
    deepseek_key: str = ""
    qwen_key: str = ""

    # 自定义AI API配置
    custom_api_url: str = ""
    custom_api_key: str = ""
    custom_model_name: str = ""

    # 币种池配置
    use_default_coins: bool = False
    coin_pool_api_url: str = ""
    oi_top_api_url: str = ""

    # 扫描配置
    scan_interval_minutes: int = 3  # 扫描间隔（建议3分钟）

    # 账户配置
    initial_balance: float = 0.0  # 初始金额（用于计算盈亏，需手动设置）

    # 杠杆配置
    btc_eth_leverage: int = 5  # BTC和ETH的杠杆倍数
    altcoin_leverage: int = 5  # 山寨币的杠杆倍数

    # 风险控制（仅作为提示，AI可自主决定）
    max_daily_loss: float = 10.0  # 最大日亏损百分比（提示）
    max_drawdown: float = 20.0  # 最大回撤百分比（提示）
    stop_trading_hours: float = 1.0  # 触发风控后暂停时长（小时）

    # 仓位模式
    is_cross_margin: bool = True  # true=全仓模式, false=逐仓模式


class AutoTrader:
    """自动交易器"""

    def __init__(self, config: AutoTraderConfig):
        self.id = config.id
        self.name = config.name
        self.ai_model = config.ai_model
        self.exchange = config.exchange
        self.config = config

        # 初始化组件
        self.trader: Optional[Trader] = None
        self.mcp_client: Optional[MCPClient] = None
        self.decision_engine: Optional[DecisionEngine] = None
        self.decision_logger: Optional[DecisionLogger] = None
        self.market_fetcher: MarketDataFetcher = MarketDataFetcher()
        self.coin_pool_manager: Optional[CoinPoolManager] = None

        # 状态
        self.initial_balance = config.initial_balance
        self.daily_pnl = 0.0
        self.last_reset_time = datetime.now()
        self.stop_until = datetime.now()
        self.is_running = False
        self.start_time = datetime.now()
        self.call_count = 0
        self.position_first_seen_time: Dict[str, int] = {}  # symbol_side -> timestamp毫秒

        # 自定义prompt
        self.custom_prompt = ""
        self.override_base_prompt = False

    async def initialize(self) -> None:
        """初始化所有组件"""
        # 验证初始金额
        if self.config.initial_balance <= 0:
            raise ValueError("初始金额必须大于0，请在配置中设置initial_balance")

        # 1. 初始化交易器
        if self.exchange == "binance":
            logger.info(f"🏦 [{self.name}] 使用币安合约交易")
            from trader.binance_futures import BinanceFuturesTrader
            self.trader = BinanceFuturesTrader(
                api_key=self.config.binance_api_key,
                secret_key=self.config.binance_secret_key,
            )
        elif self.exchange == "hyperliquid":
            logger.info(f"🏦 [{self.name}] 使用 Hyperliquid DEX")
            from trader.hyperliquid_trader import HyperliquidTrader
            self.trader = HyperliquidTrader(
                private_key=self.config.hyperliquid_private_key,
                wallet_address=self.config.hyperliquid_wallet_address,
                testnet=self.config.testnet,
            )
        elif self.exchange == "aster":
            logger.info(f"🏦 [{self.name}] 使用 Aster DEX")
            from trader.aster_trader import AsterTrader
            self.trader = AsterTrader(
                private_key=self.config.aster_private_key,
                wallet_address=self.config.aster_wallet_address,
                testnet=self.config.testnet,
            )
        elif self.exchange == "okx":
            logger.info(f"🏦 [{self.name}] 使用 OKX 交易所")
            from trader.okx_trader import OKXTrader
            self.trader = OKXTrader(
                api_key=self.config.okx_api_key,
                api_secret=self.config.okx_api_secret,
                passphrase=self.config.okx_passphrase,
                testnet=self.config.testnet,
            )
        else:
            raise ValueError(f"不支持的交易平台: {self.exchange}")

        # 2. 初始化AI客户端
        self.mcp_client = MCPClient()

        if self.ai_model == "custom":
            self.mcp_client.set_custom_api(
                base_url=self.config.custom_api_url,
                api_key=self.config.custom_api_key,
                model=self.config.custom_model_name,
            )
            logger.info(
                f"🤖 [{self.name}] 使用自定义AI API: {self.config.custom_api_url} (模型: {self.config.custom_model_name})"
            )
        elif self.ai_model == "qwen":
            self.mcp_client.set_qwen_api_key(self.config.qwen_key, "")
            logger.info(f"🤖 [{self.name}] 使用阿里云Qwen AI")
        else:
            self.mcp_client.set_deepseek_api_key(self.config.deepseek_key)
            logger.info(f"🤖 [{self.name}] 使用DeepSeek AI")

        # 3. 初始化币种池管理器
        self.coin_pool_manager = CoinPoolManager(
            use_default_coins=self.config.use_default_coins,
            coin_pool_api_url=self.config.coin_pool_api_url,
            oi_top_api_url=self.config.oi_top_api_url,
        )

        # 4. 初始化决策引擎
        self.decision_engine = DecisionEngine(
            mcp_client=self.mcp_client,
            market_fetcher=self.market_fetcher,
            coin_pool_manager=self.coin_pool_manager,
        )

        # 5. 初始化决策日志记录器
        log_dir = f"decision_logs/{self.id}"
        self.decision_logger = DecisionLogger(log_dir=log_dir)

        logger.info(f"✅ [{self.name}] 自动交易器初始化完成")

    async def run(self) -> None:
        """运行自动交易主循环"""
        self.is_running = True
        self.start_time = datetime.now()

        logger.info("🚀 AI驱动自动交易系统启动")
        logger.info(f"💰 初始余额: {self.initial_balance:.2f} USDT")
        logger.info(f"⚙️  扫描间隔: {self.config.scan_interval_minutes} 分钟")
        logger.info("🤖 AI将全权决定杠杆、仓位大小、止损止盈等参数")

        # 首次立即执行
        try:
            await self.run_cycle()
        except Exception as e:
            logger.error(f"❌ 执行失败: {e}")

        # 定期执行
        while self.is_running:
            try:
                await asyncio.sleep(self.config.scan_interval_minutes * 60)
                await self.run_cycle()
            except Exception as e:
                logger.error(f"❌ 执行失败: {e}")

    def stop(self) -> None:
        """停止自动交易"""
        self.is_running = False
        logger.info("⏹ 自动交易系统停止")

    async def run_cycle(self) -> None:
        """运行一个交易周期（使用AI全权决策）"""
        self.call_count += 1

        logger.info("\n" + "=" * 70)
        logger.info(
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - AI决策周期 #{self.call_count}"
        )
        logger.info("=" * 70)

        # 创建决策记录
        record_data: Dict[str, Any] = {
            "execution_log": [],
            "success": True,
            "decisions": [],
            "candidate_coins": [],
            "positions": [],
        }

        try:
            # 1. 检查是否需要停止交易
            if datetime.now() < self.stop_until:
                remaining = (self.stop_until - datetime.now()).total_seconds() / 60
                logger.warning(f"⏸ 风险控制：暂停交易中，剩余 {remaining:.0f} 分钟")
                record_data["success"] = False
                record_data["error_message"] = f"风险控制暂停中，剩余 {remaining:.0f} 分钟"
                await self.decision_logger.log_decision(record_data)
                return

            # 2. 重置日盈亏（每天重置）
            if datetime.now() - self.last_reset_time > timedelta(hours=24):
                self.daily_pnl = 0
                self.last_reset_time = datetime.now()
                logger.info("📅 日盈亏已重置")

            # 3. 构建交易上下文
            ctx = await self.build_trading_context()

            # 保存账户状态快照
            record_data["account_state"] = {
                "total_balance": ctx.account.total_equity,
                "available_balance": ctx.account.available_balance,
                "total_unrealized_profit": ctx.account.total_pnl,
                "position_count": ctx.account.position_count,
                "margin_used_pct": ctx.account.margin_used_pct,
            }

            # 保存持仓快照
            for pos in ctx.positions:
                record_data["positions"].append(
                    {
                        "symbol": pos.symbol,
                        "side": pos.side,
                        "position_amt": pos.quantity,
                        "entry_price": pos.entry_price,
                        "mark_price": pos.mark_price,
                        "unrealized_profit": pos.unrealized_pnl,
                        "leverage": pos.leverage,
                        "liquidation_price": pos.liquidation_price,
                    }
                )

            # 保存候选币种列表
            record_data["candidate_coins"] = [coin.symbol for coin in ctx.candidate_coins]

            logger.info(
                f"📊 账户净值: {ctx.account.total_equity:.2f} USDT | "
                f"可用: {ctx.account.available_balance:.2f} USDT | "
                f"持仓: {ctx.account.position_count}"
            )

            # 4. 调用AI获取完整决策
            logger.info("🤖 正在请求AI分析并决策...")
            decision = await self.decision_engine.get_full_decision(
                ctx, self.custom_prompt, self.override_base_prompt
            )

            # 保存prompt和思维链
            record_data["input_prompt"] = decision.user_prompt
            record_data["cot_trace"] = decision.cot_trace
            if decision.decisions:
                import json

                record_data["decision_json"] = json.dumps(
                    [
                        {
                            "symbol": d.symbol,
                            "action": d.action,
                            "leverage": d.leverage,
                            "position_size_usd": d.position_size_usd,
                            "stop_loss": d.stop_loss,
                            "take_profit": d.take_profit,
                            "confidence": d.confidence,
                            "reasoning": d.reasoning,
                        }
                        for d in decision.decisions
                    ],
                    indent=2,
                )

            # 5. 打印AI思维链
            logger.info("\n" + "-" * 70)
            logger.info("💭 AI思维链分析:")
            logger.info("-" * 70)
            logger.info(decision.cot_trace)
            logger.info("-" * 70 + "\n")

            # 6. 打印AI决策
            logger.info(f"📋 AI决策列表 ({len(decision.decisions)} 个):")
            for i, d in enumerate(decision.decisions, 1):
                logger.info(f"  [{i}] {d.symbol}: {d.action} - {d.reasoning}")
                if d.action in ["open_long", "open_short"]:
                    logger.info(
                        f"      杠杆: {d.leverage}x | 仓位: {d.position_size_usd:.2f} USDT | "
                        f"止损: {d.stop_loss:.4f} | 止盈: {d.take_profit:.4f}"
                    )

            # 7. 对决策排序：确保先平仓后开仓（防止仓位叠加超限）
            sorted_decisions = self._sort_decisions_by_priority(decision.decisions)

            logger.info("🔄 执行顺序（已优化）: 先平仓→后开仓")
            for i, d in enumerate(sorted_decisions, 1):
                logger.info(f"  [{i}] {d.symbol} {d.action}")

            # 8. 执行决策并记录结果
            for d in sorted_decisions:
                action_record = {
                    "action": d.action,
                    "symbol": d.symbol,
                    "quantity": 0.0,
                    "leverage": d.leverage,
                    "price": 0.0,
                    "timestamp": datetime.now().isoformat(),
                    "success": False,
                    "error": "",
                }

                try:
                    await self._execute_decision_with_record(d, action_record)
                    action_record["success"] = True
                    record_data["execution_log"].append(f"✓ {d.symbol} {d.action} 成功")
                    # 成功执行后短暂延迟
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"❌ 执行决策失败 ({d.symbol} {d.action}): {e}")
                    action_record["error"] = str(e)
                    record_data["execution_log"].append(
                        f"❌ {d.symbol} {d.action} 失败: {e}"
                    )

                record_data["decisions"].append(action_record)

        except Exception as e:
            logger.error(f"❌ 周期执行异常: {e}")
            record_data["success"] = False
            record_data["error_message"] = str(e)

        # 9. 保存决策记录
        try:
            await self.decision_logger.log_decision(record_data)
        except Exception as e:
            logger.warning(f"⚠ 保存决策记录失败: {e}")

    async def build_trading_context(self) -> Context:
        """构建交易上下文"""
        # 1. 获取账户信息
        balance = await self.trader.get_balance()

        # 获取账户字段
        total_wallet_balance = balance.get("totalWalletBalance", 0.0)
        total_unrealized_profit = balance.get("totalUnrealizedProfit", 0.0)
        available_balance = balance.get("availableBalance", 0.0)

        # Total Equity = 钱包余额 + 未实现盈亏
        total_equity = total_wallet_balance + total_unrealized_profit

        # 2. 获取持仓信息
        positions = await self.trader.get_positions()

        position_infos: List[PositionInfo] = []
        total_margin_used = 0.0

        # 当前持仓的key集合（用于清理已平仓的记录）
        current_position_keys = set()

        for pos in positions:
            symbol = pos["symbol"]
            side = pos["side"]
            entry_price = pos["entryPrice"]
            mark_price = pos["markPrice"]
            quantity = abs(pos["positionAmt"])  # 空仓数量为负，转为正数
            unrealized_pnl = pos["unRealizedProfit"]
            liquidation_price = pos["liquidationPrice"]

            # 计算盈亏百分比
            if side == "long":
                pnl_pct = ((mark_price - entry_price) / entry_price) * 100
            else:
                pnl_pct = ((entry_price - mark_price) / entry_price) * 100

            # 计算占用保证金（估算）
            leverage = int(pos.get("leverage", 10))
            margin_used = (quantity * mark_price) / leverage
            total_margin_used += margin_used

            # 跟踪持仓首次出现时间
            pos_key = f"{symbol}_{side}"
            current_position_keys.add(pos_key)
            if pos_key not in self.position_first_seen_time:
                # 新持仓，记录当前时间
                self.position_first_seen_time[pos_key] = int(
                    datetime.now().timestamp() * 1000
                )
            update_time = self.position_first_seen_time[pos_key]

            position_infos.append(
                PositionInfo(
                    symbol=symbol,
                    side=side,
                    entry_price=entry_price,
                    mark_price=mark_price,
                    quantity=quantity,
                    leverage=leverage,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_pct=pnl_pct,
                    liquidation_price=liquidation_price,
                    margin_used=margin_used,
                    update_time=update_time,
                )
            )

        # 清理已平仓的持仓记录
        keys_to_remove = [
            k for k in self.position_first_seen_time if k not in current_position_keys
        ]
        for k in keys_to_remove:
            del self.position_first_seen_time[k]

        # 3. 获取合并的候选币种池（AI500 + OI Top，去重）
        ai500_limit = 20  # AI500取前20个评分最高的币种

        # 获取合并后的币种池（AI500 + OI Top）
        merged_pool = await self.coin_pool_manager.get_merged_coin_pool(ai500_limit)

        # 构建候选币种列表（包含来源信息）
        candidate_coins: List[CandidateCoin] = []
        for symbol in merged_pool.all_symbols:
            sources = merged_pool.symbol_sources.get(symbol, [])
            candidate_coins.append(CandidateCoin(symbol=symbol, sources=sources))

        logger.info(
            f"📋 合并币种池: AI500前{ai500_limit} + OI_Top20 = 总计{len(candidate_coins)}个候选币种"
        )

        # 4. 计算总盈亏
        total_pnl = total_equity - self.initial_balance
        total_pnl_pct = (
            (total_pnl / self.initial_balance) * 100 if self.initial_balance > 0 else 0
        )

        margin_used_pct = (
            (total_margin_used / total_equity) * 100 if total_equity > 0 else 0
        )

        # 5. 分析历史表现（最近100个周期）
        try:
            performance = await self.decision_logger.get_performance_analysis(100)
        except Exception as e:
            logger.warning(f"⚠️  分析历史表现失败: {e}")
            performance = None

        # 6. 构建上下文
        ctx = Context(
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            runtime_minutes=int((datetime.now() - self.start_time).total_seconds() / 60),
            call_count=self.call_count,
            btc_eth_leverage=self.config.btc_eth_leverage,
            altcoin_leverage=self.config.altcoin_leverage,
            account=AccountInfo(
                total_equity=total_equity,
                available_balance=available_balance,
                total_pnl=total_pnl,
                total_pnl_pct=total_pnl_pct,
                margin_used=total_margin_used,
                margin_used_pct=margin_used_pct,
                position_count=len(position_infos),
            ),
            positions=position_infos,
            candidate_coins=candidate_coins,
            performance=performance,
        )

        return ctx

    async def _execute_decision_with_record(
        self, decision: Decision, action_record: Dict[str, Any]
    ) -> None:
        """执行AI决策并记录详细信息"""
        if decision.action == "open_long":
            await self._execute_open_long(decision, action_record)
        elif decision.action == "open_short":
            await self._execute_open_short(decision, action_record)
        elif decision.action == "close_long":
            await self._execute_close_long(decision, action_record)
        elif decision.action == "close_short":
            await self._execute_close_short(decision, action_record)
        elif decision.action in ["hold", "wait"]:
            # 无需执行，仅记录
            pass
        else:
            raise ValueError(f"未知的action: {decision.action}")

    async def _execute_open_long(
        self, decision: Decision, action_record: Dict[str, Any]
    ) -> None:
        """执行开多仓并记录详细信息"""
        logger.info(f"  📈 开多仓: {decision.symbol}")

        # 检查是否已有同币种同方向持仓
        positions = await self.trader.get_positions()
        for pos in positions:
            if pos["symbol"] == decision.symbol and pos["side"] == "long":
                raise ValueError(
                    f"❌ {decision.symbol} 已有多仓，拒绝开仓以防止仓位叠加超限。如需换仓，请先给出 close_long 决策"
                )

        # 获取当前价格
        market_data = await self.market_fetcher.get(decision.symbol)

        # 计算数量
        quantity = decision.position_size_usd / market_data.current_price
        action_record["quantity"] = quantity
        action_record["price"] = market_data.current_price

        # 执行开仓
        result = await self.trader.open_long(
            symbol=decision.symbol, quantity=quantity, leverage=decision.leverage
        )

        logger.info(
            f"  ✅ 开多仓成功: {decision.symbol} | "
            f"数量: {quantity:.4f} | "
            f"杠杆: {decision.leverage}x"
        )

        # 设置止损止盈
        if decision.stop_loss > 0 and decision.take_profit > 0:
            await self.trader.set_stop_loss_take_profit(
                symbol=decision.symbol,
                side="long",
                stop_loss=decision.stop_loss,
                take_profit=decision.take_profit,
            )
            logger.info(
                f"  ✅ 止损止盈已设置: 止损={decision.stop_loss:.4f} | 止盈={decision.take_profit:.4f}"
            )

    async def _execute_open_short(
        self, decision: Decision, action_record: Dict[str, Any]
    ) -> None:
        """执行开空仓并记录详细信息"""
        logger.info(f"  📉 开空仓: {decision.symbol}")

        # 检查是否已有同币种同方向持仓
        positions = await self.trader.get_positions()
        for pos in positions:
            if pos["symbol"] == decision.symbol and pos["side"] == "short":
                raise ValueError(
                    f"❌ {decision.symbol} 已有空仓，拒绝开仓以防止仓位叠加超限。如需换仓，请先给出 close_short 决策"
                )

        # 获取当前价格
        market_data = await self.market_fetcher.get(decision.symbol)

        # 计算数量
        quantity = decision.position_size_usd / market_data.current_price
        action_record["quantity"] = quantity
        action_record["price"] = market_data.current_price

        # 执行开仓
        result = await self.trader.open_short(
            symbol=decision.symbol, quantity=quantity, leverage=decision.leverage
        )

        logger.info(
            f"  ✅ 开空仓成功: {decision.symbol} | "
            f"数量: {quantity:.4f} | "
            f"杠杆: {decision.leverage}x"
        )

        # 设置止损止盈
        if decision.stop_loss > 0 and decision.take_profit > 0:
            await self.trader.set_stop_loss_take_profit(
                symbol=decision.symbol,
                side="short",
                stop_loss=decision.stop_loss,
                take_profit=decision.take_profit,
            )
            logger.info(
                f"  ✅ 止损止盈已设置: 止损={decision.stop_loss:.4f} | 止盈={decision.take_profit:.4f}"
            )

    async def _execute_close_long(
        self, decision: Decision, action_record: Dict[str, Any]
    ) -> None:
        """执行平多仓并记录详细信息"""
        logger.info(f"  🔻 平多仓: {decision.symbol}")

        # 获取持仓信息
        positions = await self.trader.get_positions()
        pos_quantity = 0.0
        for pos in positions:
            if pos["symbol"] == decision.symbol and pos["side"] == "long":
                pos_quantity = abs(pos["positionAmt"])
                action_record["quantity"] = pos_quantity
                action_record["price"] = pos["markPrice"]
                break

        if pos_quantity == 0:
            raise ValueError(f"❌ {decision.symbol} 无多仓可平")

        # 执行平仓
        result = await self.trader.close_long(
            symbol=decision.symbol, quantity=pos_quantity
        )

        logger.info(f"  ✅ 平多仓成功: {decision.symbol} | 数量: {pos_quantity:.4f}")

    async def _execute_close_short(
        self, decision: Decision, action_record: Dict[str, Any]
    ) -> None:
        """执行平空仓并记录详细信息"""
        logger.info(f"  🔺 平空仓: {decision.symbol}")

        # 获取持仓信息
        positions = await self.trader.get_positions()
        pos_quantity = 0.0
        for pos in positions:
            if pos["symbol"] == decision.symbol and pos["side"] == "short":
                pos_quantity = abs(pos["positionAmt"])
                action_record["quantity"] = pos_quantity
                action_record["price"] = pos["markPrice"]
                break

        if pos_quantity == 0:
            raise ValueError(f"❌ {decision.symbol} 无空仓可平")

        # 执行平仓
        result = await self.trader.close_short(
            symbol=decision.symbol, quantity=pos_quantity
        )

        logger.info(f"  ✅ 平空仓成功: {decision.symbol} | 数量: {pos_quantity:.4f}")

    def _sort_decisions_by_priority(self, decisions: List[Decision]) -> List[Decision]:
        """对决策排序：先平仓后开仓"""
        close_actions = [
            d for d in decisions if d.action in ["close_long", "close_short"]
        ]
        open_actions = [
            d for d in decisions if d.action in ["open_long", "open_short"]
        ]
        other_actions = [
            d
            for d in decisions
            if d.action not in ["close_long", "close_short", "open_long", "open_short"]
        ]

        return close_actions + open_actions + other_actions

    def set_custom_prompt(self, prompt: str, override_base: bool = False) -> None:
        """设置自定义交易策略prompt"""
        self.custom_prompt = prompt
        self.override_base_prompt = override_base
        logger.info(f"📝 [{self.name}] 自定义prompt已设置（覆盖基础={override_base}）")

    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            "id": self.id,
            "name": self.name,
            "ai_model": self.ai_model,
            "exchange": self.exchange,
            "is_running": self.is_running,
            "call_count": self.call_count,
            "runtime_minutes": int(
                (datetime.now() - self.start_time).total_seconds() / 60
            ),
            "initial_balance": self.initial_balance,
        }

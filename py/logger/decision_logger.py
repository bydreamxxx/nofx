"""
决策日志记录器
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from loguru import logger


@dataclass
class AccountSnapshot:
    """账户状态快照"""
    total_balance: float
    available_balance: float
    total_unrealized_profit: float
    position_count: int
    margin_used_pct: float


@dataclass
class PositionSnapshot:
    """持仓快照"""
    symbol: str
    side: str
    position_amt: float
    entry_price: float
    mark_price: float
    unrealized_profit: float
    leverage: float
    liquidation_price: float


@dataclass
class DecisionAction:
    """决策动作"""
    action: str  # open_long, open_short, close_long, close_short
    symbol: str
    quantity: float
    leverage: int
    price: float
    order_id: int
    timestamp: str
    success: bool
    error: str = ""


@dataclass
class DecisionRecord:
    """决策记录"""
    timestamp: str
    cycle_number: int
    input_prompt: str
    cot_trace: str
    decision_json: str
    account_state: Dict[str, Any]
    positions: List[Dict[str, Any]]
    candidate_coins: List[str]
    decisions: List[Dict[str, Any]]
    execution_log: List[str]
    success: bool
    error_message: str = ""


class DecisionLogger:
    """决策日志记录器"""

    def __init__(self, log_dir: str = "decision_logs"):
        self.log_dir = log_dir
        self.cycle_number = 0

        # 确保日志目录存在
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)

    async def log_decision(self, record_data: Dict[str, Any]) -> None:
        """记录决策"""
        self.cycle_number += 1

        # 构建决策记录
        record = {
            "timestamp": datetime.now().isoformat(),
            "cycle_number": self.cycle_number,
            **record_data
        }

        # 生成文件名
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"decision_{timestamp_str}_cycle{self.cycle_number}.json"
        filepath = os.path.join(self.log_dir, filename)

        # 写入文件
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(record, f, indent=2, ensure_ascii=False)

            logger.info(f"📝 决策记录已保存: {filename}")

        except Exception as e:
            logger.error(f"❌ 写入决策记录失败: {e}")

    async def get_latest_records(self, n: int = 20) -> List[Dict[str, Any]]:
        """获取最近N条记录（按时间正序：从旧到新）"""
        try:
            # 获取所有 JSON 文件
            files = sorted(
                Path(self.log_dir).glob("decision_*.json"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )

            records = []
            for file_path in files[:n]:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        record = json.load(f)
                        records.append(record)
                except Exception as e:
                    logger.warning(f"读取记录失败 {file_path}: {e}")
                    continue

            # 反转数组，让时间从旧到新排列
            records.reverse()

            return records

        except Exception as e:
            logger.error(f"获取历史记录失败: {e}")
            return []

    async def analyze_performance(self, lookback_cycles: int = 100) -> Dict[str, Any]:
        """
        分析最近N个周期的交易表现（完整实现，参考Go版本）

        Args:
            lookback_cycles: 分析窗口大小（默认100个周期，约5小时）

        Returns:
            完整的性能分析数据，包括：
            - 总交易数、胜率、盈亏比
            - 夏普比率
            - 各币种表现
            - 最近交易记录
        """
        # 1. 获取分析窗口内的记录
        records = await self.get_latest_records(lookback_cycles)

        if not records:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "sharpe_ratio": 0.0,
                "recent_trades": [],
                "symbol_stats": {},
                "best_symbol": "",
                "worst_symbol": "",
            }

        # 2. 扩大窗口预填充开仓记录（解决长期持仓匹配问题）
        all_records = await self.get_latest_records(lookback_cycles * 3)

        # 3. 追踪持仓状态：symbol_side -> {side, openPrice, openTime, quantity, leverage}
        open_positions: Dict[str, Dict[str, Any]] = {}

        # 预填充：从扩大窗口收集所有开仓记录
        if all_records and len(all_records) > len(records):
            for record in all_records:
                for action in record.get("decisions", []):
                    if not action.get("success"):
                        continue

                    symbol = action.get("symbol")
                    act = action.get("action")

                    # 确定方向
                    side = ""
                    if act in ["open_long", "close_long"]:
                        side = "long"
                    elif act in ["open_short", "close_short"]:
                        side = "short"

                    if not side:
                        continue

                    pos_key = f"{symbol}_{side}"

                    if act in ["open_long", "open_short"]:
                        # 记录开仓
                        open_positions[pos_key] = {
                            "side": side,
                            "open_price": action.get("price", 0.0),
                            "open_time": action.get("timestamp", ""),
                            "quantity": action.get("quantity", 0.0),
                            "leverage": action.get("leverage", 1),
                        }
                    elif act in ["close_long", "close_short"]:
                        # 移除已平仓记录
                        open_positions.pop(pos_key, None)

        # 4. 遍历分析窗口，生成交易结果
        recent_trades = []
        symbol_stats: Dict[str, Dict[str, Any]] = {}

        total_win_amount = 0.0
        total_loss_amount = 0.0
        winning_trades = 0
        losing_trades = 0

        for record in records:
            for action in record.get("decisions", []):
                if not action.get("success"):
                    continue

                symbol = action.get("symbol")
                act = action.get("action")

                # 确定方向
                side = ""
                if act in ["open_long", "close_long"]:
                    side = "long"
                elif act in ["open_short", "close_short"]:
                    side = "short"

                if not side:
                    continue

                pos_key = f"{symbol}_{side}"

                if act in ["open_long", "open_short"]:
                    # 更新开仓记录
                    open_positions[pos_key] = {
                        "side": side,
                        "open_price": action.get("price", 0.0),
                        "open_time": action.get("timestamp", ""),
                        "quantity": action.get("quantity", 0.0),
                        "leverage": action.get("leverage", 1),
                    }

                elif act in ["close_long", "close_short"]:
                    # 查找对应的开仓记录
                    if pos_key in open_positions:
                        open_pos = open_positions[pos_key]
                        open_price = open_pos["open_price"]
                        quantity = open_pos["quantity"]
                        leverage = open_pos["leverage"]
                        close_price = action.get("price", 0.0)

                        # 计算实际盈亏（USDT）
                        # 合约交易 PnL = quantity × 价格差
                        if side == "long":
                            pnl = quantity * (close_price - open_price)
                        else:
                            pnl = quantity * (open_price - close_price)

                        # 计算盈亏百分比（相对保证金）
                        position_value = quantity * open_price
                        margin_used = position_value / leverage if leverage > 0 else position_value
                        pnl_pct = (pnl / margin_used * 100) if margin_used > 0 else 0.0

                        # 计算持仓时长
                        try:
                            from dateutil import parser
                            open_dt = parser.parse(open_pos["open_time"])
                            close_dt = parser.parse(action.get("timestamp", ""))
                            duration_seconds = (close_dt - open_dt).total_seconds()

                            # 格式化持仓时长（参考Go版本）
                            hours = int(duration_seconds // 3600)
                            minutes = int((duration_seconds % 3600) // 60)
                            if hours > 0:
                                duration_str = f"{hours}h{minutes}m0s"
                            else:
                                duration_str = f"{minutes}m0s"
                        except:
                            duration_str = "0s"

                        # 记录交易结果
                        trade_outcome = {
                            "symbol": symbol,
                            "side": side,
                            "quantity": quantity,
                            "leverage": leverage,
                            "open_price": open_price,
                            "close_price": close_price,
                            "position_value": position_value,
                            "margin_used": margin_used,
                            "pn_l": pnl,  # 注意：使用 pn_l 与 Go 版本一致
                            "pn_l_pct": pnl_pct,  # 注意：使用 pn_l_pct 与 Go 版本一致
                            "duration": duration_str,  # 持仓时长
                            "open_time": open_pos["open_time"],
                            "close_time": action.get("timestamp", ""),
                            "was_stop_loss": False,  # TODO: 从订单信息判断是否止损
                        }

                        recent_trades.append(trade_outcome)

                        # 分类交易：盈利、亏损
                        if pnl > 0:
                            winning_trades += 1
                            total_win_amount += pnl
                        elif pnl < 0:
                            losing_trades += 1
                            total_loss_amount += pnl  # 负数

                        # 更新币种统计
                        if symbol not in symbol_stats:
                            symbol_stats[symbol] = {
                                "symbol": symbol,
                                "total_trades": 0,
                                "winning_trades": 0,
                                "losing_trades": 0,
                                "win_rate": 0.0,
                                "total_pn_l": 0.0,  # 注意：使用 total_pn_l 与 Go 版本一致（前端期望）
                                "avg_pn_l": 0.0,
                            }

                        stats = symbol_stats[symbol]
                        stats["total_trades"] += 1
                        stats["total_pn_l"] += pnl
                        if pnl > 0:
                            stats["winning_trades"] += 1
                        elif pnl < 0:
                            stats["losing_trades"] += 1

                        # 移除已平仓记录
                        open_positions.pop(pos_key, None)

        # 5. 计算统计指标
        total_trades = len(recent_trades)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        avg_win = (total_win_amount / winning_trades) if winning_trades > 0 else 0.0
        avg_loss = (total_loss_amount / losing_trades) if losing_trades > 0 else 0.0

        # Profit Factor = 总盈利 / |总亏损|
        if total_loss_amount != 0:
            profit_factor = total_win_amount / abs(total_loss_amount)
        elif total_win_amount > 0:
            profit_factor = 999.0  # 只有盈利
        else:
            profit_factor = 0.0

        # 6. 计算各币种胜率和平均盈亏
        best_pnl = -999999.0
        worst_pnl = 999999.0
        best_symbol = ""
        worst_symbol = ""

        for symbol, stats in symbol_stats.items():
            if stats["total_trades"] > 0:
                stats["win_rate"] = (stats["winning_trades"] / stats["total_trades"]) * 100
                stats["avg_pn_l"] = stats["total_pn_l"] / stats["total_trades"]

                if stats["total_pn_l"] > best_pnl:
                    best_pnl = stats["total_pn_l"]
                    best_symbol = symbol

                if stats["total_pn_l"] < worst_pnl:
                    worst_pnl = stats["total_pn_l"]
                    worst_symbol = symbol

        # 7. 只保留最近10笔交易（倒序：最新的在前）
        if len(recent_trades) > 10:
            recent_trades = list(reversed(recent_trades))[:10]
        else:
            recent_trades = list(reversed(recent_trades))

        # 8. 计算夏普比率
        sharpe_ratio = self._calculate_sharpe_ratio(records)

        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe_ratio,
            "recent_trades": recent_trades,
            "symbol_stats": symbol_stats,
            "best_symbol": best_symbol,
            "worst_symbol": worst_symbol,
        }

    def _calculate_sharpe_ratio(self, records: List[Dict[str, Any]]) -> float:
        """
        计算夏普比率（基于账户净值的变化）

        Args:
            records: 决策记录列表

        Returns:
            夏普比率（风险调整后收益）
        """
        if len(records) < 2:
            return 0.0

        # 提取每个周期的账户净值
        equities = []
        for record in records:
            account_state = record.get("account_state", {})
            # TotalBalance 实际存储的是 TotalEquity（账户总净值）
            equity = account_state.get("total_balance", 0.0)
            if equity > 0:
                equities.append(equity)

        if len(equities) < 2:
            return 0.0

        # 计算周期收益率
        returns = []
        for i in range(1, len(equities)):
            if equities[i - 1] > 0:
                period_return = (equities[i] - equities[i - 1]) / equities[i - 1]
                returns.append(period_return)

        if not returns:
            return 0.0

        # 计算平均收益率
        mean_return = sum(returns) / len(returns)

        # 计算收益率标准差
        if len(returns) == 1:
            return 0.0

        squared_diffs = [(r - mean_return) ** 2 for r in returns]
        variance = sum(squared_diffs) / len(returns)
        std_dev = variance ** 0.5

        # 避免除以零
        if std_dev == 0:
            if mean_return > 0:
                return 999.0  # 无波动的正收益
            elif mean_return < 0:
                return -999.0  # 无波动的负收益
            return 0.0

        # 计算夏普比率（假设无风险利率为0）
        sharpe_ratio = mean_return / std_dev
        return sharpe_ratio

    async def get_statistics(self) -> Dict[str, Any]:
        """
        获取基础统计信息（周期级别）

        Returns:
            基础统计数据：总周期数、成功/失败周期、开仓/平仓次数
        """
        try:
            files = list(Path(self.log_dir).glob("decision_*.json"))

            stats = {
                "total_cycles": 0,
                "successful_cycles": 0,
                "failed_cycles": 0,
                "total_open_positions": 0,
                "total_close_positions": 0,
            }

            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        record = json.load(f)

                    stats["total_cycles"] += 1

                    # 统计成功/失败周期
                    if record.get("success", False):
                        stats["successful_cycles"] += 1
                    else:
                        stats["failed_cycles"] += 1

                    # 统计开仓/平仓次数
                    for action in record.get("decisions", []):
                        if action.get("success"):
                            act = action.get("action")
                            if act in ["open_long", "open_short"]:
                                stats["total_open_positions"] += 1
                            elif act in ["close_long", "close_short"]:
                                stats["total_close_positions"] += 1

                except Exception as e:
                    logger.warning(f"读取统计数据失败 {file_path}: {e}")
                    continue

            return stats

        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {
                "total_cycles": 0,
                "successful_cycles": 0,
                "failed_cycles": 0,
                "total_open_positions": 0,
                "total_close_positions": 0,
            }

    async def clean_old_records(self, days: int = 7) -> int:
        """
        清理N天前的旧记录

        Args:
            days: 保留最近N天的记录，默认7天

        Returns:
            删除的记录数量
        """
        from datetime import timedelta

        cutoff_time = datetime.now() - timedelta(days=days)
        removed_count = 0

        try:
            files = list(Path(self.log_dir).glob("decision_*.json"))

            for file_path in files:
                try:
                    # 检查文件修改时间
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)

                    if file_mtime < cutoff_time:
                        file_path.unlink()
                        removed_count += 1

                except Exception as e:
                    logger.warning(f"⚠ 删除旧记录失败 {file_path.name}: {e}")
                    continue

            if removed_count > 0:
                logger.info(f"🗑️ 已清理 {removed_count} 条旧记录（{days}天前）")

            return removed_count

        except Exception as e:
            logger.error(f"清理旧记录失败: {e}")
            return 0

    async def get_record_by_date(self, date: datetime) -> List[Dict[str, Any]]:
        """
        获取指定日期的所有记录

        Args:
            date: 目标日期

        Returns:
            该日期的所有决策记录
        """
        date_str = date.strftime("%Y%m%d")
        pattern = f"decision_{date_str}_*.json"

        records = []
        try:
            files = list(Path(self.log_dir).glob(pattern))

            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        record = json.load(f)
                        records.append(record)
                except Exception as e:
                    logger.warning(f"读取记录失败 {file_path}: {e}")
                    continue

            return records

        except Exception as e:
            logger.error(f"获取日期记录失败: {e}")
            return []

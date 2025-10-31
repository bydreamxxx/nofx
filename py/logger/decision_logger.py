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

    async def get_performance_analysis(self, n: int = 20) -> Dict[str, Any]:
        """
        获取性能分析

        分析最近N条交易记录，计算：
        - 总交易次数
        - 胜率
        - 平均盈利/亏损
        - 盈亏比
        - 最佳/最差币种
        """
        records = await self.get_latest_records(n)

        if not records:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_profit": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "best_coins": [],
                "worst_coins": [],
                "recent_trades": [],
            }

        # 收集所有交易记录
        all_trades = []
        coin_performance: Dict[str, Dict[str, Any]] = {}

        for record in records:
            for decision in record.get("decisions", []):
                if not decision.get("success"):
                    continue

                symbol = decision.get("symbol")
                action = decision.get("action")

                # 简化：只记录平仓操作
                if action in ["close_long", "close_short"]:
                    # 计算盈亏（需要从持仓中计算）
                    # 这里简化处理
                    profit_pct = 0.0  # 需要实际计算

                    trade = {
                        "symbol": symbol,
                        "action": action,
                        "profit_pct": profit_pct,
                        "timestamp": decision.get("timestamp"),
                    }

                    all_trades.append(trade)

                    # 更新币种统计
                    if symbol not in coin_performance:
                        coin_performance[symbol] = {
                            "symbol": symbol,
                            "total_trades": 0,
                            "wins": 0,
                            "total_profit": 0.0,
                        }

                    coin_perf = coin_performance[symbol]
                    coin_perf["total_trades"] += 1

                    if profit_pct > 0:
                        coin_perf["wins"] += 1

                    coin_perf["total_profit"] += profit_pct

        # 计算整体统计
        total_trades = len(all_trades)
        if total_trades == 0:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_profit": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "best_coins": [],
                "worst_coins": [],
                "recent_trades": [],
            }

        wins = sum(1 for t in all_trades if t["profit_pct"] > 0)
        losses = total_trades - wins

        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0.0

        profits = [t["profit_pct"] for t in all_trades if t["profit_pct"] > 0]
        losses_list = [abs(t["profit_pct"]) for t in all_trades if t["profit_pct"] < 0]

        avg_profit = sum(profits) / len(profits) if profits else 0.0
        avg_loss = sum(losses_list) / len(losses_list) if losses_list else 0.0

        profit_factor = avg_profit / avg_loss if avg_loss > 0 else 0.0

        # 按盈利排序币种
        sorted_coins = sorted(
            coin_performance.values(),
            key=lambda x: x["total_profit"],
            reverse=True
        )

        best_coins = sorted_coins[:3]
        worst_coins = sorted_coins[-3:]

        # 最近的交易
        recent_trades = all_trades[-5:]

        return {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": win_rate,
            "avg_profit": avg_profit,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "best_coins": best_coins,
            "worst_coins": worst_coins,
            "recent_trades": recent_trades,
        }

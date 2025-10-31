"""
FastAPI REST API 服务器

提供与Go版本API兼容的端点，供前端Web界面调用
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any, List
from loguru import logger

from manager import TraderManager


def create_app(trader_manager: TraderManager) -> FastAPI:
    """创建FastAPI应用"""
    app = FastAPI(
        title="NOFX Trading System API",
        description="AI驱动的加密货币自动交易系统",
        version="2.0.0",
    )

    # 配置CORS（允许前端访问）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 生产环境应该限制具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # === 健康检查端点 ===
    @app.get("/health")
    async def health_check():
        """健康检查"""
        return {"status": "ok", "service": "nofx-trading-system"}

    # === 竞赛端点 ===
    @app.get("/api/competition")
    async def get_competition():
        """获取竞赛排行榜（所有交易员的表现）"""
        try:
            traders = trader_manager.get_all_traders()
            leaderboard = []

            for trader in traders.values():
                status = trader.get_status()

                # 获取账户信息
                try:
                    balance = await trader.trader.get_balance()
                    total_equity = (
                        balance.get("totalWalletBalance", 0)
                        + balance.get("totalUnrealizedProfit", 0)
                    )
                    roi = (
                        ((total_equity - status["initial_balance"]) / status["initial_balance"]) * 100
                        if status["initial_balance"] > 0
                        else 0
                    )

                    leaderboard.append(
                        {
                            "trader_id": status["id"],
                            "trader_name": status["name"],
                            "ai_model": status["ai_model"],
                            "exchange": status["exchange"],
                            "initial_balance": status["initial_balance"],
                            "current_equity": total_equity,
                            "roi_pct": roi,
                            "is_running": status["is_running"],
                            "call_count": status["call_count"],
                            "runtime_minutes": status["runtime_minutes"],
                        }
                    )
                except Exception as e:
                    logger.warning(f"获取交易员 {status['name']} 账户信息失败: {e}")
                    continue

            # 按ROI降序排序
            leaderboard.sort(key=lambda x: x["roi_pct"], reverse=True)

            return {
                "success": True,
                "leaderboard": leaderboard,
                "total_traders": len(leaderboard),
            }

        except Exception as e:
            logger.error(f"获取竞赛排行榜失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === 交易员状态端点 ===
    @app.get("/api/status")
    async def get_trader_status(trader_id: Optional[str] = None):
        """获取交易员状态"""
        try:
            if trader_id:
                # 获取单个交易员状态
                trader = trader_manager.get_trader(trader_id)
                if not trader:
                    raise HTTPException(status_code=404, detail=f"交易员 {trader_id} 不存在")

                status = trader.get_status()
                return {"success": True, "status": status}
            else:
                # 获取所有交易员状态
                statuses = trader_manager.get_all_trader_status()
                return {"success": True, "traders": statuses}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取交易员状态失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === 账户信息端点 ===
    @app.get("/api/account")
    async def get_account(trader_id: str):
        """获取账户信息"""
        try:
            trader = trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"交易员 {trader_id} 不存在")

            balance = await trader.trader.get_balance()

            total_equity = (
                balance.get("totalWalletBalance", 0)
                + balance.get("totalUnrealizedProfit", 0)
            )

            return {
                "success": True,
                "account": {
                    "total_equity": total_equity,
                    "available_balance": balance.get("availableBalance", 0),
                    "total_wallet_balance": balance.get("totalWalletBalance", 0),
                    "total_unrealized_profit": balance.get("totalUnrealizedProfit", 0),
                    "initial_balance": trader.initial_balance,
                    "total_pnl": total_equity - trader.initial_balance,
                    "total_pnl_pct": (
                        ((total_equity - trader.initial_balance) / trader.initial_balance) * 100
                        if trader.initial_balance > 0
                        else 0
                    ),
                },
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取账户信息失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === 持仓信息端点 ===
    @app.get("/api/positions")
    async def get_positions(trader_id: str):
        """获取持仓信息"""
        try:
            trader = trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"交易员 {trader_id} 不存在")

            positions = await trader.trader.get_positions()

            # 格式化持仓信息
            formatted_positions = []
            for pos in positions:
                formatted_positions.append(
                    {
                        "symbol": pos["symbol"],
                        "side": pos["side"],
                        "position_amt": pos["positionAmt"],
                        "entry_price": pos["entryPrice"],
                        "mark_price": pos["markPrice"],
                        "unrealized_profit": pos["unRealizedProfit"],
                        "liquidation_price": pos["liquidationPrice"],
                        "leverage": pos.get("leverage", 10),
                    }
                )

            return {"success": True, "positions": formatted_positions}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取持仓信息失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === 决策历史端点 ===
    @app.get("/api/decisions/latest")
    async def get_latest_decisions(trader_id: str, limit: int = 10):
        """获取最近的决策记录"""
        try:
            trader = trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"交易员 {trader_id} 不存在")

            records = await trader.decision_logger.get_latest_records(limit)

            return {"success": True, "decisions": records, "count": len(records)}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取决策历史失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === 性能统计端点 ===
    @app.get("/api/statistics")
    async def get_statistics(trader_id: str):
        """获取性能统计"""
        try:
            trader = trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"交易员 {trader_id} 不存在")

            performance = await trader.decision_logger.get_performance_analysis(100)

            return {"success": True, "statistics": performance}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取性能统计失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === 配置信息端点 ===
    @app.get("/api/config")
    async def get_config():
        """获取系统配置"""
        try:
            traders = trader_manager.get_all_traders()

            configs = []
            for trader in traders.values():
                configs.append(
                    {
                        "id": trader.id,
                        "name": trader.name,
                        "ai_model": trader.ai_model,
                        "exchange": trader.exchange,
                        "scan_interval_minutes": trader.config.scan_interval_minutes,
                        "initial_balance": trader.initial_balance,
                        "btc_eth_leverage": trader.config.btc_eth_leverage,
                        "altcoin_leverage": trader.config.altcoin_leverage,
                    }
                )

            return {"success": True, "traders": configs}

        except Exception as e:
            logger.error(f"获取配置信息失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === 净值历史端点（简化版）===
    @app.get("/api/equity-history")
    async def get_equity_history(trader_id: str, hours: int = 24):
        """获取净值历史（暂时返回当前值，完整实现需要历史数据存储）"""
        try:
            trader = trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"交易员 {trader_id} 不存在")

            # 获取当前账户信息
            balance = await trader.trader.get_balance()
            current_equity = (
                balance.get("totalWalletBalance", 0)
                + balance.get("totalUnrealizedProfit", 0)
            )

            # 简化版：只返回当前值
            # 完整实现需要定期记录净值历史到数据库
            from datetime import datetime

            history = [
                {
                    "timestamp": int(datetime.now().timestamp() * 1000),
                    "equity": current_equity,
                }
            ]

            return {"success": True, "history": history}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取净值历史失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    logger.info("✅ FastAPI 服务器已创建")
    return app

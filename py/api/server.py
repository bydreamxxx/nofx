"""
FastAPI REST API 服务器

提供与Go版本API兼容的端点，供前端Web界面调用
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any, List
from loguru import logger
import json

from manager import TraderManager
from config import Database
from .middleware import get_current_user
import auth


def create_app(trader_manager: TraderManager, database: Database = None) -> FastAPI:
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

    # === 工具函数 ===
    async def get_trader_from_query(user_id: str, trader_id: Optional[str] = None):
        """
        从query参数获取trader（模拟Go版本的getTraderFromQuery）

        参数:
            user_id: 当前用户ID
            trader_id: 可选的trader_id，如果不提供则返回用户的第一个trader

        返回:
            (trader_manager, trader_id)

        异常:
            HTTPException 404 - 没有可用的trader
        """
        # 确保用户的交易员已加载到内存中
        await trader_manager.load_traders_from_database(database)

        if trader_id:
            # 验证trader属于当前用户
            traders = await database.get_traders(user_id)
            trader_ids = [t["id"] for t in traders]
            if trader_id not in trader_ids:
                raise HTTPException(status_code=404, detail="交易员不存在或无权访问")
            return trader_manager, trader_id
        else:
            # 如果没有指定trader_id，返回该用户的第一个trader
            traders = await database.get_traders(user_id)
            if not traders:
                raise HTTPException(status_code=404, detail="没有可用的trader")
            return trader_manager, traders[0]["id"]

    # === 健康检查端点（无需认证）===
    @app.get("/health")
    async def health_check():
        """健康检查"""
        return {"status": "ok", "service": "nofx-trading-system"}

    # === 系统配置端点（无需认证）===
    @app.get("/api/config")
    async def get_config():
        """获取系统配置（客户端需要知道的配置）"""
        try:
            if not database:
                raise HTTPException(status_code=500, detail="数据库未初始化")

            # 获取默认币种
            default_coins_str = await database.get_system_config("default_coins")
            default_coins = []
            if default_coins_str:
                try:
                    default_coins = json.loads(default_coins_str)
                except json.JSONDecodeError:
                    pass

            if not default_coins:
                # 使用硬编码的默认币种
                default_coins = [
                    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
                    "XRPUSDT", "DOGEUSDT", "ADAUSDT", "HYPEUSDT"
                ]

            # 获取杠杆配置
            btc_eth_leverage_str = await database.get_system_config("btc_eth_leverage")
            altcoin_leverage_str = await database.get_system_config("altcoin_leverage")

            btc_eth_leverage = 5
            if btc_eth_leverage_str:
                try:
                    btc_eth_leverage = int(btc_eth_leverage_str)
                except ValueError:
                    pass

            altcoin_leverage = 5
            if altcoin_leverage_str:
                try:
                    altcoin_leverage = int(altcoin_leverage_str)
                except ValueError:
                    pass

            # 获取 admin_mode
            admin_mode_str = await database.get_system_config("admin_mode")
            admin_mode = admin_mode_str != "false"

            return {
                "admin_mode": admin_mode,
                "default_coins": default_coins,
                "btc_eth_leverage": btc_eth_leverage,
                "altcoin_leverage": altcoin_leverage,
            }

        except Exception as e:
            logger.error(f"获取系统配置失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === 竞赛端点（需要认证）===
    @app.get("/api/competition")
    async def get_competition(current_user: Dict = Depends(get_current_user)):
        """获取竞赛排行榜（当前用户的所有交易员）"""
        try:
            user_id = current_user["user_id"]

            # 加载用户的交易员
            await trader_manager.load_traders_from_database(database)

            # 获取用户的交易员列表
            user_traders = await database.get_traders(user_id)
            leaderboard = []

            for trader_record in user_traders:
                trader_id = trader_record["id"]
                trader = await trader_manager.get_trader(trader_id)

                if not trader:
                    logger.warning(f"交易员 {trader_id} 未加载到内存")
                    continue

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

                    leaderboard.append({
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
                    })
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

    # === 交易员状态端点（需要认证）===
    @app.get("/api/status")
    async def get_trader_status(
        trader_id: Optional[str] = None,
        current_user: Dict = Depends(get_current_user)
    ):
        """获取交易员状态"""
        try:
            user_id = current_user["user_id"]
            _, trader_id = await get_trader_from_query(user_id, trader_id)

            trader = await trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"交易员 {trader_id} 不存在")

            status = trader.get_status()
            return status

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取交易员状态失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === 账户信息端点（需要认证）===
    @app.get("/api/account")
    async def get_account(
        trader_id: str,
        current_user: Dict = Depends(get_current_user)
    ):
        """获取账户信息"""
        try:
            user_id = current_user["user_id"]
            _, trader_id = await get_trader_from_query(user_id, trader_id)

            trader = await trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"交易员 {trader_id} 不存在")

            balance = await trader.trader.get_balance()

            total_equity = (
                balance.get("totalWalletBalance", 0)
                + balance.get("totalUnrealizedProfit", 0)
            )

            return {
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
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取账户信息失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === 持仓信息端点（需要认证）===
    @app.get("/api/positions")
    async def get_positions(
        trader_id: str,
        current_user: Dict = Depends(get_current_user)
    ):
        """获取持仓信息"""
        try:
            user_id = current_user["user_id"]
            _, trader_id = await get_trader_from_query(user_id, trader_id)

            trader = await trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"交易员 {trader_id} 不存在")

            positions = await trader.trader.get_positions()

            # 格式化持仓信息
            formatted_positions = []
            for pos in positions:
                formatted_positions.append({
                    "symbol": pos["symbol"],
                    "side": pos["side"],
                    "position_amt": pos["positionAmt"],
                    "entry_price": pos["entryPrice"],
                    "mark_price": pos["markPrice"],
                    "unrealized_profit": pos["unRealizedProfit"],
                    "liquidation_price": pos["liquidationPrice"],
                    "leverage": pos.get("leverage", 10),
                })

            return formatted_positions

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取持仓信息失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === 决策历史端点（需要认证）===
    @app.get("/api/decisions/latest")
    async def get_latest_decisions(
        trader_id: str,
        limit: int = 5,
        current_user: Dict = Depends(get_current_user)
    ):
        """获取最近的决策记录"""
        try:
            user_id = current_user["user_id"]
            _, trader_id = await get_trader_from_query(user_id, trader_id)

            trader = await trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"交易员 {trader_id} 不存在")

            records = await trader.decision_logger.get_latest_records(limit)

            # 反转数组，让最新的在前面
            records.reverse()

            return records

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取决策历史失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === 性能统计端点（需要认证）===
    @app.get("/api/statistics")
    async def get_statistics(
        trader_id: str,
        current_user: Dict = Depends(get_current_user)
    ):
        """获取性能统计"""
        try:
            user_id = current_user["user_id"]
            _, trader_id = await get_trader_from_query(user_id, trader_id)

            trader = await trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"交易员 {trader_id} 不存在")

            # 使用 get_performance_analysis 而不是 get_statistics
            performance = await trader.decision_logger.get_performance_analysis(100)

            return performance

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取性能统计失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === 净值历史端点（需要认证）===
    @app.get("/api/equity-history")
    async def get_equity_history(
        trader_id: str,
        hours: int = 24,
        current_user: Dict = Depends(get_current_user)
    ):
        """获取净值历史"""
        try:
            user_id = current_user["user_id"]
            _, trader_id = await get_trader_from_query(user_id, trader_id)

            trader = await trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail=f"交易员 {trader_id} 不存在")

            # 获取历史决策记录（最多10000条，约20天数据）
            records = await trader.decision_logger.get_latest_records(10000)

            # 获取初始余额
            initial_balance = trader.initial_balance
            if initial_balance == 0 and len(records) > 0:
                # 从第一条记录获取
                initial_balance = records[0].get("account_state", {}).get("total_balance", 0)

            if initial_balance == 0:
                raise HTTPException(status_code=500, detail="无法获取初始余额")

            # 构建历史数据点
            history = []
            for record in records:
                account_state = record.get("account_state", {})
                total_equity = account_state.get("total_balance", 0)
                total_pnl = account_state.get("total_unrealized_profit", 0)

                # 计算盈亏百分比
                total_pnl_pct = (total_pnl / initial_balance) * 100 if initial_balance > 0 else 0

                history.append({
                    "timestamp": record.get("timestamp", ""),
                    "total_equity": total_equity,
                    "available_balance": account_state.get("available_balance", 0),
                    "total_pnl": total_pnl,
                    "total_pnl_pct": total_pnl_pct,
                    "position_count": account_state.get("position_count", 0),
                    "margin_used_pct": account_state.get("margin_used_pct", 0),
                    "cycle_number": record.get("cycle_number", 0),
                })

            return history

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取净值历史失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === 用户认证端点（无需认证）===
    @app.post("/api/register")
    async def register_user(email: str, password: str):
        """用户注册"""
        try:
            # 检查邮箱是否已存在
            try:
                existing_user = await database.get_user_by_email(email)
                if existing_user:
                    raise HTTPException(status_code=409, detail="邮箱已被注册")
            except:
                pass  # 用户不存在，可以继续注册

            # 生成密码哈希
            password_hash = auth.hash_password(password)

            # 生成OTP密钥
            otp_secret = auth.generate_otp_secret()

            # 创建用户
            import uuid
            user_id = str(uuid.uuid4())
            await database.create_user(
                user_id=user_id,
                email=email,
                password_hash=password_hash,
                otp_secret=otp_secret,
                otp_verified=False
            )

            # 返回OTP设置信息
            qr_code_url = auth.get_otp_qr_code_url(otp_secret, email)
            return {
                "user_id": user_id,
                "email": email,
                "otp_secret": otp_secret,
                "qr_code_url": qr_code_url,
                "message": "请使用Google Authenticator扫描二维码并验证OTP"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"用户注册失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/complete-registration")
    async def complete_registration(user_id: str, otp_code: str):
        """完成注册（验证OTP）"""
        try:
            # 获取用户信息
            user = await database.get_user_by_id(user_id)
            if not user:
                raise HTTPException(status_code=404, detail="用户不存在")

            # 验证OTP
            if not auth.verify_otp(user["otp_secret"], otp_code):
                raise HTTPException(status_code=400, detail="OTP验证码错误")

            # 更新用户OTP验证状态
            await database.update_user_otp_verified(user_id, True)

            # 生成JWT token
            token = auth.generate_jwt(user["id"], user["email"])

            logger.info(f"✅ 用户 {user['email']} 注册完成")

            return {
                "token": token,
                "user_id": user["id"],
                "email": user["email"],
                "message": "注册完成"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"完成注册失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/login")
    async def login_user(email: str, password: str):
        """用户登录"""
        try:
            # 获取用户信息
            user = await database.get_user_by_email(email)
            if not user:
                raise HTTPException(status_code=401, detail="邮箱或密码错误")

            # 验证密码
            if not auth.check_password(password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="邮箱或密码错误")

            # 检查OTP是否已验证
            if not user.get("otp_verified", False):
                return {
                    "error": "账户未完成OTP设置",
                    "user_id": user["id"],
                    "requires_otp_setup": True
                }

            # 返回需要OTP验证的状态
            return {
                "user_id": user["id"],
                "email": user["email"],
                "message": "请输入Google Authenticator验证码",
                "requires_otp": True
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"用户登录失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/verify-otp")
    async def verify_otp_login(user_id: str, otp_code: str):
        """验证OTP并完成登录"""
        try:
            # 获取用户信息
            user = await database.get_user_by_id(user_id)
            if not user:
                raise HTTPException(status_code=404, detail="用户不存在")

            # 验证OTP
            if not auth.verify_otp(user["otp_secret"], otp_code):
                raise HTTPException(status_code=400, detail="验证码错误")

            # 生成JWT token
            token = auth.generate_jwt(user["id"], user["email"])

            logger.info(f"✅ 用户 {user['email']} 登录成功")

            return {
                "token": token,
                "user_id": user["id"],
                "email": user["email"],
                "message": "登录成功"
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"OTP验证失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === 支持的模型和交易所（无需认证）===
    @app.get("/api/supported-models")
    async def get_supported_models():
        """获取系统支持的AI模型列表"""
        try:
            models = await database.get_ai_models("default")
            return models
        except Exception as e:
            logger.error(f"获取支持的AI模型失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/supported-exchanges")
    async def get_supported_exchanges():
        """获取系统支持的交易所列表"""
        try:
            exchanges = await database.get_exchanges("default")
            return exchanges
        except Exception as e:
            logger.error(f"获取支持的交易所失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === AI模型和交易所配置端点（需要认证）===
    @app.get("/api/models")
    async def get_model_configs(current_user: Dict = Depends(get_current_user)):
        """获取用户的AI模型配置"""
        try:
            user_id = current_user["user_id"]
            models = await database.get_ai_models(user_id)
            return models
        except Exception as e:
            logger.error(f"获取AI模型配置失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.put("/api/models")
    async def update_model_configs(
        models: Dict[str, Dict],
        current_user: Dict = Depends(get_current_user)
    ):
        """更新AI模型配置"""
        try:
            user_id = current_user["user_id"]

            # 遍历更新每个模型
            for model_id, model_data in models.get("models", {}).items():
                await database.update_ai_model(
                    user_id=user_id,
                    model_id=model_id,
                    enabled=model_data.get("enabled", False),
                    api_key=model_data.get("api_key", ""),
                    custom_api_url=model_data.get("custom_api_url", ""),
                    custom_model_name=model_data.get("custom_model_name", "")
                )

            logger.info(f"✅ AI模型配置已更新: {list(models.get('models', {}).keys())}")
            return {"message": "模型配置已更新"}
        except Exception as e:
            logger.error(f"更新AI模型配置失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/exchanges")
    async def get_exchange_configs(current_user: Dict = Depends(get_current_user)):
        """获取用户的交易所配置"""
        try:
            user_id = current_user["user_id"]
            exchanges = await database.get_exchanges(user_id)
            return exchanges
        except Exception as e:
            logger.error(f"获取交易所配置失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.put("/api/exchanges")
    async def update_exchange_configs(
        exchanges: Dict[str, Dict],
        current_user: Dict = Depends(get_current_user)
    ):
        """更新交易所配置"""
        try:
            user_id = current_user["user_id"]

            # 遍历更新每个交易所
            for exchange_id, exchange_data in exchanges.get("exchanges", {}).items():
                await database.update_exchange(
                    user_id=user_id,
                    exchange_id=exchange_id,
                    enabled=exchange_data.get("enabled", False),
                    api_key=exchange_data.get("api_key", ""),
                    secret_key=exchange_data.get("secret_key", ""),
                    testnet=exchange_data.get("testnet", False),
                    hyperliquid_wallet_addr=exchange_data.get("hyperliquid_wallet_addr", ""),
                    aster_user=exchange_data.get("aster_user", ""),
                    aster_signer=exchange_data.get("aster_signer", ""),
                    aster_private_key=exchange_data.get("aster_private_key", "")
                )

            logger.info(f"✅ 交易所配置已更新: {list(exchanges.get('exchanges', {}).keys())}")
            return {"message": "交易所配置已更新"}
        except Exception as e:
            logger.error(f"更新交易所配置失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === 用户信号源配置端点（需要认证）===
    @app.get("/api/user/signal-sources")
    async def get_user_signal_source(current_user: Dict = Depends(get_current_user)):
        """获取用户信号源配置"""
        try:
            user_id = current_user["user_id"]
            source = await database.get_user_signal_source(user_id)

            if source:
                return {
                    "coin_pool_url": source.get("coin_pool_url", ""),
                    "oi_top_url": source.get("oi_top_url", "")
                }
            else:
                # 如果配置不存在，返回空配置
                return {
                    "coin_pool_url": "",
                    "oi_top_url": ""
                }
        except Exception as e:
            logger.error(f"获取用户信号源配置失败: {e}")
            # 返回空配置而不是错误
            return {
                "coin_pool_url": "",
                "oi_top_url": ""
            }

    @app.post("/api/user/signal-sources")
    async def save_user_signal_source(
        coin_pool_url: str = "",
        oi_top_url: str = "",
        current_user: Dict = Depends(get_current_user)
    ):
        """保存用户信号源配置"""
        try:
            user_id = current_user["user_id"]
            await database.create_user_signal_source(user_id, coin_pool_url, oi_top_url)

            logger.info(f"✅ 用户信号源配置已保存: user={user_id}, coin_pool={coin_pool_url}, oi_top={oi_top_url}")
            return {"message": "用户信号源配置已保存"}
        except Exception as e:
            logger.error(f"保存用户信号源配置失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # === Trader管理端点（需要认证）===
    @app.get("/api/traders")
    async def get_traders(current_user: Dict = Depends(get_current_user)):
        """获取交易员列表"""
        try:
            user_id = current_user["user_id"]
            traders = await database.get_traders(user_id)

            result = []
            for trader in traders:
                # 获取实时运行状态
                is_running = trader.get("is_running", False)
                trader_obj = await trader_manager.get_trader(trader["id"])
                if trader_obj:
                    status = trader_obj.get_status()
                    is_running = status.get("is_running", False)

                result.append({
                    "trader_id": trader["id"],
                    "trader_name": trader["name"],
                    "ai_model": trader["ai_model_id"],
                    "exchange_id": trader["exchange_id"],
                    "is_running": is_running,
                    "initial_balance": trader.get("initial_balance", 0)
                })

            return result

        except Exception as e:
            logger.error(f"获取交易员列表失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/traders/{trader_id}/config")
    async def get_trader_config(
        trader_id: str,
        current_user: Dict = Depends(get_current_user)
    ):
        """获取交易员详细配置"""
        try:
            user_id = current_user["user_id"]

            # 验证trader属于当前用户
            traders = await database.get_traders(user_id)
            trader_config = None
            for t in traders:
                if t["id"] == trader_id:
                    trader_config = t
                    break

            if not trader_config:
                raise HTTPException(status_code=404, detail="交易员不存在")

            # 获取实时运行状态
            is_running = trader_config.get("is_running", False)
            trader_obj = await trader_manager.get_trader(trader_id)
            if trader_obj:
                status = trader_obj.get_status()
                is_running = status.get("is_running", False)

            return {
                "trader_id": trader_config["id"],
                "trader_name": trader_config["name"],
                "ai_model": trader_config["ai_model_id"],
                "exchange_id": trader_config["exchange_id"],
                "initial_balance": trader_config.get("initial_balance", 0),
                "btc_eth_leverage": trader_config.get("btc_eth_leverage", 5),
                "altcoin_leverage": trader_config.get("altcoin_leverage", 5),
                "trading_symbols": trader_config.get("trading_symbols", ""),
                "system_prompt_template": trader_config.get("system_prompt_template", "default"),
                "custom_prompt": trader_config.get("custom_prompt", ""),
                "override_base_prompt": trader_config.get("override_base_prompt", False),
                "is_cross_margin": trader_config.get("is_cross_margin", True),
                "use_coin_pool": trader_config.get("use_coin_pool", False),
                "use_oi_top": trader_config.get("use_oi_top", False),
                "is_running": is_running
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取交易员配置失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/traders")
    async def create_trader(
        name: str,
        ai_model_id: str,
        exchange_id: str,
        initial_balance: float = 1000.0,
        btc_eth_leverage: int = 5,
        altcoin_leverage: int = 5,
        trading_symbols: str = "",
        system_prompt_template: str = "default",
        custom_prompt: str = "",
        override_base_prompt: bool = False,
        is_cross_margin: bool = True,
        use_coin_pool: bool = False,
        use_oi_top: bool = False,
        current_user: Dict = Depends(get_current_user)
    ):
        """创建新的AI交易员"""
        try:
            user_id = current_user["user_id"]

            # 生成交易员ID
            import time
            trader_id = f"{exchange_id}_{ai_model_id}_{int(time.time())}"

            # 创建交易员记录
            await database.create_trader(
                trader_id=trader_id,
                user_id=user_id,
                name=name,
                ai_model_id=ai_model_id,
                exchange_id=exchange_id,
                initial_balance=initial_balance,
                btc_eth_leverage=btc_eth_leverage,
                altcoin_leverage=altcoin_leverage,
                trading_symbols=trading_symbols,
                system_prompt_template=system_prompt_template,
                custom_prompt=custom_prompt,
                override_base_prompt=override_base_prompt,
                is_cross_margin=is_cross_margin,
                use_coin_pool=use_coin_pool,
                use_oi_top=use_oi_top
            )

            # 加载到内存
            await trader_manager.load_traders_from_database(database)

            logger.info(f"✅ 创建交易员成功: {name} (模型: {ai_model_id}, 交易所: {exchange_id})")

            return {
                "trader_id": trader_id,
                "trader_name": name,
                "ai_model": ai_model_id,
                "is_running": False
            }

        except Exception as e:
            logger.error(f"创建交易员失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/api/traders/{trader_id}")
    async def delete_trader(
        trader_id: str,
        current_user: Dict = Depends(get_current_user)
    ):
        """删除交易员"""
        try:
            user_id = current_user["user_id"]

            # 如果交易员正在运行，先停止它
            trader_obj = await trader_manager.get_trader(trader_id)
            if trader_obj:
                status = trader_obj.get_status()
                if status.get("is_running", False):
                    trader_obj.stop()
                    logger.info(f"⏹  已停止运行中的交易员: {trader_id}")

            # 从数据库删除
            await database.delete_trader(user_id, trader_id)

            logger.info(f"✅ 交易员已删除: {trader_id}")
            return {"message": "交易员已删除"}

        except Exception as e:
            logger.error(f"删除交易员失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/traders/{trader_id}/start")
    async def start_trader(
        trader_id: str,
        current_user: Dict = Depends(get_current_user)
    ):
        """启动交易员"""
        try:
            user_id = current_user["user_id"]

            # 验证trader属于当前用户
            await get_trader_from_query(user_id, trader_id)

            trader = await trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail="交易员不存在")

            # 检查是否已经在运行
            status = trader.get_status()
            if status.get("is_running", False):
                raise HTTPException(status_code=400, detail="交易员已在运行中")

            # 启动交易员（在后台运行）
            import asyncio

            async def run_trader_with_error_handling():
                """带错误处理的交易员运行包装"""
                try:
                    logger.info(f"▶️  启动交易员 {trader_id} ({trader.name})")
                    await trader.run()
                except Exception as e:
                    logger.error(f"❌ 交易员 {trader.name} 运行错误: {e}")

            # 创建后台任务（asyncio会自动管理）
            asyncio.create_task(run_trader_with_error_handling())

            # 更新数据库状态
            await database.update_trader_status(user_id, trader_id, True)

            logger.info(f"✅ 交易员 {trader_id} 已启动")
            return {"message": "交易员已启动"}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"启动交易员失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/traders/{trader_id}/stop")
    async def stop_trader(
        trader_id: str,
        current_user: Dict = Depends(get_current_user)
    ):
        """停止交易员"""
        try:
            user_id = current_user["user_id"]

            # 验证trader属于当前用户
            await get_trader_from_query(user_id, trader_id)

            trader = await trader_manager.get_trader(trader_id)
            if not trader:
                raise HTTPException(status_code=404, detail="交易员不存在")

            # 检查是否正在运行
            status = trader.get_status()
            if not status.get("is_running", False):
                raise HTTPException(status_code=400, detail="交易员已停止")

            # 停止交易员
            trader.stop()

            # 更新数据库状态
            await database.update_trader_status(user_id, trader_id, False)

            logger.info(f"⏹  交易员 {trader_id} 已停止")
            return {"message": "交易员已停止"}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"停止交易员失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ==================== 提示词模板管理 ====================

    @app.get("/api/prompt-templates")
    async def get_prompt_templates(
        current_user: Dict = Depends(get_current_user)
    ):
        """获取所有系统提示词模板列表"""
        try:
            from decision.prompt_manager import get_all_prompt_templates

            templates = get_all_prompt_templates()

            # 转换为响应格式
            response = [{"name": tmpl.name} for tmpl in templates]

            return {"templates": response}

        except Exception as e:
            logger.error(f"获取提示词模板列表失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/prompt-templates/{template_name}")
    async def get_prompt_template(
        template_name: str,
        current_user: Dict = Depends(get_current_user)
    ):
        """获取指定名称的提示词模板内容"""
        try:
            from decision.prompt_manager import get_prompt_template

            template = get_prompt_template(template_name)

            if not template:
                raise HTTPException(status_code=404, detail=f"模板不存在: {template_name}")

            return {
                "name": template.name,
                "content": template.content
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"获取提示词模板失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    logger.info("✅ FastAPI 服务器已创建")
    return app

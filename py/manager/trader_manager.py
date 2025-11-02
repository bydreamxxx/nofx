"""
交易员管理器

负责管理多个AutoTrader实例，支持：
1. 从数据库加载交易员配置
2. 启动/停止所有交易员
3. 查询交易员状态
4. 多交易员竞赛模式
"""

import asyncio
from typing import Dict, List, Optional, Any
from loguru import logger

from trader.auto_trader import AutoTrader, AutoTraderConfig
from config import Database


class TraderManager:
    """交易员管理器"""

    def __init__(self):
        self.traders: Dict[str, AutoTrader] = {}  # key: trader ID
        self.trader_tasks: Dict[str, asyncio.Task] = {}  # 运行中的任务
        self._lock = asyncio.Lock()  # 并发锁保护 traders 和 trader_tasks

    async def load_traders_from_database(self, database: Database) -> None:
        """从数据库加载所有交易员到内存"""
        # 根据admin_mode确定用户ID
        admin_mode_str = await database.get_system_config("admin_mode")
        user_id = "admin" if admin_mode_str != "false" else "default"

        # 获取数据库中的所有交易员
        traders = await database.get_traders(user_id)
        logger.info(f"📋 加载数据库中的交易员配置: {len(traders)} 个 (用户: {user_id})")

        # 获取系统配置
        coin_pool_url = await database.get_system_config("coin_pool_api_url")
        oi_top_url = await database.get_system_config("oi_top_api_url")
        use_default_coins_str = await database.get_system_config("use_default_coins")
        max_daily_loss_str = await database.get_system_config("max_daily_loss")
        max_drawdown_str = await database.get_system_config("max_drawdown")
        stop_trading_minutes_str = await database.get_system_config(
            "stop_trading_minutes"
        )
        btc_eth_leverage_str = await database.get_system_config("btc_eth_leverage")
        altcoin_leverage_str = await database.get_system_config("altcoin_leverage")

        # 解析配置
        use_default_coins = use_default_coins_str == "true"
        max_daily_loss = float(max_daily_loss_str) if max_daily_loss_str else 10.0
        max_drawdown = float(max_drawdown_str) if max_drawdown_str else 20.0
        stop_trading_minutes = (
            int(stop_trading_minutes_str) if stop_trading_minutes_str else 60
        )
        btc_eth_leverage = (
            int(btc_eth_leverage_str) if btc_eth_leverage_str else 5
        )
        altcoin_leverage = (
            int(altcoin_leverage_str) if altcoin_leverage_str else 5
        )

        # 获取默认币种列表
        default_coins_str = await database.get_system_config("default_coins")
        default_coins = []
        if default_coins_str:
            import json
            try:
                default_coins = json.loads(default_coins_str)
            except json.JSONDecodeError:
                logger.warning(f"⚠️ 解析 default_coins 失败，使用空列表")
                default_coins = []

        # 为每个交易员获取AI模型和交易所配置
        for trader_cfg in traders:
            if not trader_cfg.get("enabled", True):
                logger.info(f"⏭️  交易员 {trader_cfg['name']} 未启用，跳过")
                continue

            # 获取AI模型配置
            ai_models = await database.get_ai_models(user_id)
            ai_model_cfg = None
            for model in ai_models:
                if model["id"] == trader_cfg["ai_model_id"]:
                    ai_model_cfg = model
                    break

            if not ai_model_cfg:
                logger.warning(
                    f"⚠️  交易员 {trader_cfg['name']} 的AI模型 {trader_cfg['ai_model_id']} 不存在，跳过"
                )
                continue

            if not ai_model_cfg.get("enabled", True):
                logger.warning(
                    f"⚠️  交易员 {trader_cfg['name']} 的AI模型 {ai_model_cfg['name']} 未启用，跳过"
                )
                continue

            # 获取交易所配置
            exchanges = await database.get_exchanges(user_id)
            exchange_cfg = None
            for exchange in exchanges:
                if exchange["id"] == trader_cfg["exchange_id"]:
                    exchange_cfg = exchange
                    break

            if not exchange_cfg:
                logger.warning(
                    f"⚠️  交易员 {trader_cfg['name']} 的交易所 {trader_cfg['exchange_id']} 不存在，跳过"
                )
                continue

            if not exchange_cfg.get("enabled", True):
                logger.warning(
                    f"⚠️  交易员 {trader_cfg['name']} 的交易所 {exchange_cfg['name']} 未启用，跳过"
                )
                continue

            # 添加到TraderManager
            try:
                await self._add_trader_from_db(
                    trader_cfg=trader_cfg,
                    ai_model_cfg=ai_model_cfg,
                    exchange_cfg=exchange_cfg,
                    coin_pool_url=coin_pool_url,
                    oi_top_url=oi_top_url,
                    use_default_coins=use_default_coins,
                    max_daily_loss=max_daily_loss,
                    max_drawdown=max_drawdown,
                    stop_trading_hours=stop_trading_minutes / 60,
                    btc_eth_leverage=btc_eth_leverage,
                    altcoin_leverage=altcoin_leverage,
                    default_coins=default_coins,
                )
            except Exception as e:
                logger.error(f"❌ 添加交易员 {trader_cfg['name']} 失败: {e}")
                continue

        logger.info(f"✓ 成功加载 {len(self.traders)} 个交易员到内存")

    async def load_user_traders(self, database: Database, user_id: str) -> None:
        """
        从数据库加载指定用户的交易员到内存（用于API请求）

        Args:
            database: 数据库实例
            user_id: 用户ID
        """
        # 获取指定用户的所有交易员
        traders = await database.get_traders(user_id)
        logger.debug(f"📋 为用户 {user_id} 加载交易员配置: {len(traders)} 个")

        # 获取系统配置
        coin_pool_url = await database.get_system_config("coin_pool_api_url")
        oi_top_url = await database.get_system_config("oi_top_api_url")
        use_default_coins_str = await database.get_system_config("use_default_coins")
        max_daily_loss_str = await database.get_system_config("max_daily_loss")
        max_drawdown_str = await database.get_system_config("max_drawdown")
        stop_trading_minutes_str = await database.get_system_config("stop_trading_minutes")
        btc_eth_leverage_str = await database.get_system_config("btc_eth_leverage")
        altcoin_leverage_str = await database.get_system_config("altcoin_leverage")

        # 解析配置
        use_default_coins = use_default_coins_str == "true"
        max_daily_loss = float(max_daily_loss_str) if max_daily_loss_str else 10.0
        max_drawdown = float(max_drawdown_str) if max_drawdown_str else 20.0
        stop_trading_minutes = int(stop_trading_minutes_str) if stop_trading_minutes_str else 60
        btc_eth_leverage = int(btc_eth_leverage_str) if btc_eth_leverage_str else 5
        altcoin_leverage = int(altcoin_leverage_str) if altcoin_leverage_str else 5

        # 获取默认币种列表
        default_coins_str = await database.get_system_config("default_coins")
        default_coins = []
        if default_coins_str:
            import json
            try:
                default_coins = json.loads(default_coins_str)
            except json.JSONDecodeError:
                logger.warning(f"⚠️ 解析 default_coins 失败，使用空列表")
                default_coins = []

        # 获取用户信号源配置
        try:
            signal_source = await database.get_user_signal_source(user_id)
            if signal_source:
                coin_pool_url = signal_source.get("coin_pool_url", "")
                oi_top_url = signal_source.get("oi_top_url", "")
                logger.debug(f"📡 加载用户 {user_id} 的信号源配置: COIN POOL={coin_pool_url}, OI TOP={oi_top_url}")
        except:
            logger.debug(f"🔍 用户 {user_id} 暂未配置信号源")

        # 为每个交易员获取AI模型和交易所配置
        for trader_cfg in traders:
            # 检查是否已经加载过这个交易员
            async with self._lock:
                if trader_cfg["id"] in self.traders:
                    logger.debug(f"⚠️ 交易员 {trader_cfg['name']} 已经加载，跳过")
                    continue

            if not trader_cfg.get("enabled", True):
                logger.debug(f"⏭️  交易员 {trader_cfg['name']} 未启用，跳过")
                continue

            # 获取AI模型配置
            ai_models = await database.get_ai_models(user_id)
            ai_model_cfg = None
            for model in ai_models:
                if model["id"] == trader_cfg["ai_model_id"]:
                    ai_model_cfg = model
                    break

            if not ai_model_cfg:
                logger.warning(f"⚠️  交易员 {trader_cfg['name']} 的AI模型 {trader_cfg['ai_model_id']} 不存在，跳过")
                continue

            if not ai_model_cfg.get("enabled", True):
                logger.warning(f"⚠️  交易员 {trader_cfg['name']} 的AI模型 {ai_model_cfg['name']} 未启用，跳过")
                continue

            # 获取交易所配置
            exchanges = await database.get_exchanges(user_id)
            exchange_cfg = None
            for exchange in exchanges:
                if exchange["id"] == trader_cfg["exchange_id"]:
                    exchange_cfg = exchange
                    break

            if not exchange_cfg:
                logger.warning(f"⚠️  交易员 {trader_cfg['name']} 的交易所 {trader_cfg['exchange_id']} 不存在，跳过")
                continue

            if not exchange_cfg.get("enabled", True):
                logger.warning(f"⚠️  交易员 {trader_cfg['name']} 的交易所 {exchange_cfg['name']} 未启用，跳过")
                continue

            # 添加到TraderManager
            try:
                await self._add_trader_from_db(
                    trader_cfg=trader_cfg,
                    ai_model_cfg=ai_model_cfg,
                    exchange_cfg=exchange_cfg,
                    coin_pool_url=coin_pool_url,
                    oi_top_url=oi_top_url,
                    use_default_coins=use_default_coins,
                    max_daily_loss=max_daily_loss,
                    max_drawdown=max_drawdown,
                    stop_trading_hours=stop_trading_minutes / 60,
                    btc_eth_leverage=btc_eth_leverage,
                    altcoin_leverage=altcoin_leverage,
                    default_coins=default_coins,
                )
            except Exception as e:
                logger.error(f"❌ 添加交易员 {trader_cfg['name']} 失败: {e}")
                continue

    async def _add_trader_from_db(
        self,
        trader_cfg: Dict[str, Any],
        ai_model_cfg: Dict[str, Any],
        exchange_cfg: Dict[str, Any],
        coin_pool_url: str,
        oi_top_url: str,
        use_default_coins: bool,
        max_daily_loss: float,
        max_drawdown: float,
        stop_trading_hours: float,
        btc_eth_leverage: int,
        altcoin_leverage: int,
        default_coins: List[str],
    ) -> None:
        """内部方法：从配置添加交易员"""
        trader_id = trader_cfg["id"]

        # 锁保护：检查是否已存在
        async with self._lock:
            if trader_id in self.traders:
                logger.info(f"⚠️ 交易员 {trader_cfg['name']} 已经加载，跳过")
                return  # 跳过已存在的交易员，不抛出异常

        # 处理交易币种列表
        trading_coins = []
        if trader_cfg.get("trading_symbols"):
            # 解析逗号分隔的交易币种列表
            symbols = trader_cfg["trading_symbols"].split(",")
            for symbol in symbols:
                symbol = symbol.strip()
                if symbol:
                    trading_coins.append(symbol)

        # 如果没有指定交易币种，使用默认币种
        if not trading_coins:
            trading_coins = default_coins

        # 根据交易员配置决定是否使用信号源
        effective_coin_pool_url = ""
        effective_oi_top_url = ""
        if trader_cfg.get("use_coin_pool") and coin_pool_url:
            effective_coin_pool_url = coin_pool_url
            logger.info(f"✓ 交易员 {trader_cfg['name']} 启用 COIN POOL 信号源: {coin_pool_url}")
        if trader_cfg.get("use_oi_top") and oi_top_url:
            effective_oi_top_url = oi_top_url
            logger.info(f"✓ 交易员 {trader_cfg['name']} 启用 OI TOP 信号源: {oi_top_url}")

        # 如果都没启用，使用默认币种
        use_default_coins_flag = use_default_coins
        if not effective_coin_pool_url and not effective_oi_top_url:
            use_default_coins_flag = True

        # 构建AutoTraderConfig
        config = AutoTraderConfig(
            id=trader_id,
            name=trader_cfg["name"],
            ai_model=ai_model_cfg["provider"],
            exchange=exchange_cfg["id"],
            scan_interval_minutes=trader_cfg["scan_interval_minutes"],
            initial_balance=trader_cfg["initial_balance"],
            btc_eth_leverage=btc_eth_leverage,
            altcoin_leverage=altcoin_leverage,
            max_daily_loss=max_daily_loss,
            max_drawdown=max_drawdown,
            stop_trading_hours=stop_trading_hours,
            is_cross_margin=trader_cfg.get("is_cross_margin", True),
            use_default_coins=use_default_coins_flag,
            coin_pool_api_url=effective_coin_pool_url,
            oi_top_api_url=effective_oi_top_url,
            default_coins=default_coins,
            trading_coins=trading_coins,
            # 提示词配置
            system_prompt_template=trader_cfg.get("system_prompt_template", "default"),
            custom_prompt=trader_cfg.get("custom_prompt", ""),
            override_base_prompt=trader_cfg.get("override_base_prompt", False),
        )

        # 根据交易所类型设置API密钥
        if exchange_cfg["id"] == "binance":
            config.binance_api_key = exchange_cfg["api_key"]
            config.binance_secret_key = exchange_cfg["secret_key"]
            config.testnet = exchange_cfg.get("testnet", False)
        elif exchange_cfg["id"] == "hyperliquid":
            config.hyperliquid_private_key = exchange_cfg.get("private_key", "")
            config.hyperliquid_wallet_address = exchange_cfg.get("wallet_address", "")
            config.testnet = exchange_cfg.get("testnet", False)
        elif exchange_cfg["id"] == "aster":
            config.aster_private_key = exchange_cfg.get("private_key", "")
            config.aster_wallet_address = exchange_cfg.get("wallet_address", "")
            config.testnet = exchange_cfg.get("testnet", False)
        elif exchange_cfg["id"] == "okx":
            config.okx_api_key = exchange_cfg.get("api_key", "")
            config.okx_api_secret = exchange_cfg.get("secret_key", "")
            config.okx_passphrase = exchange_cfg.get("passphrase", "")
            config.testnet = exchange_cfg.get("testnet", False)

        # 根据AI模型设置API密钥
        if ai_model_cfg["provider"] == "qwen":
            config.qwen_key = ai_model_cfg["api_key"]
            # 支持自定义 URL 和模型名称（如果有）
            config.custom_api_url = ai_model_cfg.get("custom_api_url", "")
            config.custom_model_name = ai_model_cfg.get("custom_model_name", "")
        elif ai_model_cfg["provider"] == "openrouter":
            config.openrouter_key = ai_model_cfg["api_key"]
            # 支持自定义 URL 和模型名称（如果有）
            config.custom_api_url = ai_model_cfg.get("custom_api_url", "")
            config.custom_model_name = ai_model_cfg.get("custom_model_name", "")
        elif ai_model_cfg["provider"] == "deepseek":
            config.deepseek_key = ai_model_cfg["api_key"]
            # 支持自定义 URL 和模型名称（如果有）
            config.custom_api_url = ai_model_cfg.get("custom_api_url", "")
            config.custom_model_name = ai_model_cfg.get("custom_model_name", "")
        elif ai_model_cfg["provider"] == "custom":
            config.custom_api_url = ai_model_cfg.get("base_url", "")
            config.custom_api_key = ai_model_cfg["api_key"]
            config.custom_model_name = ai_model_cfg.get("model_name", "")

        # 创建trader实例
        auto_trader = AutoTrader(config)

        # 初始化trader
        await auto_trader.initialize()

        # 锁保护：添加到管理器
        async with self._lock:
            self.traders[trader_id] = auto_trader

        logger.info(
            f"✅ 交易员 {trader_cfg['name']} (ID: {trader_id}) 已添加到管理器"
        )

    async def start_all(self) -> None:
        """启动所有交易员"""
        # 锁保护：读取 traders
        async with self._lock:
            traders_copy = dict(self.traders)
            logger.info(f"🚀 启动所有交易员 ({len(traders_copy)} 个)...")

        for trader_id, trader in traders_copy.items():
            try:
                # 创建异步任务
                task = asyncio.create_task(trader.run())

                # 锁保护：写入 trader_tasks
                async with self._lock:
                    self.trader_tasks[trader_id] = task

                logger.info(f"✅ 交易员 {trader.name} 已启动")
            except Exception as e:
                logger.error(f"❌ 启动交易员 {trader.name} 失败: {e}")

        async with self._lock:
            logger.info(f"✓ 已启动 {len(self.trader_tasks)} 个交易员")

    async def stop_all(self) -> None:
        """停止所有交易员"""
        # 锁保护：读取 traders
        async with self._lock:
            traders_copy = dict(self.traders)
            logger.info(f"⏹ 停止所有交易员 ({len(traders_copy)} 个)...")

        for trader_id, trader in traders_copy.items():
            try:
                trader.stop()
                logger.info(f"✅ 交易员 {trader.name} 停止信号已发送")
            except Exception as e:
                logger.error(f"❌ 停止交易员 {trader.name} 失败: {e}")

        # 锁保护：读取任务列表
        async with self._lock:
            tasks = list(self.trader_tasks.values()) if self.trader_tasks else []

        # 在锁外等待任务完成（避免长时间持有锁）
        if tasks:
            logger.debug(f"⏳ 等待 {len(tasks)} 个交易员任务完成...")
            _, pending = await asyncio.wait(tasks, timeout=10.0)

            if pending:
                logger.warning(f"⚠️ {len(pending)} 个任务未能在 10 秒内停止，强制取消")
                for task in pending:
                    task.cancel()
                # 等待取消完成
                await asyncio.gather(*pending, return_exceptions=True)

        # 清空任务字典
        async with self._lock:
            self.trader_tasks.clear()

        logger.info("✓ 所有交易员已停止")

    async def get_trader(self, trader_id: str) -> Optional[AutoTrader]:
        """获取指定交易员"""
        async with self._lock:
            return self.traders.get(trader_id)

    async def get_all_traders(self) -> Dict[str, AutoTrader]:
        """获取所有交易员"""
        async with self._lock:
            return dict(self.traders)

    async def get_trader_status(self, trader_id: str) -> Optional[Dict[str, Any]]:
        """获取指定交易员的状态"""
        async with self._lock:
            trader = self.traders.get(trader_id)
            if not trader:
                return None
        return trader.get_status()

    async def get_all_trader_status(self) -> List[Dict[str, Any]]:
        """获取所有交易员的状态"""
        async with self._lock:
            traders_copy = list(self.traders.values())

        statuses = []
        for trader in traders_copy:
            statuses.append(trader.get_status())
        return statuses

"""
SQLite 数据库管理
"""

import aiosqlite
import secrets
from typing import Optional, Dict, Any, List
from datetime import datetime


class Database:
    """配置数据库管理"""

    def __init__(self, db_path: str = "nofx.db"):
        self.db_path = db_path
        self.db: Optional[aiosqlite.Connection] = None

    async def connect(self):
        """连接数据库"""
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row
        await self.create_tables()
        await self.init_default_data()

    async def close(self):
        """关闭数据库连接"""
        if self.db:
            await self.db.close()

    async def create_tables(self):
        """创建数据库表"""
        queries = [
            # AI模型配置表
            """CREATE TABLE IF NOT EXISTS ai_models (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT 'default',
                name TEXT NOT NULL,
                provider TEXT NOT NULL,
                enabled BOOLEAN DEFAULT 0,
                api_key TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )""",

            # 交易所配置表
            """CREATE TABLE exchanges_new (
			id TEXT NOT NULL,
			user_id TEXT NOT NULL DEFAULT 'default',
			name TEXT NOT NULL,
			type TEXT NOT NULL,
			enabled BOOLEAN DEFAULT 0,
			api_key TEXT DEFAULT '',
			secret_key TEXT DEFAULT '',
			testnet BOOLEAN DEFAULT 0,
			hyperliquid_wallet_addr TEXT DEFAULT '',
			aster_user TEXT DEFAULT '',
			aster_signer TEXT DEFAULT '',
			aster_private_key TEXT DEFAULT '',
			created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
			PRIMARY KEY (id, user_id),
			FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )""",

            # 用户信号源配置表
            """CREATE TABLE IF NOT EXISTS user_signal_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                coin_pool_url TEXT DEFAULT '',
                oi_top_url TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(user_id)
            )""",

            # 交易员配置表
            """CREATE TABLE IF NOT EXISTS traders (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL DEFAULT 'default',
                name TEXT NOT NULL,
                ai_model_id TEXT NOT NULL,
                exchange_id TEXT NOT NULL,
                initial_balance REAL NOT NULL,
                scan_interval_minutes INTEGER DEFAULT 3,
                is_running BOOLEAN DEFAULT 0,
                btc_eth_leverage INTEGER DEFAULT 5,
                altcoin_leverage INTEGER DEFAULT 5,
                trading_symbols TEXT DEFAULT '',
                use_coin_pool BOOLEAN DEFAULT 0,
                use_oi_top BOOLEAN DEFAULT 0,
                custom_prompt TEXT DEFAULT '',
                override_base_prompt BOOLEAN DEFAULT 0,
                is_cross_margin BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (ai_model_id) REFERENCES ai_models(id),
                FOREIGN KEY (exchange_id) REFERENCES exchanges(id)
            )""",

            # 用户表
            """CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                otp_secret TEXT,
                otp_verified BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",

            # 系统配置表
            """CREATE TABLE IF NOT EXISTS system_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",

            # 触发器：自动更新 updated_at
            """CREATE TRIGGER IF NOT EXISTS update_users_updated_at
                AFTER UPDATE ON users
                BEGIN
                    UPDATE users SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END""",

            """CREATE TRIGGER IF NOT EXISTS update_ai_models_updated_at
                AFTER UPDATE ON ai_models
                BEGIN
                    UPDATE ai_models SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END""",

            """CREATE TRIGGER IF NOT EXISTS update_exchanges_updated_at
                AFTER UPDATE ON exchanges
                BEGIN
                    UPDATE exchanges SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END""",

            """CREATE TRIGGER IF NOT EXISTS update_traders_updated_at
                AFTER UPDATE ON traders
                BEGIN
                    UPDATE traders SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END""",

            """CREATE TRIGGER IF NOT EXISTS update_system_config_updated_at
                AFTER UPDATE ON system_config
                BEGIN
                    UPDATE system_config SET updated_at = CURRENT_TIMESTAMP WHERE key = NEW.key;
                END""",
        ]

        for query in queries:
            try:
                await self.db.execute(query)
            except Exception as e:
                print(f"执行SQL失败: {e}")
                continue

        await self.db.commit()

        # 添加新字段（如果不存在）
        alter_queries = [
            "ALTER TABLE traders ADD COLUMN system_prompt_template TEXT DEFAULT 'default'",  # 系统提示词模板名称
            "ALTER TABLE ai_models ADD COLUMN custom_api_url TEXT DEFAULT ''",              # 自定义API地址
            "ALTER TABLE ai_models ADD COLUMN custom_model_name TEXT DEFAULT ''",           # 自定义模型名称
        ]

        for query in alter_queries:
            try:
                await self.db.execute(query)
            except Exception:
                # 忽略已存在字段的错误
                pass

        await self.db.commit()

    async def init_default_data(self):
        """初始化默认数据"""
        # 初始化AI模型（使用default用户）
        ai_models = [
            {"id": "deepseek", "name": "DeepSeek", "provider": "deepseek"},
            {"id": "qwen", "name": "Qwen", "provider": "qwen"},
            {"id": "openrouter", "name": "OpenRouter", "provider": "openrouter"},
        ]

        for model in ai_models:
            await self.db.execute(
                """INSERT OR IGNORE INTO ai_models (id, user_id, name, provider, enabled)
                   VALUES (?, 'default', ?, ?, 0)""",
                (model["id"], model["name"], model["provider"])
            )

        # 初始化交易所（使用default用户）
        exchanges = [
            {"id": "binance", "name": "Binance Futures", "type": "binance"},
            {"id": "hyperliquid", "name": "Hyperliquid", "type": "hyperliquid"},
            {"id": "aster", "name": "Aster DEX", "type": "aster"},
        ]

        for exchange in exchanges:
            await self.db.execute(
                """INSERT OR IGNORE INTO exchanges (id, user_id, name, type, enabled)
                   VALUES (?, 'default', ?, ?, 0)""",
                (exchange["id"], exchange["name"], exchange["type"])
            )

        # 初始化系统配置
        default_configs = {
            "api_server_port": "8080",
            "use_default_coins": "true",
            "default_coins": '["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","HYPEUSDT"]',
            "coin_pool_api_url": "",
            "oi_top_api_url": "",
            "max_daily_loss": "0",
            "max_drawdown": "0",
            "stop_trading_minutes": "0",
            "btc_eth_leverage": "5",
            "altcoin_leverage": "5",
            "admin_mode": "false",
            "jwt_secret": secrets.token_urlsafe(32),
        }

        for key, value in default_configs.items():
            await self.db.execute(
                """INSERT OR IGNORE INTO system_config (key, value)
                   VALUES (?, ?)""",
                (key, value)
            )

        await self.db.commit()

    async def get_system_config(self, key: str) -> Optional[str]:
        """获取系统配置"""
        cursor = await self.db.execute(
            "SELECT value FROM system_config WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def set_system_config(self, key: str, value: str):
        """设置系统配置"""
        await self.db.execute(
            """INSERT OR REPLACE INTO system_config (key, value, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)""",
            (key, value)
        )
        await self.db.commit()

    async def get_traders(self, user_id: str) -> List[Dict[str, Any]]:
        """获取指定用户的所有交易员"""
        cursor = await self.db.execute(
            """SELECT id, user_id, name, ai_model_id, exchange_id, initial_balance,
                      scan_interval_minutes, is_running,
                      COALESCE(btc_eth_leverage, 5) as btc_eth_leverage,
                      COALESCE(altcoin_leverage, 5) as altcoin_leverage,
                      COALESCE(trading_symbols, '') as trading_symbols,
                      COALESCE(use_coin_pool, 0) as use_coin_pool,
                      COALESCE(use_oi_top, 0) as use_oi_top,
                      COALESCE(custom_prompt, '') as custom_prompt,
                      COALESCE(override_base_prompt, 0) as override_base_prompt,
                      COALESCE(system_prompt_template, 'default') as system_prompt_template,
                      COALESCE(is_cross_margin, 1) as is_cross_margin,
                      created_at, updated_at
               FROM traders WHERE user_id = ? ORDER BY created_at DESC""",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_all_traders(self) -> List[Dict[str, Any]]:
        """获取所有交易员（不区分用户）"""
        cursor = await self.db.execute(
            """SELECT t.*, a.name as ai_model_name, a.provider,
                      e.name as exchange_name, e.type as exchange_type
               FROM traders t
               LEFT JOIN ai_models a ON t.ai_model_id = a.id
               LEFT JOIN exchanges e ON t.exchange_id = e.id"""
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_trader(self, trader_id: str) -> Optional[Dict[str, Any]]:
        """获取单个交易员"""
        cursor = await self.db.execute(
            """SELECT t.*, a.name as ai_model_name, a.provider,
                      e.name as exchange_name, e.type as exchange_type
               FROM traders t
               LEFT JOIN ai_models a ON t.ai_model_id = a.id
               LEFT JOIN exchanges e ON t.exchange_id = e.id
               WHERE t.id = ?""",
            (trader_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def create_trader(
        self,
        trader_id: str,
        user_id: str,
        name: str,
        ai_model_id: str,
        exchange_id: str,
        initial_balance: float,
        btc_eth_leverage: int = 5,
        altcoin_leverage: int = 5,
        trading_symbols: str = "",
        system_prompt_template: str = "default",
        custom_prompt: str = "",
        override_base_prompt: bool = False,
        is_cross_margin: bool = True,
        use_coin_pool: bool = False,
        use_oi_top: bool = False,
        scan_interval_minutes: int = 3,
    ) -> str:
        """创建交易员"""
        await self.db.execute(
            """INSERT INTO traders
               (id, user_id, name, ai_model_id, exchange_id, initial_balance,
                scan_interval_minutes, is_running, btc_eth_leverage, altcoin_leverage,
                trading_symbols, use_coin_pool, use_oi_top, custom_prompt,
                override_base_prompt, system_prompt_template, is_cross_margin)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trader_id,
                user_id,
                name,
                ai_model_id,
                exchange_id,
                initial_balance,
                scan_interval_minutes,
                0,  # is_running默认为False
                btc_eth_leverage,
                altcoin_leverage,
                trading_symbols,
                use_coin_pool,
                use_oi_top,
                custom_prompt,
                override_base_prompt,
                system_prompt_template,
                is_cross_margin,
            )
        )
        await self.db.commit()
        return trader_id

    async def update_trader_status(self, user_id: str, trader_id: str, is_running: bool):
        """更新交易员运行状态"""
        await self.db.execute(
            "UPDATE traders SET is_running = ? WHERE id = ? AND user_id = ?",
            (is_running, trader_id, user_id)
        )
        await self.db.commit()

    async def delete_trader(self, user_id: str, trader_id: str):
        """删除交易员"""
        await self.db.execute("DELETE FROM traders WHERE id = ? AND user_id = ?", (trader_id, user_id))
        await self.db.commit()

    async def get_ai_models(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的AI模型配置"""
        cursor = await self.db.execute(
            "SELECT * FROM ai_models WHERE user_id = ?",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_exchanges(self, user_id: str) -> List[Dict[str, Any]]:
        """获取用户的交易所配置"""
        cursor = await self.db.execute(
            "SELECT * FROM exchanges WHERE user_id = ?",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def update_ai_model(self, user_id: str, model_id: str, enabled: bool,
                             api_key: str, custom_api_url: str = "", custom_model_name: str = ""):
        """更新AI模型配置，如果不存在则创建用户特定配置"""
        provider = model_id  # id参数实际上是provider

        # 先查找用户是否已有这个provider的配置
        cursor = await self.db.execute(
            "SELECT id FROM ai_models WHERE user_id = ? AND provider = ? LIMIT 1",
            (user_id, provider)
        )
        row = await cursor.fetchone()

        if row:
            # 找到了现有配置，更新它
            await self.db.execute(
                """UPDATE ai_models SET enabled = ?, api_key = ?, custom_api_url = ?, custom_model_name = ?,
                   updated_at = datetime('now') WHERE id = ? AND user_id = ?""",
                (enabled, api_key, custom_api_url, custom_model_name, row[0], user_id)
            )
        else:
            # 没有找到现有配置，创建新的
            # 获取模型的基本信息
            cursor = await self.db.execute(
                "SELECT name FROM ai_models WHERE provider = ? LIMIT 1",
                (provider,)
            )
            name_row = await cursor.fetchone()

            if name_row:
                name = name_row[0]
            else:
                # 使用默认名称
                name_map = {
                    "deepseek": "DeepSeek AI",
                    "qwen": "Qwen AI",
                    "openrouter": "OpenRouter AI"
                }
                name = name_map.get(provider, f"{provider} AI")

            # 创建用户特定的配置
            user_model_id = f"{user_id}_{provider}"
            await self.db.execute(
                """INSERT INTO ai_models (id, user_id, name, provider, enabled, api_key, custom_api_url, custom_model_name,
                   created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                (user_model_id, user_id, name, provider, enabled, api_key, custom_api_url, custom_model_name)
            )

        await self.db.commit()

    async def update_exchange(self, user_id: str, exchange_id: str, enabled: bool, api_key: str, secret_key: str,
                             testnet: bool = False, hyperliquid_wallet_addr: str = "", aster_user: str = "",
                             aster_signer: str = "", aster_private_key: str = ""):
        """更新交易所配置，如果不存在则创建用户特定配置"""
        # 先尝试更新
        cursor = await self.db.execute(
            """UPDATE exchanges SET enabled = ?, api_key = ?, secret_key = ?, testnet = ?,
               hyperliquid_wallet_addr = ?, aster_user = ?, aster_signer = ?, aster_private_key = ?,
               updated_at = datetime('now') WHERE user_id = ? AND id = ?""",
            (enabled, api_key, secret_key, testnet, hyperliquid_wallet_addr, aster_user, aster_signer,
             aster_private_key, user_id, exchange_id)
        )

        if cursor.rowcount == 0:
            # 没有更新任何行，需要创建新记录
            # 获取交易所的基本信息
            cursor = await self.db.execute(
                "SELECT name, type FROM exchanges WHERE id = ? LIMIT 1",
                (exchange_id,)
            )
            info_row = await cursor.fetchone()

            if info_row:
                name, typ = info_row[0], info_row[1]
            else:
                # 使用默认值
                name_map = {
                    "binance": ("Binance", "cex"),
                    "hyperliquid": ("Hyperliquid", "dex"),
                    "aster": ("Aster DEX", "dex")
                }
                name, typ = name_map.get(exchange_id, (exchange_id.capitalize(), "cex"))

            # 创建新记录
            await self.db.execute(
                """INSERT INTO exchanges (id, user_id, name, type, enabled, api_key, secret_key, testnet,
                   hyperliquid_wallet_addr, aster_user, aster_signer, aster_private_key, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                (exchange_id, user_id, name, typ, enabled, api_key, secret_key, testnet,
                 hyperliquid_wallet_addr, aster_user, aster_signer, aster_private_key)
            )

        await self.db.commit()

    async def create_user_signal_source(self, user_id: str, coin_pool_url: str, oi_top_url: str):
        """创建或更新用户信号源配置"""
        await self.db.execute(
            """INSERT OR REPLACE INTO user_signal_sources (user_id, coin_pool_url, oi_top_url, updated_at)
               VALUES (?, ?, ?, datetime('now'))""",
            (user_id, coin_pool_url, oi_top_url)
        )
        await self.db.commit()

    async def get_user_signal_source(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户信号源配置"""
        cursor = await self.db.execute(
            """SELECT id, user_id, coin_pool_url, oi_top_url, created_at, updated_at
               FROM user_signal_sources WHERE user_id = ?""",
            (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None

    async def update_ai_models(self, models: List[Dict[str, Any]]):
        """更新AI模型配置"""
        # 先删除所有现有配置
        await self.db.execute("DELETE FROM ai_models")

        # 插入新配置
        for model in models:
            await self.db.execute(
                """INSERT INTO ai_models (id, user_id, name, provider, enabled, api_key)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    model['id'],
                    model.get('user_id', 'default'),
                    model['name'],
                    model['provider'],
                    model.get('enabled', False),
                    model.get('api_key', '')
                )
            )

        await self.db.commit()

    async def update_exchanges(self, exchanges: List[Dict[str, Any]]):
        """更新交易所配置"""
        # 先删除所有现有配置
        await self.db.execute("DELETE FROM exchanges")

        # 插入新配置
        for exchange in exchanges:
            await self.db.execute(
                """INSERT INTO exchanges
                   (id, user_id, name, type, enabled, api_key, secret_key,
                    testnet, hyperliquid_wallet_addr, aster_user, aster_signer, aster_private_key)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    exchange['id'],
                    exchange.get('user_id', 'default'),
                    exchange['name'],
                    exchange['type'],
                    exchange.get('enabled', False),
                    exchange.get('api_key', ''),
                    exchange.get('secret_key', ''),
                    exchange.get('testnet', False),
                    exchange.get('hyperliquid_wallet_addr', ''),
                    exchange.get('aster_user', ''),
                    exchange.get('aster_signer', ''),
                    exchange.get('aster_private_key', '')
                )
            )

        await self.db.commit()

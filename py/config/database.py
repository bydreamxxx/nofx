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
            """CREATE TABLE IF NOT EXISTS exchanges (
                id TEXT PRIMARY KEY,
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

    async def init_default_data(self):
        """初始化默认数据"""
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

    async def create_trader(self, trader_data: Dict[str, Any]) -> str:
        """创建交易员"""
        await self.db.execute(
            """INSERT INTO traders
               (id, user_id, name, ai_model_id, exchange_id,
                initial_balance, scan_interval_minutes, is_running)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trader_data['id'],
                trader_data.get('user_id', 'default'),
                trader_data['name'],
                trader_data['ai_model_id'],
                trader_data['exchange_id'],
                trader_data['initial_balance'],
                trader_data.get('scan_interval_minutes', 3),
                0
            )
        )
        await self.db.commit()
        return trader_data['id']

    async def update_trader_status(self, trader_id: str, is_running: bool):
        """更新交易员运行状态"""
        await self.db.execute(
            "UPDATE traders SET is_running = ? WHERE id = ?",
            (is_running, trader_id)
        )
        await self.db.commit()

    async def delete_trader(self, trader_id: str):
        """删除交易员"""
        await self.db.execute("DELETE FROM traders WHERE id = ?", (trader_id,))
        await self.db.commit()

    async def get_ai_models(self) -> List[Dict[str, Any]]:
        """获取所有AI模型配置"""
        cursor = await self.db.execute("SELECT * FROM ai_models")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_exchanges(self) -> List[Dict[str, Any]]:
        """获取所有交易所配置"""
        cursor = await self.db.execute("SELECT * FROM exchanges")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

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

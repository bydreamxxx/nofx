"""
配置管理模块
"""

import json
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class LeverageConfig(BaseModel):
    """杠杆配置"""
    btc_eth_leverage: int = Field(default=5, description="BTC和ETH的杠杆倍数")
    altcoin_leverage: int = Field(default=5, description="山寨币的杠杆倍数")


class TraderConfig(BaseModel):
    """单个交易员配置"""
    id: str
    name: str
    enabled: bool = True
    ai_model: str  # "qwen" or "deepseek" or "custom"

    # 交易平台选择
    exchange: str = "binance"  # "binance" or "hyperliquid" or "aster"

    # 币安配置
    binance_api_key: Optional[str] = None
    binance_secret_key: Optional[str] = None

    # Hyperliquid配置
    hyperliquid_private_key: Optional[str] = None
    hyperliquid_wallet_addr: Optional[str] = None
    hyperliquid_testnet: bool = False

    # Aster配置
    aster_user: Optional[str] = None  # Aster主钱包地址
    aster_signer: Optional[str] = None  # Aster API钱包地址
    aster_private_key: Optional[str] = None  # Aster API钱包私钥

    # AI配置
    qwen_key: Optional[str] = None
    deepseek_key: Optional[str] = None
    openrouter_key: Optional[str] = None

    # 自定义AI API配置
    custom_api_url: Optional[str] = None
    custom_api_key: Optional[str] = None
    custom_model_name: Optional[str] = None

    initial_balance: float
    scan_interval_minutes: int = 3

    @field_validator('exchange')
    @classmethod
    def validate_exchange(cls, v):
        if v not in ['binance', 'hyperliquid', 'aster']:
            raise ValueError(f'exchange must be one of: binance, hyperliquid, aster, got: {v}')
        return v

    @field_validator('ai_model')
    @classmethod
    def validate_ai_model(cls, v):
        if v not in ['qwen', 'deepseek', 'custom']:
            raise ValueError(f'ai_model must be one of: qwen, deepseek, custom, got: {v}')
        return v


class Config(BaseModel):
    """总配置"""
    admin_mode: bool = False  # 管理员模式（单用户模式）
    traders: List[TraderConfig] = []
    use_default_coins: bool = True
    default_coins: List[str] = Field(default_factory=lambda: [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
        "XRPUSDT", "DOGEUSDT", "ADAUSDT", "HYPEUSDT"
    ])
    coin_pool_api_url: str = ""
    oi_top_api_url: str = ""
    api_server_port: int = 8080
    max_daily_loss: float = 0.0
    max_drawdown: float = 0.0
    stop_trading_minutes: int = 0
    leverage: LeverageConfig = Field(default_factory=LeverageConfig)
    jwt_secret: str = ""  # JWT密钥

    def validate_config(self) -> None:
        """验证配置"""
        # 如果use_default_coins为False且没有配置coin_pool_api_url，则自动启用默认币种
        if not self.use_default_coins and not self.coin_pool_api_url:
            self.use_default_coins = True

        # 验证每个交易员的配置
        for trader in self.traders:
            if not trader.enabled:
                continue

            # 验证交易所配置
            if trader.exchange == "binance":
                if not trader.binance_api_key or not trader.binance_secret_key:
                    raise ValueError(f"Trader {trader.id}: Binance exchange requires api_key and secret_key")
            elif trader.exchange == "hyperliquid":
                if not trader.hyperliquid_private_key or not trader.hyperliquid_wallet_addr:
                    raise ValueError(f"Trader {trader.id}: Hyperliquid exchange requires private_key and wallet_addr")
            elif trader.exchange == "aster":
                if not trader.aster_user or not trader.aster_signer or not trader.aster_private_key:
                    raise ValueError(f"Trader {trader.id}: Aster exchange requires user, signer, and private_key")

            # 验证AI配置
            if trader.ai_model == "qwen" and not trader.qwen_key:
                raise ValueError(f"Trader {trader.id}: Qwen AI model requires qwen_key")
            elif trader.ai_model == "openrouter" and not trader.openrouter_key:
                raise ValueError(f"Trader {trader.id}: OpenRouter AI model requires openrouter_key")
            elif trader.ai_model == "deepseek" and not trader.deepseek_key:
                raise ValueError(f"Trader {trader.id}: DeepSeek AI model requires deepseek_key")
            elif trader.ai_model == "custom":
                if not trader.custom_api_url or not trader.custom_api_key:
                    raise ValueError(f"Trader {trader.id}: Custom AI model requires custom_api_url and custom_api_key")


def load_config(filename: str) -> Config:
    """从文件加载配置"""
    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)

    config = Config(**data)
    config.validate_config()
    return config


async def sync_config_to_database(config_path: str, database) -> bool:
    """
    从 config.json 读取配置并同步到数据库

    Args:
        config_path: config.json 文件路径
        database: Database 实例

    Returns:
        bool: 是否成功同步
    """
    from pathlib import Path
    from loguru import logger

    # 检查 config.json 是否存在
    config_file = Path(config_path)
    if not config_file.exists():
        logger.info(f"📄 {config_path} 不存在，跳过同步")
        return False

    try:
        # 加载配置（使用现有的 Config 结构体）
        logger.info(f"🔄 开始从 {config_path} 同步配置到数据库...")
        config = load_config(config_path)

        # 同步系统配置到数据库
        sync_count = 0

        # admin_mode
        await database.set_system_config("admin_mode", str(config.admin_mode).lower())
        logger.success(f"✓ 同步配置: admin_mode = {config.admin_mode}")
        sync_count += 1

        # api_server_port
        await database.set_system_config("api_server_port", str(config.api_server_port))
        logger.success(f"✓ 同步配置: api_server_port = {config.api_server_port}")
        sync_count += 1

        # use_default_coins
        await database.set_system_config("use_default_coins", str(config.use_default_coins).lower())
        logger.success(f"✓ 同步配置: use_default_coins = {config.use_default_coins}")
        sync_count += 1

        # default_coins（转换为JSON字符串）
        if config.default_coins:
            default_coins_json = json.dumps(config.default_coins)
            await database.set_system_config("default_coins", default_coins_json)
            logger.success(f"✓ 同步配置: default_coins = {default_coins_json}")
            sync_count += 1

        # coin_pool_api_url
        await database.set_system_config("coin_pool_api_url", config.coin_pool_api_url)
        logger.success(f"✓ 同步配置: coin_pool_api_url = {config.coin_pool_api_url}")
        sync_count += 1

        # oi_top_api_url
        await database.set_system_config("oi_top_api_url", config.oi_top_api_url)
        logger.success(f"✓ 同步配置: oi_top_api_url = {config.oi_top_api_url}")
        sync_count += 1

        # max_daily_loss
        await database.set_system_config("max_daily_loss", str(float(config.max_daily_loss)))
        logger.success(f"✓ 同步配置: max_daily_loss = {config.max_daily_loss}")
        sync_count += 1

        # max_drawdown
        await database.set_system_config("max_drawdown", str(float(config.max_drawdown)))
        logger.success(f"✓ 同步配置: max_drawdown = {config.max_drawdown}")
        sync_count += 1

        # stop_trading_minutes
        await database.set_system_config("stop_trading_minutes", str(int(config.stop_trading_minutes)))
        logger.success(f"✓ 同步配置: stop_trading_minutes = {config.stop_trading_minutes}")
        sync_count += 1

        # btc_eth_leverage
        if config.leverage.btc_eth_leverage > 0:
            await database.set_system_config("btc_eth_leverage", str(config.leverage.btc_eth_leverage))
            logger.success(f"✓ 同步配置: btc_eth_leverage = {config.leverage.btc_eth_leverage}")
            sync_count += 1

        # altcoin_leverage
        if config.leverage.altcoin_leverage > 0:
            await database.set_system_config("altcoin_leverage", str(config.leverage.altcoin_leverage))
            logger.success(f"✓ 同步配置: altcoin_leverage = {config.leverage.altcoin_leverage}")
            sync_count += 1

        # jwt_secret
        if config.jwt_secret:
            await database.set_system_config("jwt_secret", config.jwt_secret)
            logger.success(f"✓ 同步配置: jwt_secret = ***（已隐藏）")
            sync_count += 1

        logger.success(f"✅ config.json 同步完成，共同步 {sync_count} 项配置")
        return True

    except FileNotFoundError:
        logger.warning(f"⚠️  {config_path} 不存在")
        return False
    except Exception as e:
        logger.error(f"❌ 同步配置到数据库失败: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False

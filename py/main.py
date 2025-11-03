"""
NOFX Python 版本 - 主程序入口
"""

import asyncio
import argparse
import sys
from pathlib import Path
from loguru import logger

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import load_config, Database, sync_config_to_database
from manager import TraderManager
from api import create_app
import uvicorn
import auth


async def main():
    """主函数"""
    # 配置日志
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )

    # 解析命令行参数
    parser = argparse.ArgumentParser(description="NOFX Python 版本 - AI 加密货币自动交易系统")
    parser.add_argument(
        "--config",
        default="../config.json",
        help="配置文件路径 (默认: ../config.json)"
    )
    parser.add_argument(
        "--db",
        default="../nofx.db",
        help="数据库文件路径 (默认: ../nofx.db)"
    )
    args = parser.parse_args()

    # 打印欢迎信息
    print_banner()

    # 加载配置（目前只用于验证，实际配置从数据库读取）
    logger.info(f"📁 加载配置文件: {args.config}")
    try:
        _ = load_config(args.config)  # 验证配置文件格式
        logger.success(f"✓ 配置加载成功")
    except FileNotFoundError:
        logger.warning(f"⚠️  配置文件不存在: {args.config}")
        logger.info("💡 将使用数据库配置")
    except Exception as e:
        logger.error(f"❌ 配置加载失败: {e}")
        return

    # 连接数据库
    logger.info(f"🗄️  连接数据库: {args.db}")
    database = Database(args.db)
    try:
        await database.connect()
        logger.success("✓ 数据库连接成功")
    except Exception as e:
        logger.error(f"❌ 数据库连接失败: {e}")
        return

    # 同步 config.json 到数据库
    await sync_config_to_database(args.config, database)

    # 初始化提示词管理器
    logger.info("📝 初始化提示词管理器...")
    from decision.prompt_manager import init_prompt_manager
    try:
        await init_prompt_manager("prompts")
        logger.success("✓ 提示词管理器初始化成功")
    except Exception as e:
        logger.warning(f"⚠️  提示词管理器初始化失败: {e}")

    # 初始化认证系统
    logger.info("🔐 初始化认证系统...")
    jwt_secret = await database.get_system_config("jwt_secret")
    if not jwt_secret:
        jwt_secret = "default-secret-please-change-in-production"
        logger.warning("⚠️  未配置JWT密钥，使用默认密钥（生产环境请修改）")
    auth.set_jwt_secret(jwt_secret)

    admin_mode_str = await database.get_system_config("admin_mode")
    admin_mode = admin_mode_str != "false"
    auth.set_admin_mode(admin_mode)
    logger.success(f"✓ 认证系统初始化完成 (admin_mode={admin_mode})")

    # 初始化交易员管理器
    logger.info("🤖 初始化交易员管理器...")
    trader_manager = TraderManager()

    try:
        await trader_manager.load_traders_from_database(database)
        logger.success(f"✓ 交易员管理器初始化成功")
    except Exception as e:
        logger.error(f"❌ 交易员管理器初始化失败: {e}")
        await database.close()
        return

    # 启动所有交易员
    traders = await trader_manager.get_all_traders()
    if traders:
        try:
            # 在后台启动所有交易员
            asyncio.create_task(trader_manager.start_all())
        except Exception as e:
            logger.error(f"❌ 启动交易员失败: {e}")
    else:
        logger.warning("⚠️  没有启用的交易员，请通过数据库或Web界面配置")

    # 创建 FastAPI 应用
    logger.info("🌐 创建 API 服务器...")
    app = create_app(trader_manager, database)

    # 获取API端口配置
    api_port_str = await database.get_system_config("api_server_port")
    api_port = int(api_port_str) if api_port_str else 8080

    logger.success(f"\n{'='*60}")
    logger.success(f"🚀 NOFX Python 版本已启动")
    logger.success(f"📡 API 服务器: http://localhost:{api_port}")
    logger.success(f"🌐 Web 界面: http://localhost:3000")
    logger.success(f"{'='*60}\n")

    # 启动 uvicorn 服务器
    config_uvicorn = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=api_port,
        log_level="info"
    )
    server = uvicorn.Server(config_uvicorn)

    # 运行服务器
    try:
        await server.serve()
    except KeyboardInterrupt:
        logger.info("\n👋 收到中断信号，正在关闭...")
    finally:
        # 停止所有交易员
        logger.info("⏹ 停止所有交易员...")
        await trader_manager.stop_all()
        logger.success("✓ 所有交易员已停止")

        # 关闭数据库连接
        logger.info("📊 正在关闭数据库连接...")
        await database.close()
        logger.success("✓ 数据库连接已关闭")


def print_banner():
    """打印启动横幅"""
    banner = """
╔════════════════════════════════════════════════════════════╗
║    🐍 NOFX Python 版本 - AI 自动交易系统                   ║
║    支持 Binance, Hyperliquid, Aster DEX                    ║
║    支持 DeepSeek, Qwen, 自定义 AI 模型                     ║
╚════════════════════════════════════════════════════════════╝
"""
    print(banner)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # 抑制 KeyboardInterrupt 的 traceback
        logger.info("\n👋 程序已退出")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ 程序异常退出: {e}")
        sys.exit(1)

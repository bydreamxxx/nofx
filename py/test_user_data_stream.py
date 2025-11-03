"""
测试币安用户数据流 WebSocket
"""

import asyncio
from loguru import logger
from market.user_data_stream import UserDataStream


async def test_user_data_stream():
    """测试用户数据流"""

    # 配置 API 密钥（从环境变量或配置文件读取）
    api_key = "637kd2QwvtU5loaBn3ND4d6OtRh7uVM8nEvODAbiYmtYPwDzzG4JEqxqFyzQCRXp"
    secret_key = "axO3gMaRXY1TsziWbtEXzg3haKcOq8Q0d6dwajjF4FRDLDTlHh8b45oQsmAhhyUs"
    testnet = True

    # 创建用户数据流实例
    user_stream = UserDataStream(
        api_key=api_key,
        secret_key=secret_key,
        testnet=testnet  # 使用正式网络
    )

    # 设置回调函数（可选）
    async def on_account_update(account_data):
        logger.info(f"📊 账户更新: {account_data}")

    async def on_position_update(positions):
        logger.info(f"📈 持仓更新: {len(positions)} 个持仓")
        for pos in positions:
            logger.info(f"  {pos['symbol']}: {pos['side']} {pos['positionAmt']} @ {pos['entryPrice']}")

    async def on_order_update(order):
        logger.info(f"📋 订单更新: {order['symbol']} {order['side']} {order['status']}")

    # 注册回调
    user_stream.on_account_update = on_account_update
    user_stream.on_position_update = on_position_update
    user_stream.on_order_update = on_order_update

    try:
        # 启动用户数据流
        await user_stream.start()

        # 运行 60 秒，观察实时更新
        logger.info("🎯 用户数据流已启动，监听 60 秒...")
        await asyncio.sleep(60)

        # 获取缓存的数据
        logger.info("\n📊 缓存的数据：")

        account = user_stream.get_account_data()
        if account:
            logger.info(f"账户余额: {account['totalWalletBalance']:.2f} USDT")
            logger.info(f"可用余额: {account['availableBalance']:.2f} USDT")
            logger.info(f"未实现盈亏: {account['totalUnrealizedProfit']:.2f} USDT")

        positions = user_stream.get_positions()
        logger.info(f"持仓数量: {len(positions)}")

    except KeyboardInterrupt:
        logger.info("\n⏹  用户中断")
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
    finally:
        # 停止用户数据流
        await user_stream.stop()
        logger.info("✅ 测试完成")


async def test_with_binance_trader():
    """测试在 BinanceFuturesTrader 中使用"""
    from trader.binance_futures import BinanceFuturesTrader

    api_key = "637kd2QwvtU5loaBn3ND4d6OtRh7uVM8nEvODAbiYmtYPwDzzG4JEqxqFyzQCRXp"
    secret_key = "axO3gMaRXY1TsziWbtEXzg3haKcOq8Q0d6dwajjF4FRDLDTlHh8b45oQsmAhhyUs"
    testnet = True

    # 创建交易器
    trader = BinanceFuturesTrader(
        api_key=api_key,
        secret_key=secret_key,
        testnet=testnet
    )

    try:
        # 启动用户数据流
        await trader.initialize_user_stream()
        logger.success("✅ 用户数据流已启动")

        # 等待几秒让数据流就绪
        await asyncio.sleep(3)

        # 获取余额（自动使用 WebSocket 数据）
        balance = await trader.get_balance()
        logger.info(f"📊 余额（WebSocket）: {balance}")

        # 获取持仓（自动使用 WebSocket 数据）
        positions = await trader.get_positions()
        logger.info(f"📈 持仓（WebSocket）: {len(positions)} 个")

        # 持续监听 30 秒
        logger.info("🎯 监听 30 秒...")
        await asyncio.sleep(30)

    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
    finally:
        # 停止用户数据流
        await trader.stop_user_stream()
        logger.info("✅ 测试完成")


if __name__ == "__main__":
    import sys

    logger.info("=" * 70)
    logger.info("币安用户数据流 WebSocket 测试")
    logger.info("=" * 70)

    if len(sys.argv) > 1 and sys.argv[1] == "trader":
        # 测试在交易器中使用
        asyncio.run(test_with_binance_trader())
    else:
        # 测试独立使用
        asyncio.run(test_user_data_stream())

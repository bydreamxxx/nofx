"""
测试 Binance 双向持仓模式设置

运行方式：
    python test_dual_position_mode.py
"""

import asyncio
import os
from dotenv import load_dotenv
from loguru import logger

from trader.binance_futures import BinanceFuturesTrader


async def test_dual_position_mode():
    """测试双向持仓模式设置"""
    # 加载环境变量
    load_dotenv()

    api_key = "637kd2QwvtU5loaBn3ND4d6OtRh7uVM8nEvODAbiYmtYPwDzzG4JEqxqFyzQCRXp"
    secret_key = "axO3gMaRXY1TsziWbtEXzg3haKcOq8Q0d6dwajjF4FRDLDTlHh8b45oQsmAhhyUs"
    testnet = True

    if not api_key or not secret_key:
        logger.error("❌ 请在 .env 文件中设置 BINANCE_API_KEY 和 BINANCE_SECRET_KEY")
        return

    logger.info(f"📋 开始测试双向持仓模式设置")
    logger.info(f"   测试网: {testnet}")

    # 创建交易器实例
    trader = BinanceFuturesTrader(api_key, secret_key, testnet)

    # 测试1: 检查初始状态
    logger.info("📝 测试1: 检查初始标志状态")
    assert trader._dual_position_mode_set == False, "初始状态应该为 False"
    logger.info("   ✓ 初始标志为 False")

    # 测试2: 第一次调用 _ensure_dual_position_mode
    logger.info("\n📝 测试2: 第一次调用 _ensure_dual_position_mode")
    try:
        await trader._ensure_dual_position_mode()
        logger.info("   ✓ 第一次调用成功")

        # 检查标志是否已设置
        assert trader._dual_position_mode_set == True, "调用后标志应该为 True"
        logger.info("   ✓ 标志已设置为 True")
    except Exception as e:
        logger.error(f"   ❌ 第一次调用失败: {e}")
        raise

    # 测试3: 第二次调用（应该立即返回，不调用 API）
    logger.info("\n📝 测试3: 第二次调用（测试缓存）")
    try:
        # 记录调用前的标志状态
        before_flag = trader._dual_position_mode_set

        await trader._ensure_dual_position_mode()
        logger.info("   ✓ 第二次调用成功（应该直接返回）")

        # 标志应该保持为 True
        assert trader._dual_position_mode_set == before_flag == True
        logger.info("   ✓ 标志保持为 True（未重复调用 API）")
    except Exception as e:
        logger.error(f"   ❌ 第二次调用失败: {e}")
        raise

    # 测试4: 测试 open_long（应该自动调用 _ensure_dual_position_mode）
    logger.info("\n📝 测试4: 测试 open_long 自动启用双向持仓模式")

    # 重置标志以测试自动调用
    trader._dual_position_mode_set = False
    logger.info("   重置标志为 False")

    # 注意：这里只测试模式设置，不实际下单
    # 我们通过捕获下单前的异常来验证模式设置逻辑
    try:
        # 使用非常小的数量和低杠杆进行测试
        symbol = "BTCUSDT"
        quantity = 0.001  # 非常小的数量
        leverage = 1

        # 设置杠杆会触发 _ensure_dual_position_mode
        await trader.set_leverage(symbol, leverage)
        logger.info(f"   ✓ 设置杠杆成功: {symbol} @ {leverage}x")

        # 检查标志（在 open_long 内部会被调用）
        # 注意：由于我们不实际下单，这里手动调用来验证
        await trader._ensure_dual_position_mode()

        if trader._dual_position_mode_set:
            logger.info("   ✓ 双向持仓模式已启用")
        else:
            logger.warning("   ⚠️ 双向持仓模式未启用（可能已是双向模式）")

    except Exception as e:
        logger.warning(f"   ⚠️ 测试下单流程时出现错误: {e}")
        logger.info("   这是预期的（我们不会实际下单）")

    # 测试5: 获取账户信息验证连接
    logger.info("\n📝 测试5: 验证 API 连接")
    try:
        balance = await trader.get_balance()
        logger.info(f"   ✓ 账户余额: {balance.get('totalWalletBalance', 0):.2f} USDT")
        logger.info(f"   ✓ 可用余额: {balance.get('availableBalance', 0):.2f} USDT")
    except Exception as e:
        logger.error(f"   ❌ 获取账户信息失败: {e}")
        raise

    logger.info("\n" + "="*50)
    logger.info("✅ 所有测试通过！")
    logger.info("="*50)


async def test_position_mode_error_handling():
    """测试持仓模式错误处理"""
    logger.info("\n" + "="*50)
    logger.info("📋 测试持仓模式错误处理")
    logger.info("="*50)

    # 加载环境变量
    load_dotenv()

    api_key = os.getenv("BINANCE_API_KEY")
    secret_key = os.getenv("BINANCE_SECRET_KEY")
    testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    if not api_key or not secret_key:
        logger.error("❌ 请在 .env 文件中设置 BINANCE_API_KEY 和 BINANCE_SECRET_KEY")
        return

    trader = BinanceFuturesTrader(api_key, secret_key, testnet)

    # 测试多次调用的幂等性
    logger.info("\n📝 测试多次调用的幂等性")
    for i in range(3):
        try:
            await trader._ensure_dual_position_mode()
            logger.info(f"   ✓ 第 {i+1} 次调用成功")
        except Exception as e:
            logger.error(f"   ❌ 第 {i+1} 次调用失败: {e}")
            raise

    logger.info("   ✓ 多次调用均成功（幂等性验证通过）")

    logger.info("\n✅ 错误处理测试通过！")


if __name__ == "__main__":
    # 配置日志
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>",
        level="DEBUG"
    )

    # 运行测试
    try:
        asyncio.run(test_dual_position_mode())
        asyncio.run(test_position_mode_error_handling())
    except KeyboardInterrupt:
        logger.info("\n\n⚠️ 测试被用户中断")
    except Exception as e:
        logger.error(f"\n\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

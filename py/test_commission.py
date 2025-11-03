"""
测试币安期货手续费查询
"""

import asyncio
from loguru import logger
from trader.binance_futures import BinanceFuturesTrader


async def test_commission():
    """测试手续费查询"""

    # 配置 API 密钥
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
        logger.info("=" * 70)
        logger.info("币安期货手续费查询测试")
        logger.info("=" * 70)

        # 1. 查询单个币种的手续费率
        logger.info("\n📊 1. 查询 BTCUSDT 手续费率")
        btc_rate = await trader.get_commission_rate("BTCUSDT")
        logger.info(f"  Maker 费率: {btc_rate['makerCommissionRate']*100:.4f}%")
        logger.info(f"  Taker 费率: {btc_rate['takerCommissionRate']*100:.4f}%")

        # 2. 计算持仓手续费示例
        logger.info("\n💰 2. 计算持仓手续费示例")
        logger.info("  假设持仓: 0.1 BTC @ $50,000")

        fee_info = await trader.calculate_position_fee(
            symbol="BTCUSDT",
            quantity=0.1,
            entry_price=50000.0
        )

        logger.info(f"  持仓价值: ${fee_info['position_value_usdt']:.2f} USDT")
        logger.info(f"  开仓手续费: ${fee_info['estimated_open_fee_usdt']:.2f} USDT")
        logger.info(f"  平仓手续费: ${fee_info['estimated_close_fee_usdt']:.2f} USDT")
        logger.info(f"  往返手续费: ${fee_info['total_round_trip_fee_usdt']:.2f} USDT")

        # 3. 查询当前所有持仓的手续费
        logger.info("\n📈 3. 查询当前所有持仓的手续费")

        positions = await trader.get_positions()
        if len(positions) > 0:
            commission_info = await trader.get_account_commission_info()

            logger.info(f"  总持仓数: {commission_info['total_positions']}")
            logger.info(f"  总持仓价值: ${commission_info['total_position_value_usdt']:.2f} USDT")
            logger.info(f"  总往返手续费: ${commission_info['total_estimated_round_trip_fees_usdt']:.2f} USDT")

            logger.info("\n  各持仓详情:")
            for pos_fee in commission_info['positions']:
                logger.info(
                    f"    {pos_fee['symbol']:12} {pos_fee['side']:5} "
                    f"价值: ${pos_fee['position_value']:.2f} "
                    f"开仓费: ${pos_fee['open_fee']:.2f} "
                    f"平仓费: ${pos_fee['close_fee']:.2f} "
                    f"往返费: ${pos_fee['round_trip_fee']:.2f}"
                )
        else:
            logger.info("  当前无持仓")

        # 4. 费率等级说明
        logger.info("\n📚 4. 币安期货费率等级说明")
        logger.info("  VIP 0:  Maker 0.0200%, Taker 0.0400%")
        logger.info("  VIP 1:  Maker 0.0160%, Taker 0.0400%")
        logger.info("  VIP 2:  Maker 0.0140%, Taker 0.0350%")
        logger.info("  VIP 3:  Maker 0.0120%, Taker 0.0320%")
        logger.info("  ...")

        logger.info("\n💡 提示:")
        logger.info("  • Maker：挂单（限价单）手续费")
        logger.info("  • Taker：吃单（市价单）手续费")
        logger.info("  • 本系统使用市价单，按 Taker 费率计算")
        logger.info("  • 持有 BNB 可享受手续费折扣（减免 10%）")

    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_commission())

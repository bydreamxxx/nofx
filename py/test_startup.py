#!/usr/bin/env python3
"""测试启动脚本"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import Database, sync_config_to_database

async def test():
    print("=" * 60)
    print("测试配置同步功能")
    print("=" * 60)

    # 连接数据库
    database = Database("../nofx.db")
    await database.connect()
    print("✓ 数据库连接成功")

    # 同步配置
    success = await sync_config_to_database("../config.json", database)
    print(f"\n同步结果: {'✅ 成功' if success else '❌ 失败'}")

    # 读取几个配置验证
    admin_mode = await database.get_system_config("admin_mode")
    api_port = await database.get_system_config("api_server_port")
    btc_lev = await database.get_system_config("btc_eth_leverage")

    print("\n验证配置:")
    print(f"  admin_mode: {admin_mode}")
    print(f"  api_server_port: {api_port}")
    print(f"  btc_eth_leverage: {btc_lev}")

    # 关闭
    await database.close()
    print("\n✓ 测试完成")

if __name__ == "__main__":
    asyncio.run(test())

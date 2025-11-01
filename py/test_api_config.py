#!/usr/bin/env python3
"""测试 /api/config 端点"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import Database, sync_config_to_database
from manager import TraderManager
from api import create_app
from fastapi.testclient import TestClient


async def test():
    print("=" * 60)
    print("测试 /api/config 端点")
    print("=" * 60)

    # 连接数据库
    database = Database("../nofx.db")
    await database.connect()
    print("✓ 数据库连接成功")

    # 同步配置
    await sync_config_to_database("../config.json", database)

    # 创建应用
    trader_manager = TraderManager()
    app = create_app(trader_manager, database)

    # 创建测试客户端
    client = TestClient(app)

    # 测试 /api/config
    print("\n📡 请求 GET /api/config")
    response = client.get("/api/config")

    print(f"状态码: {response.status_code}")
    print(f"响应:\n{response.json()}")

    # 验证
    data = response.json()
    assert "admin_mode" in data, "缺少 admin_mode 字段"
    assert "default_coins" in data, "缺少 default_coins 字段"
    assert "btc_eth_leverage" in data, "缺少 btc_eth_leverage 字段"
    assert "altcoin_leverage" in data, "缺少 altcoin_leverage 字段"

    print("\n✅ 测试通过！")

    # 关闭
    await database.close()


if __name__ == "__main__":
    asyncio.run(test())

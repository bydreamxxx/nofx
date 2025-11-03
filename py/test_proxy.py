"""
测试 HTTP 代理配置功能
"""

import asyncio
from utils.http_config import set_http_proxy, get_http_proxy


async def test_proxy():
    """测试代理配置"""

    # 初始状态
    print("1. 初始状态:")
    print(f"   Proxy: {get_http_proxy()}")

    # 设置代理
    print("\n2. 设置代理: http://127.0.0.1:7897")
    set_http_proxy("http://127.0.0.1:7897")
    print(f"   Proxy: {get_http_proxy()}")

    # 清空代理
    print("\n3. 清空代理:")
    set_http_proxy("")
    print(f"   Proxy: {get_http_proxy()}")

    # 再次设置
    print("\n4. 再次设置代理: http://proxy.example.com:8080")
    set_http_proxy("http://proxy.example.com:8080")
    print(f"   Proxy: {get_http_proxy()}")

    print("\n✅ 测试完成")


if __name__ == "__main__":
    asyncio.run(test_proxy())

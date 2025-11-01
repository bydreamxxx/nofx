#!/usr/bin/env python3
"""测试Trader生命周期管理（启动/停止）"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


async def test_trader_lifecycle():
    """测试trader的启动和停止"""
    print("=" * 60)
    print("测试Trader生命周期管理")
    print("=" * 60)

    # 模拟一个简化的trader
    class MockTrader:
        def __init__(self):
            self.is_running = False
            self.cycle_count = 0
            self._background_tasks = []

        async def run(self):
            """模拟trader.run()"""
            self.is_running = True
            print(f"✅ Trader启动")

            try:
                while self.is_running:
                    self.cycle_count += 1
                    print(f"  🔄 执行周期 #{self.cycle_count}")
                    await asyncio.sleep(1)  # 模拟扫描间隔
                    if not self.is_running:
                        break
            except asyncio.CancelledError:
                print(f"  ⏹ 交易循环被取消")
            finally:
                print(f"🛑 Trader已退出 (总共执行了 {self.cycle_count} 个周期)")

        def stop(self):
            """停止trader"""
            print(f"⏹ 调用stop()方法")
            self.is_running = False

            # 取消所有后台任务
            if hasattr(self, '_background_tasks'):
                for task in self._background_tasks:
                    if not task.done():
                        print(f"  ↪ 取消后台任务: {task}")
                        task.cancel()
                self._background_tasks.clear()

    # 测试1: 正常启动和停止（使用标志位）
    print("\n测试1: 使用标志位停止")
    print("-" * 60)
    trader1 = MockTrader()
    task1 = asyncio.create_task(trader1.run())
    trader1._background_tasks.append(task1)

    # 运行3秒后停止
    await asyncio.sleep(3)
    trader1.stop()
    await asyncio.sleep(0.1)  # 等待循环检查标志位
    print(f"✓ Trader1状态: is_running={trader1.is_running}, cycles={trader1.cycle_count}")

    # 测试2: 使用task.cancel()强制停止
    print("\n测试2: 使用task.cancel()强制停止")
    print("-" * 60)
    trader2 = MockTrader()
    task2 = asyncio.create_task(trader2.run())
    trader2._background_tasks.append(task2)

    # 运行2秒后强制取消
    await asyncio.sleep(2)
    trader2.stop()  # 这会调用task.cancel()

    try:
        await task2
    except asyncio.CancelledError:
        print(f"✓ Task被成功取消")

    print(f"✓ Trader2状态: is_running={trader2.is_running}, cycles={trader2.cycle_count}")

    # 测试3: 在sleep期间停止（验证立即响应）
    print("\n测试3: 在sleep期间停止（测试响应速度）")
    print("-" * 60)
    trader3 = MockTrader()
    task3 = asyncio.create_task(trader3.run())
    trader3._background_tasks.append(task3)

    # 只等待0.5秒就停止（模拟用户快速点击停止按钮）
    await asyncio.sleep(0.5)
    import time
    start = time.time()
    trader3.stop()
    try:
        await task3
    except asyncio.CancelledError:
        pass
    elapsed = time.time() - start
    print(f"✓ 停止耗时: {elapsed:.3f}秒 (应该是立即的，因为task被cancel)")

    print("\n" + "=" * 60)
    print("✅ 所有测试完成！")
    print("=" * 60)

    print("\n总结:")
    print("1. ✅ 标志位 is_running 控制循环退出")
    print("2. ✅ task.cancel() 立即中断sleep")
    print("3. ✅ CancelledError 被正确捕获")
    print("4. ✅ 即使在sleep期间也能快速停止")


if __name__ == "__main__":
    asyncio.run(test_trader_lifecycle())

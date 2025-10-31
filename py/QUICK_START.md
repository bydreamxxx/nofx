# 🚀 NOFX Python 版本 - 快速开始

## 一键测试

```bash
# 1. 安装依赖
cd py
pip install -r requirements.txt

# 2. 运行（使用 Go 版本的配置和数据库）
python main.py --config ../config.json --db ../nofx.db
```

## 当前可用功能

### ✅ 已实现
- 配置文件加载和验证
- SQLite 数据库管理
- AI 客户端（DeepSeek, Qwen, 自定义）
- 交易器接口定义

### 🚧 待实现（可参考 Go 版本）
查看 `PROJECT_STATUS.md` 了解详细进度

## 开发快速指南

### 1. 实现 Binance 交易器

创建 `trader/binance_futures.py`：

```python
from binance.client import Client as BinanceClient
from .interface import Trader
from typing import Dict, List, Any

class BinanceFuturesTrader(Trader):
    def __init__(self, api_key: str, secret_key: str):
        self.client = BinanceClient(api_key, secret_key)
        # 设置为期货API
        self.client.FUTURES_URL = 'https://fapi.binance.com'

    async def get_balance(self) -> Dict[str, Any]:
        account = self.client.futures_account()
        return {
            'total_balance': float(account['totalWalletBalance']),
            'available_balance': float(account['availableBalance']),
        }

    # TODO: 实现其他方法...
```

### 2. 测试 AI 客户端

```python
import asyncio
from mcp import Client, Provider

async def test_ai():
    client = Client()
    client.set_deepseek_api_key("your-api-key")

    response = await client.call_with_messages(
        system_prompt="You are a trading assistant.",
        user_prompt="Analyze BTC market trend."
    )
    print(response)

asyncio.run(test_ai())
```

### 3. 测试数据库

```python
import asyncio
from config import Database

async def test_db():
    db = Database("test.db")
    await db.connect()

    # 获取所有交易员
    traders = await db.get_all_traders()
    print(f"Found {len(traders)} traders")

    await db.close()

asyncio.run(test_db())
```

## 项目结构

```
py/
├── config/          # ✅ 配置和数据库
│   ├── config.py
│   └── database.py
├── mcp/             # ✅ AI 客户端
│   └── client.py
├── trader/          # ✅ 交易器接口（待实现）
│   └── interface.py
├── market/          # ⏳ 市场数据（待实现）
├── decision/        # ⏳ 决策引擎（待实现）
├── logger/          # ⏳ 日志记录（待实现）
├── manager/         # ⏳ 交易员管理（待实现）
├── api/             # ⏳ REST API（待实现）
└── main.py          # ✅ 主程序
```

## 与 Go 版本对应关系

| Go 文件 | Python 文件 | 状态 |
|---------|------------|------|
| config/config.go | config/config.py | ✅ 完成 |
| config/database.go | config/database.py | ✅ 完成 |
| mcp/client.go | mcp/client.py | ✅ 完成 |
| trader/interface.go | trader/interface.py | ✅ 完成 |
| trader/binance_futures.go | trader/binance_futures.py | ⏳ 待开发 |
| trader/auto_trader.go | trader/auto_trader.py | ⏳ 待开发 |
| market/data.go | market/data.py | ⏳ 待开发 |
| decision/engine.go | decision/engine.py | ⏳ 待开发 |
| logger/decision_logger.go | logger/decision_logger.py | ⏳ 待开发 |
| manager/trader_manager.go | manager/trader_manager.py | ⏳ 待开发 |
| api/server.go | api/server.py | ⏳ 待开发 |

## 下一步

1. **参考 Go 代码**：查看对应的 `.go` 文件了解逻辑
2. **选择模块**：从 Binance 交易器开始是个好选择
3. **编写代码**：使用异步、类型提示和 Pydantic
4. **测试**：确保功能正确
5. **集成**：与其他模块协同工作

## 常见问题

### Q: 如何运行？
A: 当前只是框架，需要实现具体模块后才能完整运行

### Q: 可以和 Go 版本一起运行吗？
A: 不建议，它们共享数据库。选择其中一个运行即可

### Q: 如何贡献代码？
A: 参考 `PROJECT_STATUS.md` 选择一个待开发模块，实现后提交 PR

### Q: 性能如何？
A: Python 版本会稍慢于 Go，但对于交易系统来说已经足够

## 资源

- 📖 完整指南：`SETUP_GUIDE.md`
- 📊 项目状态：`PROJECT_STATUS.md`
- 🔧 Go 架构文档：`../CLAUDE.md`
- 💬 社区：https://t.me/nofx_dev_community

---

**开始开发**: 选择一个模块，参考对应的 Go 代码，开始编写 Python 实现吧！

# NOFX Python 版本 - 安装和使用指南

## 🚀 快速开始

### 1. 安装依赖

#### 安装 TA-Lib（必需）

**macOS**:
```bash
brew install ta-lib
```

**Ubuntu/Debian**:
```bash
sudo apt-get install libta-lib0-dev
```

**Windows**:
1. 下载预编译的 whl 文件：https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib
2. 安装：`pip install TA_Lib‑0.4.XX‑cpXX‑cpXXm‑win_amd64.whl`

#### 安装 Python 依赖

```bash
cd py
pip install -r requirements.txt
```

### 2. 运行

```bash
# 方式1: 使用 Python 版本（独立运行）
cd py
python main.py

# 方式2: 使用共享的 Go 配置和数据库
cd py
python main.py --config ../config.json --db ../nofx.db
```

## 📋 与 Go 版本的区别

### 相同点
- ✅ 完全相同的功能
- ✅ 共享同一个数据库
- ✅ 兼容的配置文件
- ✅ 相同的 API 接口

### 不同点

| 特性 | Go 版本 | Python 版本 |
|------|---------|------------|
| 启动速度 | 更快（编译型） | 较慢（解释型） |
| 内存占用 | 较小 | 较大 |
| 并发模型 | Goroutines | asyncio |
| Web 框架 | Gin | FastAPI |
| 开发效率 | 中等 | 更高 |
| 生态丰富度 | 简洁 | 非常丰富 |

## 🔧 目前实现的模块

### ✅ 已完成
- [x] 配置管理 (config/)
- [x] 数据库管理 (config/database.py)
- [x] AI 客户端 (mcp/)
- [x] 交易器接口 (trader/interface.py)
- [x] 项目基础结构

### 🚧 待完成（可参考 Go 版本实现）
- [ ] Binance Futures 实现 (trader/binance_futures.py)
- [ ] Hyperliquid 实现 (trader/hyperliquid_trader.py)
- [ ] Aster DEX 实现 (trader/aster_trader.py)
- [ ] 自动交易控制器 (trader/auto_trader.py)
- [ ] 市场数据获取 (market/data.py)
- [ ] AI 决策引擎 (decision/engine.py)
- [ ] 决策日志记录 (logger/decision_logger.py)
- [ ] 交易员管理器 (manager/trader_manager.py)
- [ ] REST API 服务器 (api/server.py)
- [ ] 认证系统 (auth/auth.py)
- [ ] 币种池管理 (pool/coin_pool.py)

## 💡 开发建议

### 如何继续开发

1. **参考 Go 代码**：每个 Python 模块都对应一个 Go 模块
2. **使用类型提示**：利用 Pydantic 和 Python typing 保证类型安全
3. **异步优先**：所有 I/O 操作使用 async/await
4. **测试驱动**：为每个模块编写单元测试

### 推荐的开发顺序

```
1. trader/binance_futures.py  （实现 Binance 交易）
   ↓
2. market/data.py            （获取市场数据）
   ↓
3. decision/engine.py        （AI 决策引擎）
   ↓
4. logger/decision_logger.py （记录决策和性能）
   ↓
5. trader/auto_trader.py     （自动交易主控制）
   ↓
6. manager/trader_manager.py （管理多个交易员）
   ↓
7. api/server.py             （FastAPI 服务器）
   ↓
8. auth/auth.py              （JWT 认证）
```

### 示例：实现 Binance Futures Trader

参考 `../trader/binance_futures.go`，创建 `trader/binance_futures.py`:

```python
from binance.client import Client as BinanceClient
from .interface import Trader

class BinanceFuturesTrader(Trader):
    def __init__(self, api_key: str, secret_key: str):
        self.client = BinanceClient(api_key, secret_key)
        self.client.FUTURES_URL = 'https://fapi.binance.com'

    async def get_balance(self) -> Dict[str, Any]:
        # 实现获取余额逻辑
        account = self.client.futures_account()
        return {
            'total_balance': float(account['totalWalletBalance']),
            'available_balance': float(account['availableBalance']),
            # ... 其他字段
        }

    # 实现其他方法...
```

## 🧪 测试

```bash
# 运行测试
cd py
pytest tests/

# 运行特定测试
pytest tests/test_config.py

# 带覆盖率
pytest --cov=. tests/
```

## 📚 相关资源

### Go 版本文档
- `../CLAUDE.md` - Go 版本架构文档
- `../README.md` - Go 版本使用说明

### Python 依赖文档
- [FastAPI](https://fastapi.tiangolo.com/)
- [python-binance](https://python-binance.readthedocs.io/)
- [Pydantic](https://docs.pydantic.dev/)
- [TA-Lib Python](https://mrjbq7.github.io/ta-lib/)

## ⚠️ 注意事项

1. **数据库兼容性**：Python 和 Go 版本可以共享数据库，但不要同时运行
2. **API 密钥安全**：不要提交包含真实 API 密钥的配置文件
3. **测试环境**：建议先在测试网或小资金账户测试
4. **日志文件**：决策日志会占用磁盘空间，定期清理

## 🤝 贡献

欢迎提交 PR 完善 Python 版本！

### 开发规范
- 使用 `black` 格式化代码
- 使用 `mypy` 进行类型检查
- 遵循 PEP 8 编码规范
- 为新功能编写单元测试

## 📞 支持

- GitHub Issues: https://github.com/tinkle-community/nofx/issues
- Telegram: https://t.me/nofx_dev_community

---

**最后更新**: 2025-11-01

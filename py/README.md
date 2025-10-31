# NOFX Python Version

这是 NOFX 加密货币自动交易系统的 Python 实现版本，与 Go 版本功能完全一致。

## 🚀 快速启动

### 方式一：使用启动脚本（推荐）

**macOS/Linux**:
```bash
./run.sh
```

**Windows**:
```bash
run.bat
```

### 方式二：手动启动

```bash
# 1. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动系统（需要先有数据库文件）
python main.py --db ../nofx.db
```

### 访问 Web 界面

启动成功后，打开浏览器访问 `http://localhost:3000`

---

## 为什么有 Python 版本？

- 🐍 **更易于扩展**：Python 生态系统丰富，集成第三方库更方便
- 📊 **数据分析友好**：pandas、numpy 等数据处理库支持更好
- 🤖 **AI/ML 集成**：更容易集成机器学习模型和量化策略
- 🔧 **快速原型**：Python 开发速度快，适合快速迭代

## 支持的交易所

NOFX Python 版本现已支持 **4 个交易所**：

| 交易所 | 类型 | 认证方式 | 状态 |
|--------|------|----------|------|
| **Binance Futures** | CEX | API Key + Secret | ✅ 完整支持 |
| **Hyperliquid** | DEX | 以太坊私钥 | ✅ 完整支持 |
| **Aster DEX** | DEX | 以太坊私钥 | ✅ 完整支持 |
| **OKX** | CEX | API Key + Secret + Passphrase | ✅ 完整支持 |

详细配置和使用说明请参考 [EXCHANGES.md](EXCHANGES.md)

## 项目结构

```
py/
├── config/           # 配置管理
│   ├── __init__.py
│   ├── config.py     # 配置加载
│   └── database.py   # SQLite 数据库管理
├── trader/           # 交易所接口
│   ├── __init__.py
│   ├── interface.py  # 交易器抽象基类
│   ├── binance_futures.py   # 币安合约
│   ├── hyperliquid_trader.py  # Hyperliquid DEX
│   ├── aster_trader.py      # Aster DEX
│   ├── okx_trader.py        # OKX 交易所
│   └── auto_trader.py  # 自动交易主控制器
├── mcp/              # AI 客户端
│   ├── __init__.py
│   └── client.py     # DeepSeek/Qwen/自定义 AI
├── decision/         # AI 决策引擎
│   ├── __init__.py
│   └── engine.py
├── market/           # 市场数据
│   ├── __init__.py
│   └── data.py       # K线、技术指标
├── logger/           # 日志记录
│   ├── __init__.py
│   └── decision_logger.py
├── manager/          # 交易员管理
│   ├── __init__.py
│   └── trader_manager.py
├── api/              # REST API
│   ├── __init__.py
│   └── server.py     # FastAPI 服务器
├── auth/             # 认证系统
│   ├── __init__.py
│   └── auth.py
├── pool/             # 币种池
│   ├── __init__.py
│   └── coin_pool.py
├── main.py           # 主程序入口
├── requirements.txt  # 依赖项
└── README.md         # 本文件
```

## 安装依赖

### 1. 安装 TA-Lib

**macOS**:
```bash
brew install ta-lib
```

**Ubuntu/Debian**:
```bash
sudo apt-get install libta-lib0-dev
```

### 2. 安装 Python 依赖

```bash
cd py
pip install -r requirements.txt
```

## 运行

```bash
# 从项目根目录运行
cd py
python main.py

# 或使用自定义配置
python main.py --config ../config.json
```

## 与 Go 版本的区别

| 特性 | Go 版本 | Python 版本 |
|------|---------|------------|
| 并发模型 | Goroutines + Channels | asyncio + async/await |
| Web 框架 | Gin | FastAPI |
| 类型系统 | 静态类型 | 动态类型 + Pydantic 验证 |
| 性能 | 更快 | 稍慢但足够 |
| 生态系统 | 简洁 | 丰富 |
| 技术分析库 | go-talib | TA-Lib Python bindings + pandas |

## 开发

```bash
# 格式化代码
black .

# 类型检查
mypy .

# 运行测试
pytest tests/
```

## 注意事项

- Python 版本与 Go 版本共享同一个 SQLite 数据库
- 配置文件格式完全兼容
- API 端点保持一致
- 决策日志格式相同

## 性能优化

- 使用 `uvloop` 提升 asyncio 性能
- 使用 `orjson` 加速 JSON 序列化
- 合理使用缓存减少 API 调用
- 数据库查询使用异步操作

## 许可证

MIT License - 与 Go 版本相同

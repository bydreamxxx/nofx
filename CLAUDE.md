# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此代码仓库中工作时提供指导。

## 项目概述

NOFX 是一个 AI 驱动的加密货币期货自动交易竞赛系统，支持多个交易所（Binance、Hyperliquid、Aster DEX、OKX）和多个 AI 模型（DeepSeek、Qwen 或自定义 OpenAI 兼容 API）。该系统具有通过历史性能反馈进行 AI 自我学习、多交易员竞赛模式以及专业的 React 监控仪表板等特性。

**⚠️ 重要：项目有两个完整实现**：
- **Go 版本**（主目录）：生产就绪，性能优异，静态类型安全
- **Python 版本**（`py/` 目录）：易于扩展，数据分析友好，AI/ML 集成方便

两个版本共享相同的数据库（`nofx.db`）和 Web 前端（`web/`），功能完全一致。

### 如何选择版本

**选择 Go 版本，如果你**：
- 需要最佳性能和低延迟
- 偏好静态类型和编译时检查
- 部署到生产环境
- 不需要频繁修改核心逻辑

**选择 Python 版本，如果你**：
- 需要快速原型开发和迭代
- 想要集成机器学习库（sklearn、pytorch 等）
- 需要使用 pandas 进行数据分析
- 熟悉 Python 生态系统
- 想要添加自定义指标或策略

**注意**：两个版本可以同时存在，但同时只能运行一个后端实例（共享同一个数据库）。

## 开发命令

### 后端 (Go 版本)

```bash
# 构建后端
go build -o nofx

# 运行后端（从项目根目录）
./nofx

# 使用自定义数据库路径运行
./nofx --db path/to/nofx.db

# 安装依赖
go mod download

# 运行测试
go test ./...
```

### 后端 (Python 版本)

```bash
# 创建 Conda 环境（推荐）
conda create -n nofx python=3.11
conda activate nofx

# 安装 TA-Lib (必需)
# macOS: brew install ta-lib
# Ubuntu: sudo apt-get install libta-lib0-dev

# 安装依赖
cd py
pip install -r requirements.txt

# 运行后端（需要指定数据库路径）
python main.py --db ../nofx.db

# 或使用快速启动脚本
./run.sh  # macOS/Linux
run.bat   # Windows
```

### 前端 (React + TypeScript)

```bash
# 安装依赖
cd web
npm install

# 开发服务器（运行在 3000 端口）
npm run dev

# 生产构建
npm run build

# 预览生产构建
npm run preview
```

### Docker 部署

```bash
# 启动所有服务（后端 + 前端）
docker compose up -d --build

# 查看日志
docker compose logs -f

# 停止服务
docker compose down

# 重启服务
docker compose restart
```

## 高层架构

### 系统组件

系统由三个主要层次组成：

1. **后端 (Go)** - 交易逻辑、AI 集成、市场分析和 REST API
2. **前端 (React + TypeScript)** - 实时监控仪表板，包含图表和竞赛排行榜
3. **外部服务** - 交易所 API（Binance/Hyperliquid/Aster）、AI API（DeepSeek/Qwen/自定义）、可选的币种池 API

### 核心架构模式：多交易员竞赛

系统使用**管理者-工作者模式**：
- `TraderManager` (manager/trader_manager.go) 协调多个 `AutoTrader` 实例
- 每个 `AutoTrader` (trader/auto_trader.go) 是一个独立的工作者，拥有自己的：
  - 交易所连接器（通过 `Trader` 接口）
  - AI 客户端（通过 `mcp.Client`）
  - 决策日志记录器（通过 `logger.DecisionLogger`）
  - 生命周期管理（启动/停止/暂停）

这允许多个 AI 模型同时进行交易竞赛（例如 Qwen vs DeepSeek）。

### 数据流：决策循环

核心交易循环每 3-5 分钟执行以下序列：

```
AutoTrader.Start() → [每隔 scan_interval_minutes]
  ↓
1. 获取账户余额和持仓（Trader 接口）
  ↓
2. 获取历史性能（DecisionLogger.GetPerformanceAnalysis）
  ↓
3. 构建交易上下文（decision.Context）：
   - 账户信息（权益、保证金使用率、盈亏）
   - 持仓信息及实时市场数据
   - 候选币种池（AI500 + OI Top 或默认币种）
   - 历史性能反馈（胜率、最佳/最差币种）
  ↓
4. 生成 AI 决策（decision.GetFullDecision）：
   - 构建系统提示（规则、风险限制、杠杆配置）
   - 构建用户提示（市场数据、指标、持仓）
   - 使用思维链推理调用 AI API
   - 解析 JSON 决策（开多/平多/开空/平空/持有/等待）
  ↓
5. 执行决策（AutoTrader.executeDecisions）：
   - 优先级：先平仓现有持仓，再开新仓
   - 风险检查（持仓限制、保证金使用率、重复持仓）
   - 通过交易所 API 执行（Binance/Hyperliquid/Aster）
   - 设置止损和止盈订单
  ↓
6. 记录决策并更新性能（DecisionLogger.LogDecision）：
   - 保存完整决策记录（CoT、提示词、执行结果）
   - 通过 symbol_side 匹配开平仓对（例如 "BTCUSDT_long"）
   - 计算准确的 USDT 盈亏 = 持仓价值 × 价格变化% × 杠杆
   - 更新胜率、盈亏比、夏普比率
  ↓
7. 通过 REST API 提供数据（api/server.go）
  ↓
8. 在 Web 仪表板显示（React 组件）
```

### 交易所抽象层

**Go 版本** - `Trader` 接口（trader/interface.go）：
- **Binance**：`FuturesTrader`（trader/binance_futures.go）- 使用 go-binance SDK
- **Hyperliquid**：`HyperliquidTrader`（trader/hyperliquid_trader.go）- 使用 go-hyperliquid SDK，需要以太坊私钥
- **Aster**：`AsterTrader`（trader/aster_trader.go）- Binance 兼容 API，使用 Web3 钱包认证

**Python 版本** - `Trader` 抽象基类（py/trader/interface.py）：
- **Binance**：`BinanceFuturesTrader`（py/trader/binance_futures.py）- 使用 binance-connector-python
- **Hyperliquid**：`HyperliquidTrader`（py/trader/hyperliquid_trader.py）- 使用 hyperliquid-python SDK
- **Aster**：`AsterTrader`（py/trader/aster_trader.py）- 使用 requests + eth_account
- **OKX**：`OKXTrader`（py/trader/okx_trader.py）- 使用 ccxt 库

所有交易所实现必须处理：
- 持仓管理（开多/平多/开空/平空）
- 杠杆配置
- 订单精度（从交易所信息获取 LOT_SIZE）
- 止损和止盈订单

### AI 集成架构

`mcp.Client`（mcp/client.go）支持三种 AI 提供商类型：
- **DeepSeek**：`https://api.deepseek.com/v1` 使用模型 `deepseek-chat`
- **Qwen**：`https://dashscope.aliyuncs.com/compatible-mode/v1` 使用模型如 `qwen-plus`
- **自定义**：任何 OpenAI 兼容 API（支持带 `#` 后缀的完整 URL 以跳过自动路径）

所有提供商使用相同的接口：
```go
CallWithMessages(systemPrompt, userPrompt string) (string, error)
```

AI 接收：
- **系统提示**：交易规则、风险限制、杠杆配置、JSON 输出模式
- **用户提示**：实时市场数据、技术指标、历史性能、持仓信息

AI 返回带有思维链推理的结构化 JSON。

### 自我学习反馈循环

关键特性：系统从过去的交易中学习。

**性能跟踪**（logger/decision_logger.go）：
- 存储持仓记录包含：`symbol_side`、`quantity`、`leverage`、`entry_price`、`timestamp`
- 通过 `symbol_side` 键匹配平仓操作与开仓持仓（防止多空冲突）
- 计算准确的 USDT 盈亏：`持仓价值 × 价格变化% × 杠杆`
- 汇总统计数据：胜率、盈亏比（平均盈利/平均亏损）、夏普比率

**反馈给 AI**（decision/engine.go）：
- 每次决策前，加载最近 20 条交易记录
- 生成 `PerformanceAnalysis` 包含：
  - 整体统计（总交易数、胜率、平均盈亏）
  - 每个币种的性能（最佳/最差表现者）
  - 最近的交易（最近 5 条，包含入场 → 出场 → 盈亏）
- 将此反馈注入用户提示

**AI 适应**：
- 避免重复错误（例如，连续亏损的币种）
- 强化成功模式（例如，高胜率策略）
- 根据市场条件调整交易风格

### 配置系统

`config.json` 文件控制所有系统行为（config/config.go）：

**关键配置概念**：
- **多交易员设置**：交易员配置数组，每个都有唯一 ID、名称、AI 模型、交易所凭证
- **交易员启用/禁用**：`enabled: true/false` 允许选择性激活交易员
- **杠杆配置**：`BTCETHLeverage` 和 `AltcoinLeverage` 设置最大杠杆（⚠️ Binance 子账户 ≤5x）
- **币种池模式**：
  - 默认模式：`use_default_coins: true` 使用硬编码列表（BTC、ETH、SOL 等）
  - 高级模式：`use_default_coins: false` + AI500 和 OI Top 的外部 API
- **AI 提供商**：`ai_model` 可以是 "deepseek"、"qwen" 或 "custom"，对应相应的 API 密钥

**自动默认值**：
- 如果 `use_default_coins` 为 false 但未提供 `coin_pool_api_url` → 自动启用默认币种
- 如果未指定 `exchange` → 默认为 "binance"
- 如果未指定杠杆 → 默认为 5x（对 Binance 子账户安全）

### 市场数据和技术指标

`market` 包（market/data.go）获取并计算：
- **3 分钟 K 线**：短期价格走势、EMA20、MACD、RSI(7)
- **4 小时 K 线**：长期趋势、EMA20/50、ATR、RSI(14)
- **持仓量（OI）**：市场情绪、资金费率、清算数据
- **OI Top 跟踪**：持仓量增长最快的前 20 个币种

技术指标使用 go-talib 计算（需要 TA-Lib C 库）。

### REST API 层

`api` 包（api/server.go）提供：
- **竞赛端点**：`/api/competition`、`/api/traders`（多交易员排行榜）
- **交易员特定端点**：`/api/status?trader_id=xxx`、`/api/account`、`/api/positions`、`/api/equity-history`、`/api/decisions/latest`、`/api/statistics`
- **系统端点**：`/health`、`/api/config`

所有端点使用 Gin 框架，为本地开发启用了 CORS。

### 前端架构

React 应用（web/src/）使用：
- **SWR**：数据获取，5 秒自动刷新实现实时更新
- **Recharts**：权益曲线和性能比较图表
- **Zustand**：全局状态管理（最小使用）
- **TailwindCSS**：Binance 风格的深色主题（金色 #F0B90B + 深色背景）

**关键组件**：
- `CompetitionPage.tsx`：多交易员排行榜，实时 ROI 比较
- `EquityChart.tsx`：历史账户价值趋势（USD/百分比切换）
- `ComparisonChart.tsx`：并排 AI 性能比较（基于时间戳分组）
- `AILearning.tsx`：显示历史反馈和性能分析

## Python 实现特定注意事项

### 并发模型：Asyncio 简单化原则

**关键原则**：保持简单！不要过度管理 asyncio 任务。

**✅ 正确的做法**（py/api/server.py）：
```python
# 启动交易员 - 让 asyncio 自动管理任务
async def run_trader_with_error_handling():
    try:
        await trader.run()
    except Exception as e:
        logger.error(f"交易员运行错误: {e}")

# 创建后台任务（不保存引用）
asyncio.create_task(run_trader_with_error_handling())

# 停止交易员 - 只需设置标志
def stop(self):
    self.is_running = False  # 任务会自然结束
```

**❌ 错误的做法**（过度复杂）：
```python
# 不要这样做：手动跟踪和取消任务
trader._background_tasks = []
task = asyncio.create_task(trader.run())
trader._background_tasks.append(task)  # 不需要！

def stop(self):
    for task in self._background_tasks:  # 不需要！
        task.cancel()
```

**为什么简单更好**：
- asyncio 会自动管理创建的任务
- 使用 `is_running` 标志，任务循环会自然退出
- 不需要手动取消任务，避免 CancelledError 异常处理
- 代码更清晰，维护更容易

### 数据库操作：用户隔离

**关键变更**（v3.0.0+）：所有数据库方法现在都需要 `user_id` 参数进行用户隔离。

**示例**（py/config/database.py）：
```python
# 旧版本（错误）：
async def get_ai_models(self) -> List[Dict]:
    cursor = await self.db.execute("SELECT * FROM ai_models")

# 新版本（正确）：
async def get_ai_models(self, user_id: str) -> List[Dict]:
    cursor = await self.db.execute(
        "SELECT * FROM ai_models WHERE user_id = ?",
        (user_id,)
    )
```

**所有需要 user_id 的方法**：
- `get_ai_models(user_id)` - 获取用户的 AI 模型
- `get_exchanges(user_id)` - 获取用户的交易所
- `update_ai_model(user_id, ...)` - 更新 AI 模型配置
- `update_exchange(user_id, ...)` - 更新交易所配置
- `get_user_signal_source(user_id)` - 获取用户信号源

### 认证系统

**管理员模式绕过**（py/auth/__init__.py 和 py/api/middleware.py）：
```python
# 如果启用管理员模式，所有请求使用 "admin" 用户
if auth.is_admin_mode():
    return {"user_id": "admin", "email": "admin@localhost"}

# 否则验证 JWT token
token = authorization.split(" ")[1]
user_data = auth.validate_jwt(token)
```

### 初始化默认数据

**关键修复**（v3.0.0+）：`init_default_data()` 现在会插入默认 AI 模型和交易所。

**必须包含**（py/config/database.py:161+）：
```python
async def init_default_data(self):
    # 1. 初始化 AI 模型（user_id='default'）
    ai_models = [
        {"id": "deepseek", "name": "DeepSeek", "provider": "deepseek"},
        {"id": "qwen", "name": "Qwen", "provider": "qwen"},
    ]

    # 2. 初始化交易所（user_id='default'）
    exchanges = [
        {"id": "binance", "name": "Binance Futures", "type": "binance"},
        {"id": "hyperliquid", "name": "Hyperliquid", "type": "hyperliquid"},
        {"id": "aster", "name": "Aster DEX", "type": "aster"},
    ]

    # 3. 初始化系统配置
    # ...
```

**为什么重要**：前端的 `/api/supported-models` 端点依赖这些默认数据。如果缺失，前端将显示空列表。

### FastAPI vs Gin 差异

| 特性 | Go (Gin) | Python (FastAPI) |
|------|----------|------------------|
| 路由定义 | `router.GET("/api/status", handler)` | `@app.get("/api/status")` |
| 请求参数 | `c.Query("trader_id")` | `trader_id: str = Query(...)` |
| 依赖注入 | 手动传递 | `Depends(get_current_user)` |
| 中间件 | `router.Use(middleware)` | `@app.middleware("http")` |
| 错误处理 | `c.JSON(400, gin.H{"error": msg})` | `raise HTTPException(status_code=400)` |

## 重要技术约束

### 使用 symbol_side 键跟踪持仓

**关键**：系统使用 `symbol_side` 格式（例如 "BTCUSDT_long"、"BTCUSDT_short"）跟踪持仓，而不仅仅是 `symbol`。这可以防止同时持有多空持仓时的数据冲突。

在编写持仓跟踪代码时：
- 始终使用 `fmt.Sprintf("%s_%s", symbol, side)` 作为持仓键
- 永远不要单独使用 `symbol` 作为持仓的 map 键

### 准确的盈亏计算（v2.0.2+）

**公式**：`盈亏（USDT）= 持仓价值 × 价格变化% × 杠杆`

示例：1000 USDT 持仓 × 5% 价格变动 × 20x 杠杆 = 1000 USDT 利润

**持仓记录中的必需字段**：
- `quantity`（持仓大小，以币为单位）
- `leverage`（杠杆倍数）
- `entry_price`（开仓价格）

没有这些字段，盈亏计算将不准确。

### 交易所特定的精度处理

每个交易所对数量和价格有不同的精度要求：
- **Binance**：从 `/fapi/v1/exchangeInfo` 使用 `LOT_SIZE` 和 `PRICE_FILTER`
- **Hyperliquid**：从 meta 端点自动获取精度
- **Aster**：Binance 兼容，从 `/fapi/v1/exchangeInfo` 获取

在下单前始终使用 `Trader.FormatQuantity()` 以避免精度错误。

### Binance 子账户杠杆限制

**关键约束**：Binance 子账户限制为 ≤5x 杠杆。如果 `config.json` 有更高的杠杆值并使用子账户，交易将失败，错误信息：
```
Subaccounts are restricted from using leverage greater than 5x
```

主账户可以使用：
- BTC/ETH：50x（高风险）
- 山寨币：20x（非常高风险）

**安全默认值**：在配置中设置 `btc_eth_leverage: 5` 和 `altcoin_leverage: 5`。

### AI 决策模式验证

AI 必须返回符合此模式的有效 JSON：
```json
{
  "symbol": "BTCUSDT",
  "action": "open_long|open_short|close_long|close_short|hold|wait",
  "leverage": 5,
  "position_size_usd": 100.0,
  "stop_loss": 95000.0,
  "take_profit": 105000.0,
  "confidence": 75,
  "risk_usd": 50.0,
  "reasoning": "..."
}
```

如果 AI 返回格式错误的 JSON，循环将失败并记录错误。

### 持仓时长跟踪（v2.0.2+）

系统通过在 AutoTrader 中存储 `positionFirstSeenTime` 来跟踪每个持仓持有的时间。此时间戳在提示中显示为"持仓时长2小时15分钟"，以帮助 AI 做出退出时机决策。

## 代码质量指南

- **错误处理**：始终使用 `fmt.Errorf("...: %w", err)` 包装错误并添加上下文
- **日志记录**：使用带交易员名称前缀的结构化日志消息：`log.Printf("🤖 [%s] ...", traderName)`
- **并发**：TraderManager 使用 sync.RWMutex 对 traders map 进行线程安全访问
- **JSON 序列化**：决策日志使用 `json.MarshalIndent`（人类可读），API 响应使用常规 `json.Marshal`
- **时间处理**：内部始终使用 `time.Time`，仅在存储/API 时转换为 Unix 时间戳
- **浮点精度**：所有金融计算使用 `float64`，仅在下单时格式化为交易所精度

## 常见开发任务

### 添加新交易所

**Go 版本**：
1. 在新文件中实现 `Trader` 接口（例如 `trader/new_exchange.go`）
2. 将交易所特定的配置字段添加到 `config.TraderConfig`
3. 在 `config.Validate()` 中添加验证
4. 在 `AutoTrader.NewAutoTrader()` 的 switch 语句中添加分支
5. 更新 README.md 中的新交易所文档

**Python 版本**：
1. 在新文件中实现 `Trader` 抽象基类（例如 `py/trader/new_exchange.py`）
2. 实现所有抽象方法：`open_long()`, `close_long()`, `open_short()`, `close_short()`, 等
3. 在 `py/trader/auto_trader.py` 的交易所工厂函数中添加分支
4. 在 `py/config/database.py` 的默认交易所列表中添加
5. 更新 `py/README.md` 和 `EXCHANGES.md`

### 添加新 AI 提供商

1. 在 `mcp/client.go` 中添加新的提供商常量（例如 `ProviderNewAI`）
2. 在 `mcp.Client` 中实现 `SetNewAIAPIKey()` 方法
3. 更新 `config.Validate()` 以验证新的 AI 配置
4. 在 CUSTOM_API.md 中添加示例

### 修改 AI 决策逻辑

1. 在 `decision/engine.go` → `buildSystemPrompt()` 中编辑系统提示
2. 在 `decision/engine.go` → `buildUserPrompt()` 中编辑用户提示
3. 更新注释中的 JSON 模式文档
4. 使用 `./nofx` 测试并监控日志中的解析错误

### 添加新技术指标

1. 在 `market/data.go` 中使用 go-talib 函数添加计算
2. 向 `market.Data` 结构体添加新字段
3. 在用户提示生成中包含（`decision/engine.go`）
4. 如果添加新图表类型，重新构建前端

## 测试和调试

### 后端测试（Go）

```bash
# 使用详细日志运行
LOG_LEVEL=debug ./nofx

# 使用小资金测试
# 通过 Web 界面创建交易员时设置："initial_balance": 100.0

# 运行单元测试
go test ./...

# 运行特定包的测试
go test ./trader -v
```

### 后端测试（Python）

```bash
# 激活 Conda 环境
conda activate nofx

# 使用详细日志运行
cd py
python main.py --db ../nofx.db

# 运行单元测试（如果存在）
pytest tests/ -v

# 测试特定模块
python -m pytest tests/test_trader.py -v

# 代码格式化
black .

# 类型检查
mypy . --ignore-missing-imports

# 快速测试 API 端点
python test_api_config.py
python test_trader_lifecycle.py
```

### 前端测试

```bash
cd web
npm run dev

# 访问 http://localhost:3000
# 后端必须运行在 http://localhost:8080（Go）或 http://localhost:8081（Python）
```

### 决策日志分析

决策日志存储在 `decision_logs/{trader_id}/decision_YYYYMMDD_HHMMSS_cycleN.json`

每个日志包含：
- `input_prompt`：发送给 AI 的内容
- `cot_trace`：AI 的思维链推理
- `decision_json`：解析的决策
- `execution_log`：交易执行结果
- `success`：循环是否成功完成

查看这些日志以调试 AI 决策或执行失败。

### 常见问题

**问题**："Precision is over the maximum defined for this asset"
- **原因**：数量/价格未格式化为交易所精度
- **修复**：确保在下单前调用 `Trader.FormatQuantity()`（Go）或 `format_quantity()`（Python）

**问题**：Binance 子账户杠杆错误
- **原因**：配置中杠杆 >5x 但使用子账户
- **修复**：通过 Web 界面设置杠杆 ≤5x

**问题**：AI 每个周期都返回"等待"
- **原因**：没有候选币种，或所有币种被流动性过滤
- **修复**：检查币种池配置，或使用默认币种

**问题**：前端显示"无数据"
- **原因**：后端未运行，或端口不匹配
- **修复**：验证后端在 http://localhost:8080/health（Go）或 http://localhost:8081/health（Python），检查 CORS

**Python 特定问题**：

**问题**：`ModuleNotFoundError: No module named 'bcrypt'`
- **原因**：缺少认证依赖
- **修复**：`conda run -n nofx pip install bcrypt pyjwt pyotp`

**问题**：`ModuleNotFoundError: No module named 'pandas_ta'`
- **原因**：技术指标库未安装
- **修复**：`pip install pandas_ta`（Python版本使用pandas_ta，不需要TA-Lib C库）

**问题**：`database is locked`
- **原因**：Go 和 Python 版本同时访问数据库
- **修复**：同时只运行一个后端实例

**问题**：`/api/supported-models` 返回空数组
- **原因**：数据库未初始化默认 AI 模型
- **修复**：删除 `nofx.db` 重新启动，或检查 `init_default_data()` 实现

**问题**：FastAPI 启动失败 "Address already in use"
- **原因**：端口被占用（可能 Go 版本正在运行）
- **修复**：停止其他后端实例，或修改 `.env` 中的 `API_PORT`

## 依赖项

### 后端 (Go)
- `github.com/adshao/go-binance/v2` - Binance Futures API 客户端
- `github.com/sonirico/go-hyperliquid` - Hyperliquid SDK
- `github.com/ethereum/go-ethereum` - 以太坊加密（用于 Hyperliquid/Aster）
- `github.com/gin-gonic/gin` - HTTP API 框架
- TA-Lib C 库（技术指标计算所需）

### 后端 (Python)
- `fastapi` + `uvicorn` - 异步 Web 框架和 ASGI 服务器
- `aiosqlite` - 异步 SQLite 数据库
- `binance-connector-python` - Binance API 客户端
- `hyperliquid-python-sdk` - Hyperliquid DEX SDK
- `ccxt` - 多交易所统一 API（用于 OKX）
- `eth-account` - 以太坊账户管理（用于 Aster/Hyperliquid）
- `pandas_ta` - 技术指标计算库（Python纯实现，无需C库依赖）
- `pandas` + `numpy` - 数据处理
- `bcrypt` + `pyjwt` + `pyotp` - 认证和安全
- `aiohttp` - 异步 HTTP 客户端
- `python-dateutil` - 日期时间解析

### 前端 (React)
- `react` + `react-dom` - UI 框架
- `recharts` - 图表库
- `swr` - 数据获取和自动刷新
- `tailwindcss` - 实用优先的 CSS
- `date-fns` - 日期格式化

### 技术指标库说明

**Go 版本**：使用 TA-Lib C 库（需要系统安装）

**macOS**：
```bash
brew install ta-lib
```

**Ubuntu/Debian**：
```bash
sudo apt-get install libta-lib0-dev
```

**从源码安装**（如果包管理器失败）：
```bash
wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
cd ta-lib/
./configure --prefix=/usr
make
sudo make install
```

**Python 版本**：使用 pandas_ta（纯Python实现）

✅ **优势**：
- 无需安装系统C库，避免编译问题
- 跨平台兼容性更好
- 安装简单：`pip install pandas_ta`
- 与pandas数据流无缝集成

**注意**：Python版本不需要安装TA-Lib C库，`pip install`会自动安装所有依赖。

## 版本历史注释

**v2.0.2**（2025-10-29）引入的关键修复：
- 准确的 USDT 盈亏计算（之前仅百分比）
- 使用 `symbol_side` 键跟踪持仓（防止多空冲突）
- 持仓时长跟踪（显示持仓持有时间）
- 使用 `math.Sqrt` 计算夏普比率（替换自定义实现）

v2.0.2 之前编写的代码可能有不正确的盈亏计算。

## 部署

生产部署请参见：
- Docker：`DOCKER_DEPLOY.md`（中文）或 `DOCKER_DEPLOY.en.md`（英文）
- PM2：`PM2_DEPLOYMENT.md`

安全性：
- 永远不要提交包含真实 API 密钥的 `config.json`
- 使用环境变量或密钥管理
- 将 API 密钥限制为仅交易权限（无提现）
- 在交易所 API 密钥上使用 IP 白名单
- 考虑使用交易所子账户进行隔离

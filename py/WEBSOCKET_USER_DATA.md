# 币安用户数据流 WebSocket 使用指南

## 概述

币安用户数据流（User Data Stream）是币安提供的 WebSocket 服务，可以实时推送账户、订单、持仓更新，相比 REST API 有以下优势：

- **实时性**: <10ms 延迟，立即获得账户变更通知
- **高效性**: 无需轮询，减少 API 请求次数
- **准确性**: 100% 实时数据，不会过期
- **无限制**: 不消耗 API 权重限制

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                     AutoTrader                              │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         BinanceFuturesTrader                         │  │
│  │                                                      │  │
│  │  ┌────────────────────────────────────────────────┐ │  │
│  │  │        UserDataStream (WebSocket)             │ │  │
│  │  │                                                │ │  │
│  │  │  • 连接 wss://fstream.binance.com/ws/        │ │  │
│  │  │  • 订阅账户更新 (ACCOUNT_UPDATE)              │ │  │
│  │  │  • 订阅订单更新 (ORDER_TRADE_UPDATE)          │ │  │
│  │  │  • 每 30 分钟刷新 listenKey                   │ │  │
│  │  └────────────────────────────────────────────────┘ │  │
│  │                                                      │  │
│  │  优先级：                                            │  │
│  │  1. WebSocket 实时数据 ✅                           │  │
│  │  2. REST API 缓存 (10秒)                            │  │
│  │  3. REST API 请求（fallback）                       │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 自动集成

### 1. 在 AutoTrader 中自动启动

当你创建 `AutoTrader` 并使用币安交易器时，用户数据流会自动启动：

```python
from trader.auto_trader import AutoTrader, AutoTraderConfig

# 创建配置
config = AutoTraderConfig(
    id="trader_001",
    name="AI Trader",
    exchange="binance",
    binance_api_key="your_api_key",
    binance_secret_key="your_secret_key",
    # ... 其他配置
)

# 创建 AutoTrader
trader = AutoTrader(config)

# 初始化（会自动启动用户数据流）
await trader.initialize()

# 现在所有的 get_balance() 和 get_positions() 都会使用 WebSocket 数据！
```

### 2. 数据优先级

`BinanceFuturesTrader` 的 `get_balance()` 和 `get_positions()` 方法使用以下优先级：

```python
# 1. 优先使用 WebSocket 实时数据
if self.user_stream:
    data = self.user_stream.get_account_data()
    if data:
        return data  # 实时数据，<10ms 延迟

# 2. 使用 REST API 缓存（10秒有效期）
if self.balance_cache_time:
    age = datetime.now() - self.balance_cache_time
    if age < timedelta(seconds=10):
        return self.cached_balance  # 缓存数据

# 3. 调用 REST API（最后手段）
account = await asyncio.to_thread(self.client.futures_account)
return account
```

### 3. 停止时自动清理

```python
# 停止交易员（会自动停止用户数据流）
trader.stop()
```

## 独立使用

### 1. 基础示例

```python
from market.user_data_stream import UserDataStream

# 创建用户数据流
user_stream = UserDataStream(
    api_key="your_api_key",
    secret_key="your_secret_key",
    testnet=False
)

# 启动
await user_stream.start()

# 获取实时数据
account = user_stream.get_account_data()
positions = user_stream.get_positions()

# 停止
await user_stream.stop()
```

### 2. 使用回调函数

```python
async def on_account_update(account_data):
    print(f"账户更新: {account_data}")

async def on_position_update(positions):
    print(f"持仓更新: {len(positions)} 个")

async def on_order_update(order):
    print(f"订单更新: {order['symbol']} {order['status']}")

# 注册回调
user_stream.on_account_update = on_account_update
user_stream.on_position_update = on_position_update
user_stream.on_order_update = on_order_update

await user_stream.start()
```

## 事件类型

### ACCOUNT_UPDATE（账户更新）

触发时机：
- 余额变更
- 持仓变更
- 保证金变更

推送数据：
```python
{
    "totalWalletBalance": 10000.0,  # 总余额
    "availableBalance": 8000.0,      # 可用余额
    "totalUnrealizedProfit": 100.0   # 未实现盈亏
}
```

### ORDER_TRADE_UPDATE（订单更新）

触发时机：
- 订单创建
- 订单成交
- 订单取消
- 订单失败

推送数据：
```python
{
    "orderId": 123456789,
    "symbol": "BTCUSDT",
    "side": "BUY",
    "type": "MARKET",
    "status": "FILLED",
    "price": 50000.0,
    "quantity": 0.1,
    "executedQty": 0.1,
    "avgPrice": 50000.0,
    "positionSide": "LONG"
}
```

## 测试

### 运行测试

```bash
cd py

# 测试独立使用
python test_user_data_stream.py

# 测试在交易器中使用
python test_user_data_stream.py trader
```

### 修改测试配置

编辑 `test_user_data_stream.py`，填入你的 API 密钥：

```python
api_key = "your_api_key_here"
secret_key = "your_secret_key_here"
```

## 性能对比

| 方法 | 延迟 | API 权重消耗 | 更新频率 |
|------|------|-------------|---------|
| **WebSocket** | <10ms | 0 | 实时推送 |
| REST API + 缓存 | 100-500ms | 每 10 秒消耗 1 次 | 10 秒一次 |
| REST API 直接调用 | 100-500ms | 每次消耗 1 次 | 按需 |

## 常见问题

### Q: 用户数据流会自动重连吗？

A: 是的，如果连接断开，会自动尝试重新连接并重新订阅。

### Q: listenKey 会过期吗？

A: listenKey 有效期 60 分钟，系统会每 30 分钟自动刷新，确保连接不中断。

### Q: 如果 WebSocket 失败，会影响交易吗？

A: 不会。系统会自动 fallback 到 REST API + 缓存模式，确保交易正常进行。

### Q: 可以禁用用户数据流吗？

A: 可以。在 `BinanceFuturesTrader` 初始化后设置：

```python
trader.user_stream_enabled = False
```

### Q: 支持其他交易所吗？

A: 目前仅支持币安。Hyperliquid、OKX、Aster 的 WebSocket 实现后续会添加。

## 日志示例

启动成功：
```
✓ 获取到 listenKey: Y2FycXBtMj...
✓ 用户数据流 WebSocket 连接成功
✅ 用户数据流已启动
```

接收更新：
```
✓ 账户更新: 余额=10000.00, 持仓数=3
📋 订单更新: BTCUSDT BUY FILLED
✓ 使用 WebSocket 实时账户数据
✓ 使用 WebSocket 实时持仓数据（3 个）
```

停止：
```
⏹  正在停止用户数据流...
✓ listenKey 已删除
✅ 用户数据流已停止
```

## 技术细节

### listenKey 生命周期

1. **获取 listenKey**: `POST /fapi/v1/listenKey`
2. **连接 WebSocket**: `wss://fstream.binance.com/ws/{listenKey}`
3. **保活（每 30 分钟）**: `PUT /fapi/v1/listenKey`
4. **删除（停止时）**: `DELETE /fapi/v1/listenKey`

### 数据结构

账户数据缓存：
```python
self.account_data = {
    "totalWalletBalance": float,
    "availableBalance": float,
    "totalUnrealizedProfit": float
}
```

持仓数据缓存：
```python
self.positions = [
    {
        "symbol": str,
        "positionAmt": float,
        "entryPrice": float,
        "markPrice": float,
        "unRealizedProfit": float,
        "leverage": int,
        "side": "long" | "short"
    }
]
```

## 最佳实践

1. **启动检查**: 确保 API 密钥有 "数据流" 权限
2. **错误处理**: 使用 try-except 捕获 WebSocket 异常
3. **优雅关闭**: 总是调用 `stop()` 清理资源
4. **回调简洁**: 回调函数应快速返回，避免阻塞 WebSocket 接收
5. **日志监控**: 关注 "重新连接" 日志，检测网络问题

## 总结

用户数据流 WebSocket 为 NOFX 交易系统提供了：
- ✅ **极低延迟**的账户和持仓数据
- ✅ **零 API 消耗**的实时更新
- ✅ **自动集成**到现有代码
- ✅ **自动容错**的 fallback 机制

无需修改业务逻辑，只需确保调用 `await trader.initialize()`，即可享受 WebSocket 带来的性能提升！

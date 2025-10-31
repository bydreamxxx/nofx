# 交易所支持文档

NOFX Python 版本现已支持 4 个交易所：

## 1. Binance Futures（币安合约）

**类型**：中心化交易所（CEX）
**认证方式**：API Key + Secret Key
**实现文件**：`trader/binance_futures.py`

### 配置示例

```python
config = AutoTraderConfig(
    exchange="binance",
    binance_api_key="YOUR_API_KEY",
    binance_secret_key="YOUR_SECRET_KEY",
    # ...
)
```

### 数据库配置字段

```sql
INSERT INTO exchanges (type, api_key, secret_key) VALUES (
    'binance',
    'YOUR_API_KEY',
    'YOUR_SECRET_KEY'
);
```

### 特性

- ✅ 完整的合约交易支持
- ✅ LOT_SIZE 精度自动处理
- ✅ 止损止盈订单
- ✅ 杠杆调整（注意：子账户限制 ≤5x）
- ✅ 全仓/逐仓模式

---

## 2. Hyperliquid DEX

**类型**：去中心化交易所（DEX）
**认证方式**：以太坊私钥（Web3 签名）
**实现文件**：`trader/hyperliquid_trader.py`

### 配置示例

```python
config = AutoTraderConfig(
    exchange="hyperliquid",
    hyperliquid_private_key="0x1234...",  # 以太坊私钥
    hyperliquid_wallet_address="0xABCD...",  # 钱包地址
    testnet=False,  # true=测试网, false=主网
    # ...
)
```

### 数据库配置字段

```sql
INSERT INTO exchanges (type, private_key, wallet_address, testnet) VALUES (
    'hyperliquid',
    '0x1234...',
    '0xABCD...',
    0  -- 0=主网, 1=测试网
);
```

### 特性

- ✅ Web3 签名认证（EIP-712）
- ✅ Clearinghouse 状态查询
- ✅ 市价订单（IOC 模式）
- ✅ 杠杆调整（全仓模式）
- ✅ 精度自动获取（szDecimals）
- ⚠️ 止损止盈需手动实现触发订单

### API 端点

- **主网**：`https://api.hyperliquid.xyz`
- **测试网**：`https://api.hyperliquid-testnet.xyz`

### 签名机制

使用 `eth_account` 库进行 Keccak-256 哈希签名：

```python
action_str = json.dumps(action, separators=(',', ':'))
message_hash = keccak(text=action_str)
signature = account.signHash(message_hash)
```

---

## 3. Aster DEX

**类型**：去中心化交易所（DEX）
**API 兼容**：Binance API 格式
**认证方式**：以太坊私钥（EIP-712 签名）
**实现文件**：`trader/aster_trader.py`

### 配置示例

```python
config = AutoTraderConfig(
    exchange="aster",
    aster_private_key="0x1234...",  # 以太坊私钥
    aster_wallet_address="0xABCD...",  # 钱包地址
    testnet=False,
    # ...
)
```

### 数据库配置字段

```sql
INSERT INTO exchanges (type, private_key, wallet_address, testnet) VALUES (
    'aster',
    '0x1234...',
    '0xABCD...',
    0
);
```

### 特性

- ✅ Binance API 完全兼容
- ✅ EIP-712 结构化签名
- ✅ STOP_MARKET 和 TAKE_PROFIT_MARKET 订单
- ✅ LOT_SIZE 精度处理
- ✅ 全仓模式
- ✅ 市价和限价订单

### API 端点

- **主网**：`https://api.aster.exchange`
- **测试网**：`https://testnet-api.aster.exchange`

### 签名机制

使用 EIP-712 结构化数据签名：

```python
structured_data = {
    "types": {...},
    "primaryType": "AsterRequest",
    "domain": {
        "name": "Aster DEX",
        "version": "1",
        "chainId": 1  # 主网
    },
    "message": {
        "endpoint": "/fapi/v1/order",
        "timestamp": timestamp,
        "params": "..."
    }
}
```

---

## 4. OKX

**类型**：中心化交易所（CEX）
**认证方式**：API Key + Secret + Passphrase
**实现文件**：`trader/okx_trader.py`
**使用库**：CCXT

### 配置示例

```python
config = AutoTraderConfig(
    exchange="okx",
    okx_api_key="YOUR_API_KEY",
    okx_api_secret="YOUR_SECRET",
    okx_passphrase="YOUR_PASSPHRASE",
    testnet=False,
    # ...
)
```

### 数据库配置字段

```sql
INSERT INTO exchanges (type, api_key, secret_key, passphrase, testnet) VALUES (
    'okx',
    'YOUR_API_KEY',
    'YOUR_SECRET',
    'YOUR_PASSPHRASE',
    0
);
```

### 特性

- ✅ 使用 CCXT 库简化集成
- ✅ 永续合约（swap）
- ✅ 止损止盈订单（stop 类型）
- ✅ 杠杆调整（全仓模式）
- ✅ 市场精度自动获取
- ✅ Symbol 格式自动转换（BTCUSDT ↔ BTC/USDT:USDT）

### Symbol 格式转换

- **标准格式**：`BTCUSDT`
- **OKX 格式**：`BTC/USDT:USDT`（永续合约）

系统会自动进行双向转换。

### CCXT 配置

```python
exchange = ccxt.okx({
    'apiKey': api_key,
    'secret': api_secret,
    'password': passphrase,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',  # 永续合约
    }
})
```

---

## 依赖安装

### Web3 相关（Hyperliquid + Aster）

```bash
pip install web3==6.15.1 eth-account==0.11.0 eth-keys==0.5.0 eth-utils==4.0.0
```

### CCXT（OKX）

```bash
pip install ccxt==4.2.25
```

### 完整依赖

```bash
cd py
pip install -r requirements.txt
```

---

## 数据库 Schema 更新

### exchanges 表扩展

```sql
CREATE TABLE IF NOT EXISTS exchanges (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,  -- 'binance', 'hyperliquid', 'aster', 'okx'

    -- CEX 配置（Binance, OKX）
    api_key TEXT,
    secret_key TEXT,
    passphrase TEXT,  -- OKX 专用

    -- DEX 配置（Hyperliquid, Aster）
    private_key TEXT,
    wallet_address TEXT,

    -- 通用配置
    testnet INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
```

---

## 使用示例

### 创建 Binance 交易员

```python
from trader import AutoTrader, AutoTraderConfig

config = AutoTraderConfig(
    id="trader_1",
    name="Binance Trader",
    ai_model="deepseek",
    exchange="binance",
    binance_api_key="...",
    binance_secret_key="...",
    initial_balance=1000.0,
    # ...
)

trader = AutoTrader(config)
await trader.initialize()
await trader.run()
```

### 创建 Hyperliquid 交易员

```python
config = AutoTraderConfig(
    id="trader_2",
    name="Hyperliquid Trader",
    ai_model="qwen",
    exchange="hyperliquid",
    hyperliquid_private_key="0x...",
    hyperliquid_wallet_address="0x...",
    testnet=False,
    initial_balance=500.0,
    # ...
)

trader = AutoTrader(config)
await trader.initialize()
await trader.run()
```

### 创建 OKX 交易员

```python
config = AutoTraderConfig(
    id="trader_3",
    name="OKX Trader",
    ai_model="custom",
    exchange="okx",
    okx_api_key="...",
    okx_api_secret="...",
    okx_passphrase="...",
    testnet=False,
    initial_balance=2000.0,
    # ...
)

trader = AutoTrader(config)
await trader.initialize()
await trader.run()
```

---

## 安全注意事项

### 1. API 密钥权限

- ✅ 仅授予交易权限
- ❌ 不要授予提币权限
- ✅ 使用 IP 白名单（如支持）
- ✅ 使用子账户隔离风险

### 2. 私钥管理（DEX）

- ⚠️ **永远不要**将私钥硬编码到代码中
- ✅ 使用环境变量或加密存储
- ✅ 确保数据库文件权限安全（`chmod 600 nofx.db`）
- ✅ 考虑使用独立的交易钱包

### 3. 测试网先行

- ✅ 先在测试网验证策略
- ✅ 确认签名机制正常工作
- ✅ 测试止损止盈逻辑

### 4. 资金管理

- ✅ 设置合理的初始资金量
- ✅ 使用小杠杆倍数（≤5x）
- ✅ 设置最大日亏损限制
- ✅ 定期提取利润

---

## 常见问题（FAQ）

### Q1: Hyperliquid 的止损止盈如何实现？

A: 当前实现中，`set_stop_loss_take_profit` 返回 `not_implemented`。需要手动实现触发订单（trigger orders）逻辑。可以参考 Hyperliquid 官方文档的 trigger order API。

### Q2: Aster DEX 的 chainId 如何确定？

A: 主网使用 `chainId: 1`（以太坊主网），测试网使用 `chainId: 5`（Goerli）。具体取决于 Aster 的部署链。

### Q3: OKX 的 symbol 格式问题

A: 系统会自动转换：
- 输入：`BTCUSDT`（标准格式）
- 调用 OKX API：`BTC/USDT:USDT`（CCXT 格式）
- 返回：`BTCUSDT`（标准格式）

### Q4: 如何切换测试网和主网？

A: 在配置中设置 `testnet=True` 或 `testnet=False`。所有交易所都支持此参数。

### Q5: 杠杆设置失败怎么办？

A: 某些交易所可能已有默认杠杆设置，失败时会记录警告但继续执行。如果是权限问题，请检查 API Key 权限。

---

## 性能对比

| 交易所 | 延迟 | 可靠性 | Gas费用 | 推荐场景 |
|--------|------|--------|---------|---------|
| **Binance** | 极低 | 极高 | 无 | 主流交易，高频策略 |
| **Hyperliquid** | 低 | 高 | 低 | DeFi 原生，链上透明 |
| **Aster** | 中 | 中 | 中 | Binance API 熟悉用户 |
| **OKX** | 低 | 高 | 无 | 多市场交易，丰富产品 |

---

## 下一步扩展

### 计划中的交易所

- [ ] Bybit
- [ ] Gate.io
- [ ] dYdX v4
- [ ] GMX

### 功能增强

- [ ] Hyperliquid 触发订单完整实现
- [ ] 交易所健康检查（ping/pong）
- [ ] 多交易所套利策略
- [ ] 跨交易所仓位聚合

---

## 技术支持

- **GitHub Issues**: https://github.com/yourusername/nofx/issues
- **文档**: `/py/README.md`
- **示例配置**: `/config.example.json`

**提示**：遇到问题时，请先检查日志文件 `decision_logs/{trader_id}/` 中的详细信息。

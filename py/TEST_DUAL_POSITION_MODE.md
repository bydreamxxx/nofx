# 测试 Binance 双向持仓模式

## 测试目的

验证 `BinanceFuturesTrader` 类的双向持仓模式（hedge mode）设置功能是否正常工作。

## 问题背景

在使用 Binance Futures API 时，如果账户处于单向持仓模式（one-way mode），使用 `positionSide='LONG'` 或 `positionSide='SHORT'` 参数会导致错误：

```
APIError(code=-4061): Order's position side does not match user's setting.
```

## 解决方案

在 `open_long()` 和 `open_short()` 方法中自动调用 `_ensure_dual_position_mode()` 来启用双向持仓模式。

## 测试步骤

### 1. 准备测试环境

```bash
cd py

# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入你的 Binance API 密钥
# 建议使用测试网进行测试
```

### 2. 配置 API 密钥

在 `.env` 文件中设置：

```env
BINANCE_API_KEY=your_testnet_api_key
BINANCE_SECRET_KEY=your_testnet_secret_key
BINANCE_TESTNET=true
```

**获取测试网 API 密钥**：
1. 访问 https://testnet.binancefuture.com
2. 登录并生成 API 密钥
3. 复制 API Key 和 Secret Key

### 3. 运行测试

```bash
# 确保已安装依赖
pip install python-dotenv

# 运行测试
python test_dual_position_mode.py
```

## 测试内容

测试脚本会执行以下检查：

### 测试1: 初始状态检查
- 验证 `_dual_position_mode_set` 标志初始为 `False`

### 测试2: 第一次调用 _ensure_dual_position_mode
- 调用方法启用双向持仓模式
- 验证标志设置为 `True`
- 验证 API 调用成功

### 测试3: 第二次调用（缓存测试）
- 再次调用方法
- 验证直接返回（不重复调用 API）
- 验证标志保持为 `True`

### 测试4: open_long 自动启用测试
- 重置标志
- 调用 `set_leverage()` 触发持仓模式设置
- 验证模式已启用

### 测试5: API 连接验证
- 获取账户余额
- 验证 API 连接正常

### 测试6: 错误处理测试
- 多次调用验证幂等性
- 确保不会因重复调用而出错

## 预期输出

成功的测试输出应该类似：

```
12:34:56 | 📋 开始测试双向持仓模式设置
12:34:56 |    测试网: True
12:34:56 | 📝 测试1: 检查初始标志状态
12:34:56 |    ✓ 初始标志为 False
12:34:56 |
12:34:56 | 📝 测试2: 第一次调用 _ensure_dual_position_mode
12:34:57 | ✓ 已启用双向持仓模式（hedge mode）
12:34:57 |    ✓ 第一次调用成功
12:34:57 |    ✓ 标志已设置为 True
12:34:57 |
12:34:57 | 📝 测试3: 第二次调用（测试缓存）
12:34:57 |    ✓ 第二次调用成功（应该直接返回）
12:34:57 |    ✓ 标志保持为 True（未重复调用 API）
...
12:34:58 | ✅ 所有测试通过！
```

## 可能的错误情况

### 错误1: "No need to change position side"

这个错误表示账户已经处于双向持仓模式，测试会自动处理这种情况。

**处理**：
```python
if "No need to change position side" in error_msg:
    logger.debug("✓ 账户已处于双向持仓模式")
    self._dual_position_mode_set = True
```

### 错误2: API 认证失败

如果看到 401 或 403 错误：
1. 检查 API 密钥是否正确
2. 检查 API 密钥权限（需要"仅交易"权限）
3. 如果使用测试网，确保密钥来自测试网而非主网

### 错误3: 有持仓时无法切换模式

如果账户有持仓，Binance 不允许切换持仓模式。

**解决方法**：
1. 平掉所有现有持仓
2. 然后再运行测试

## 实现原理

### _ensure_dual_position_mode() 方法

```python
async def _ensure_dual_position_mode(self) -> None:
    """确保账户启用了双向持仓模式（hedge mode）"""
    if self._dual_position_mode_set:
        return  # 已设置，直接返回

    try:
        # 调用 Binance API 启用双向持仓模式
        await asyncio.to_thread(
            self.client.futures_change_position_mode,
            dualSidePosition=True
        )
        logger.info("✓ 已启用双向持仓模式（hedge mode）")
        self._dual_position_mode_set = True
    except BinanceAPIException as e:
        error_msg = str(e)
        # 如果已经是双向持仓模式，不报错
        if "No need to change position side" in error_msg:
            logger.debug("✓ 账户已处于双向持仓模式")
            self._dual_position_mode_set = True
        else:
            logger.warning(f"⚠️ 设置双向持仓模式失败: {e}")
            # 不抛出异常，让交易继续尝试
```

### 集成到交易方法

```python
async def open_long(self, symbol: str, quantity: float, leverage: int):
    """开多仓"""
    # 确保启用双向持仓模式
    await self._ensure_dual_position_mode()

    # ... 继续执行下单逻辑 ...
```

## 注意事项

1. **测试网与主网**：测试网和主网是独立的，API 密钥不通用
2. **持仓限制**：账户有持仓时无法切换模式，需先平仓
3. **一次性设置**：双向持仓模式设置后会持久保存在账户中
4. **标志缓存**：使用 `_dual_position_mode_set` 标志避免重复 API 调用

## 相关文档

- [Binance Futures API 文档](https://binance-docs.github.io/apidocs/futures/en/)
- [Change Position Mode API](https://binance-docs.github.io/apidocs/futures/en/#change-position-mode-trade)
- [双向持仓模式说明](https://www.binance.com/en/support/faq/how-to-use-hedge-mode-on-binance-futures-360056582232)

# NOFX Python API 实现计划

## 📋 API 差异对比和实现计划

---

## 已实现 API 的差异修复

### 1. `/api/config` - 系统配置接口 ⚠️ **功能错误**

**Go 版本 (正确):**
```go
GET /api/config
返回: {
  "admin_mode": true,
  "default_coins": ["BTCUSDT", "ETHUSDT", ...],
  "btc_eth_leverage": 5,
  "altcoin_leverage": 5
}
```

**Python 版本 (错误):**
```python
GET /api/config
返回: {
  "success": true,
  "traders": [...]  # ❌ 返回的是交易员列表，不是系统配置
}
```

**需要修复：**
```python
@app.get("/api/config")
async def get_config(database: Database):
    """获取系统配置（客户端需要的配置）"""
    # 获取默认币种
    default_coins_str = await database.get_system_config("default_coins")
    default_coins = json.loads(default_coins_str) if default_coins_str else [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
        "XRPUSDT", "DOGEUSDT", "ADAUSDT", "HYPEUSDT"
    ]

    # 获取杠杆配置
    btc_eth_leverage_str = await database.get_system_config("btc_eth_leverage")
    altcoin_leverage_str = await database.get_system_config("altcoin_leverage")

    btc_eth_leverage = int(btc_eth_leverage_str) if btc_eth_leverage_str else 5
    altcoin_leverage = int(altcoin_leverage_str) if altcoin_leverage_str else 5

    # 获取 admin_mode
    admin_mode_str = await database.get_system_config("admin_mode")
    admin_mode = admin_mode_str != "false"

    return {
        "admin_mode": admin_mode,
        "default_coins": default_coins,
        "btc_eth_leverage": btc_eth_leverage,
        "altcoin_leverage": altcoin_leverage
    }
```

---

## API 实现优先级

### Phase 1: 认证系统 (P0) 🔥

#### 1.1 数据库方法实现

```python
# /Users/xxx/Source/nofx/py/auth/__init__.py (新建)

class Auth:
    """认证管理类"""

    async def create_user(self, email: str, password: str) -> str:
        """创建新用户"""
        # 1. 生成用户ID
        # 2. 密码哈希
        # 3. 插入数据库
        # 4. 返回用户ID

    async def verify_password(self, email: str, password: str) -> Optional[Dict]:
        """验证密码"""
        # 1. 通过邮箱获取用户
        # 2. 验证密码哈希
        # 3. 返回用户信息

    def generate_jwt_token(self, user_id: str, email: str) -> str:
        """生成 JWT Token"""
        # 使用 python-jose

    def verify_jwt_token(self, token: str) -> Optional[Dict]:
        """验证 JWT Token"""
```

**数据库方法需求：**
```python
# config/database.py 添加

async def create_user(self, user: Dict[str, Any]) -> str:
    """创建用户"""
    # INSERT INTO users ...

async def get_user_by_email(self, email: str) -> Optional[Dict]:
    """通过邮箱获取用户"""
    # SELECT * FROM users WHERE email = ?

async def get_user_by_id(self, user_id: str) -> Optional[Dict]:
    """通过ID获取用户"""
    # SELECT * FROM users WHERE id = ?

async def update_user_otp_verified(self, user_id: str, verified: bool) -> None:
    """更新OTP验证状态"""
    # UPDATE users SET otp_verified = ? WHERE id = ?

async def ensure_admin_user(self) -> None:
    """确保管理员用户存在"""
    # 检查是否有管理员
    # 如果没有，创建默认管理员
```

#### 1.2 认证 API 实现

```python
# api/auth_routes.py (新建)

@router.post("/api/register")
async def register(request: RegisterRequest):
    """用户注册"""
    # 1. 验证邮箱格式
    # 2. 检查邮箱是否已存在
    # 3. 创建用户（未激活）
    # 4. 生成 OTP
    # 5. 返回用户ID和OTP（测试环境）

@router.post("/api/login")
async def login(request: LoginRequest):
    """用户登录"""
    # 1. 验证邮箱和密码
    # 2. 检查 OTP 是否验证
    # 3. 生成 JWT Token
    # 4. 返回 Token

@router.post("/api/verify-otp")
async def verify_otp(request: VerifyOTPRequest):
    """验证 OTP"""
    # 1. 获取用户
    # 2. 验证 OTP
    # 3. 更新 otp_verified = true
    # 4. 返回成功

@router.post("/api/complete-registration")
async def complete_registration(request: CompleteRegRequest):
    """完成注册（OTP验证后）"""
    # 1. 验证 OTP
    # 2. 更新用户状态
    # 3. 生成 JWT Token
    # 4. 返回 Token
```

#### 1.3 认证中间件

```python
# api/middleware.py (新建)

from fastapi import Depends, HTTPException, Header
from typing import Optional

async def get_current_user(
    authorization: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """获取当前登录用户（中间件）"""
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证信息")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="认证格式错误")

    token = authorization[7:]  # 去掉 "Bearer "

    # 验证 JWT Token
    auth = Auth()
    user_data = auth.verify_jwt_token(token)

    if not user_data:
        raise HTTPException(status_code=401, detail="Token无效或已过期")

    return user_data

# 使用示例：
@app.get("/api/traders")
async def get_traders(current_user: Dict = Depends(get_current_user)):
    """获取交易员列表（需要认证）"""
    user_id = current_user["user_id"]
    # ...
```

---

### Phase 2: 交易员管理 API (P0) 🔥

#### 2.1 数据库方法实现

```python
# config/database.py 添加

async def get_trader_config(
    self,
    user_id: str,
    trader_id: str
) -> Optional[Tuple[Dict, Dict, Dict]]:
    """
    获取交易员完整配置（包含AI模型和交易所信息）

    返回: (trader, ai_model, exchange)
    """
    # SELECT t.*, a.*, e.*
    # FROM traders t
    # JOIN ai_models a ON t.ai_model_id = a.id
    # JOIN exchanges e ON t.exchange_id = e.id
    # WHERE t.id = ? AND t.user_id = ?

async def update_trader(self, trader: Dict[str, Any]) -> None:
    """更新交易员配置"""
    # UPDATE traders SET
    #   name = ?, ai_model_id = ?, exchange_id = ?,
    #   initial_balance = ?, scan_interval_minutes = ?,
    #   btc_eth_leverage = ?, altcoin_leverage = ?,
    #   trading_symbols = ?, custom_prompt = ?,
    #   override_base_prompt = ?, is_cross_margin = ?
    # WHERE id = ? AND user_id = ?

async def update_trader_custom_prompt(
    self,
    user_id: str,
    trader_id: str,
    custom_prompt: str,
    override_base: bool
) -> None:
    """更新交易员自定义提示词"""
    # UPDATE traders
    # SET custom_prompt = ?, override_base_prompt = ?
    # WHERE id = ? AND user_id = ?
```

#### 2.2 交易员 API 实现

```python
# api/trader_routes.py (新建)

@router.get("/api/traders")
async def get_traders(current_user: Dict = Depends(get_current_user)):
    """获取交易员列表"""
    user_id = current_user["user_id"]
    traders = await database.get_traders(user_id)
    return {"success": True, "traders": traders}

@router.get("/api/traders/{trader_id}/config")
async def get_trader_config(
    trader_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """获取交易员完整配置"""
    user_id = current_user["user_id"]
    result = await database.get_trader_config(user_id, trader_id)

    if not result:
        raise HTTPException(status_code=404, detail="交易员不存在")

    trader, ai_model, exchange = result

    return {
        "success": True,
        "trader": trader,
        "ai_model": ai_model,
        "exchange": exchange
    }

@router.post("/api/traders")
async def create_trader(
    request: CreateTraderRequest,
    current_user: Dict = Depends(get_current_user)
):
    """创建交易员"""
    user_id = current_user["user_id"]

    # 1. 验证AI模型和交易所存在
    # 2. 创建交易员
    # 3. 返回交易员ID

    trader_id = await database.create_trader({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "name": request.name,
        "ai_model_id": request.ai_model_id,
        "exchange_id": request.exchange_id,
        "initial_balance": request.initial_balance,
        # ...
    })

    return {"success": True, "trader_id": trader_id}

@router.put("/api/traders/{trader_id}")
async def update_trader(
    trader_id: str,
    request: UpdateTraderRequest,
    current_user: Dict = Depends(get_current_user)
):
    """更新交易员配置"""
    user_id = current_user["user_id"]

    # 1. 验证交易员属于当前用户
    # 2. 更新配置
    await database.update_trader({
        "id": trader_id,
        "user_id": user_id,
        **request.dict()
    })

    return {"success": True}

@router.delete("/api/traders/{trader_id}")
async def delete_trader(
    trader_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """删除交易员"""
    user_id = current_user["user_id"]

    # 1. 停止交易员（如果正在运行）
    # 2. 删除数据库记录
    await database.delete_trader(user_id, trader_id)

    return {"success": True}

@router.post("/api/traders/{trader_id}/start")
async def start_trader(
    trader_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """启动交易员"""
    user_id = current_user["user_id"]

    # 1. 验证交易员属于当前用户
    # 2. 调用 TraderManager.start_trader()
    # 3. 更新数据库状态

    await trader_manager.start_trader(trader_id)
    await database.update_trader_status(trader_id, True)

    return {"success": True}

@router.post("/api/traders/{trader_id}/stop")
async def stop_trader(
    trader_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """停止交易员"""
    user_id = current_user["user_id"]

    await trader_manager.stop_trader(trader_id)
    await database.update_trader_status(trader_id, False)

    return {"success": True}

@router.put("/api/traders/{trader_id}/prompt")
async def update_trader_prompt(
    trader_id: str,
    request: UpdatePromptRequest,
    current_user: Dict = Depends(get_current_user)
):
    """更新交易员自定义提示词"""
    user_id = current_user["user_id"]

    await database.update_trader_custom_prompt(
        user_id,
        trader_id,
        request.custom_prompt,
        request.override_base_prompt
    )

    return {"success": True}
```

---

### Phase 3: AI模型和交易所管理 (P1)

#### 3.1 数据库方法

```python
# config/database.py 添加

async def create_ai_model(self, model: Dict[str, Any]) -> str:
    """创建AI模型"""

async def update_ai_model(self, model: Dict[str, Any]) -> None:
    """更新AI模型"""

async def create_exchange(self, exchange: Dict[str, Any]) -> str:
    """创建交易所"""

async def update_exchange(self, exchange: Dict[str, Any]) -> None:
    """更新交易所"""
```

#### 3.2 API 实现

```python
@router.get("/api/models")
async def get_models(current_user: Dict = Depends(get_current_user)):
    """获取AI模型配置"""

@router.put("/api/models")
async def update_models(
    request: UpdateModelsRequest,
    current_user: Dict = Depends(get_current_user)
):
    """更新AI模型配置"""

@router.get("/api/exchanges")
async def get_exchanges(current_user: Dict = Depends(get_current_user)):
    """获取交易所配置"""

@router.put("/api/exchanges")
async def update_exchanges(
    request: UpdateExchangesRequest,
    current_user: Dict = Depends(get_current_user)
):
    """更新交易所配置"""
```

---

### Phase 4: 用户信号源 (P2)

```python
@router.get("/api/user/signal-sources")
async def get_user_signal_source(current_user: Dict = Depends(get_current_user)):
    """获取用户信号源"""

@router.post("/api/user/signal-sources")
async def save_user_signal_source(
    request: SaveSignalSourceRequest,
    current_user: Dict = Depends(get_current_user)
):
    """保存用户信号源"""
```

---

### Phase 5: 支持查询接口 (P2)

```python
@router.get("/api/supported-models")
async def get_supported_models():
    """获取系统支持的AI模型列表（无需认证）"""
    return {
        "models": [
            {"id": "deepseek", "name": "DeepSeek", "provider": "deepseek"},
            {"id": "qwen", "name": "Qwen", "provider": "qwen"},
            {"id": "custom", "name": "Custom API", "provider": "custom"},
        ]
    }

@router.get("/api/supported-exchanges")
async def get_supported_exchanges():
    """获取系统支持的交易所列表（无需认证）"""
    return {
        "exchanges": [
            {"id": "binance", "name": "Binance Futures", "type": "binance"},
            {"id": "hyperliquid", "name": "Hyperliquid", "type": "hyperliquid"},
            {"id": "aster", "name": "Aster DEX", "type": "aster"},
        ]
    }
```

---

## 实施步骤

### Step 1: 修复现有 API (1-2小时)
- [x] 修复 `/api/config` 返回系统配置而不是交易员列表

### Step 2: 实现认证系统 (1-2天)
1. 创建 `auth/__init__.py`
2. 实现用户管理数据库方法
3. 实现认证 API
4. 实现认证中间件
5. 添加单元测试

### Step 3: 实现交易员管理 API (1-2天)
1. 实现交易员相关数据库方法
2. 实现交易员 CRUD API
3. 实现启动/停止 API
4. 集成到 TraderManager
5. 测试

### Step 4: 实现配置管理 API (1天)
1. AI 模型管理
2. 交易所管理
3. 用户信号源管理

### Step 5: 完善其他 API (1天)
1. 支持查询接口
2. 性能分析接口
3. 历史决策接口

---

## 依赖安装

```bash
conda run -n nofx pip install \
    python-jose[cryptography] \
    passlib[bcrypt] \
    python-multipart
```

---

## 文件结构

```
py/
├── api/
│   ├── __init__.py
│   ├── server.py              # 主应用（修改）
│   ├── auth_routes.py         # 认证路由（新建）
│   ├── trader_routes.py       # 交易员路由（新建）
│   ├── config_routes.py       # 配置路由（新建）
│   └── middleware.py          # 认证中间件（新建）
├── auth/
│   └── __init__.py            # 认证管理（新建）
├── config/
│   ├── database.py            # 添加缺失方法
│   └── ...
└── ...
```

---

**下一步：从修复 `/api/config` 开始，然后实现认证系统。**

"""
FastAPI 认证中间件
"""

from fastapi import Depends, HTTPException, Header
from typing import Optional, Dict
import auth


async def get_current_user(
    authorization: Optional[str] = Header(None)
) -> Dict[str, str]:
    """
    获取当前登录用户（认证中间件）

    用法:
        @app.get("/api/traders")
        async def get_traders(current_user: Dict = Depends(get_current_user)):
            user_id = current_user["user_id"]
            ...

    返回:
        {"user_id": "xxx", "email": "xxx"}

    异常:
        HTTPException 401 - 认证失败
    """
    # 如果是管理员模式，直接使用admin用户
    if auth.is_admin_mode():
        return {
            "user_id": "admin",
            "email": "admin@localhost"
        }

    # 检查Authorization头
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="缺少Authorization头"
        )

    # 检查Bearer token格式
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0] != "Bearer":
        raise HTTPException(
            status_code=401,
            detail="无效的Authorization格式，应为: Bearer <token>"
        )

    token = parts[1]

    # 验证JWT token
    user_data = auth.validate_jwt(token)
    if not user_data:
        raise HTTPException(
            status_code=401,
            detail="Token无效或已过期"
        )

    return user_data

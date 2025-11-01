"""
认证模块 - JWT Token和密码哈希
"""

import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict
import pyotp


# 全局配置
JWT_SECRET = b""
ADMIN_MODE = False
OTP_ISSUER = "nofxAI"


def set_jwt_secret(secret: str):
    """设置JWT密钥"""
    global JWT_SECRET
    JWT_SECRET = secret.encode('utf-8')


def set_admin_mode(enabled: bool):
    """设置管理员模式"""
    global ADMIN_MODE
    ADMIN_MODE = enabled


def is_admin_mode() -> bool:
    """检查是否为管理员模式"""
    return ADMIN_MODE


def hash_password(password: str) -> str:
    """哈希密码"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def check_password(password: str, hashed: str) -> bool:
    """验证密码"""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False


def generate_otp_secret() -> str:
    """生成OTP密钥"""
    return pyotp.random_base32()


def verify_otp(secret: str, code: str) -> bool:
    """验证OTP码"""
    totp = pyotp.TOTP(secret)
    return totp.verify(code)


def generate_jwt(user_id: str, email: str) -> str:
    """生成JWT token"""
    payload = {
        'user_id': user_id,
        'email': email,
        'exp': datetime.utcnow() + timedelta(hours=24),  # 24小时过期
        'iat': datetime.utcnow(),
        'nbf': datetime.utcnow(),
        'iss': 'nofxAI'
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


def validate_jwt(token: str) -> Optional[Dict]:
    """
    验证JWT token

    返回:
        成功: {"user_id": "xxx", "email": "xxx"}
        失败: None
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return {
            'user_id': payload.get('user_id'),
            'email': payload.get('email')
        }
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_otp_qr_code_url(secret: str, email: str) -> str:
    """获取OTP二维码URL"""
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=email,
        issuer_name=OTP_ISSUER
    )


__all__ = [
    'set_jwt_secret',
    'set_admin_mode',
    'is_admin_mode',
    'hash_password',
    'check_password',
    'generate_otp_secret',
    'verify_otp',
    'generate_jwt',
    'validate_jwt',
    'get_otp_qr_code_url'
]

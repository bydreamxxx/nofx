"""
HTTP 全局配置模块
用于存储和访问全局 HTTP 配置（如 proxy）
"""

from typing import Optional

# 全局 HTTP 代理配置
_http_proxy: Optional[str] = None


def set_http_proxy(proxy: str):
    """
    设置全局 HTTP 代理

    Args:
        proxy: 代理地址（如 "http://127.0.0.1:7897"）
    """
    global _http_proxy
    _http_proxy = proxy if proxy else None


def get_http_proxy() -> Optional[str]:
    """
    获取全局 HTTP 代理配置

    Returns:
        代理地址，如果未配置则返回 None
    """
    return _http_proxy

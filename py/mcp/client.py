"""
AI API 客户端
支持 DeepSeek、Qwen 和自定义 OpenAI 兼容 API
"""

import httpx
import asyncio
from enum import Enum
from typing import Optional
from loguru import logger


class Provider(str, Enum):
    """AI 提供商类型"""
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    CUSTOM = "custom"


class Client:
    """AI API 客户端"""

    def __init__(self):
        self.provider: Provider = Provider.DEEPSEEK
        self.api_key: str = ""
        self.secret_key: str = ""  # 阿里云可能需要
        self.base_url: str = "https://api.deepseek.com/v1"
        self.model: str = "deepseek-chat"
        self.timeout: float = 120.0  # 超时时间（秒）
        self.use_full_url: bool = False  # 是否使用完整URL

    def set_deepseek_api_key(self, api_key: str):
        """设置 DeepSeek API 密钥"""
        self.provider = Provider.DEEPSEEK
        self.api_key = api_key
        self.base_url = "https://api.deepseek.com/v1"
        self.model = "deepseek-chat"

    def set_qwen_api_key(self, api_key: str, secret_key: str = ""):
        """设置阿里云 Qwen API 密钥"""
        self.provider = Provider.QWEN
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.model = "qwen-plus"  # 可选: qwen-turbo, qwen-plus, qwen-max

    def set_custom_api(self, api_url: str, api_key: str, model_name: str):
        """设置自定义 OpenAI 兼容 API"""
        self.provider = Provider.CUSTOM
        self.api_key = api_key

        # 检查URL是否以#结尾，如果是则使用完整URL
        if api_url.endswith("#"):
            self.base_url = api_url.rstrip("#")
            self.use_full_url = True
        else:
            self.base_url = api_url
            self.use_full_url = False

        self.model = model_name
        self.timeout = 120.0

    async def call_with_messages(
        self, system_prompt: str, user_prompt: str
    ) -> str:
        """
        使用 system + user prompt 调用 AI API

        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词

        Returns:
            AI 返回的内容
        """
        if not self.api_key:
            raise ValueError("AI API密钥未设置，请先调用 set_deepseek_api_key() 或 set_qwen_api_key()")

        # 重试配置
        max_retries = 3
        last_error = None

        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                logger.warning(f"⚠️  AI API调用失败，正在重试 ({attempt}/{max_retries})...")

            try:
                result = await self._call_once(system_prompt, user_prompt)
                if attempt > 1:
                    logger.success("✓ AI API重试成功")
                return result
            except Exception as e:
                last_error = e

                # 判断是否可重试
                if not self._is_retryable_error(e):
                    raise

                # 重试前等待
                if attempt < max_retries:
                    wait_time = attempt * 2
                    logger.info(f"⏳ 等待{wait_time}秒后重试...")
                    await asyncio.sleep(wait_time)

        raise Exception(f"重试{max_retries}次后仍然失败: {last_error}")

    async def _call_once(self, system_prompt: str, user_prompt: str) -> str:
        """单次调用 AI API（内部使用）"""
        # 构建 messages 数组
        messages = []

        # 添加 system message
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        # 添加 user message
        messages.append({
            "role": "user",
            "content": user_prompt
        })

        # 构建请求体
        request_body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.5,  # 降低temperature以提高JSON格式稳定性
            "max_tokens": 2000,
        }

        # 创建 HTTP 请求
        if self.use_full_url:
            url = self.base_url
        else:
            url = f"{self.base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        # 发送请求
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                json=request_body,
                headers=headers
            )

            if response.status_code != 200:
                raise Exception(
                    f"API返回错误 (status {response.status_code}): {response.text}"
                )

            # 解析响应
            result = response.json()

            if not result.get("choices"):
                raise Exception("API返回空响应")

            return result["choices"][0]["message"]["content"]

    def _is_retryable_error(self, error: Exception) -> bool:
        """判断错误是否可重试"""
        error_str = str(error).lower()
        retryable_errors = [
            "eof",
            "timeout",
            "connection reset",
            "connection refused",
            "temporary failure",
            "no such host",
        ]

        return any(err in error_str for err in retryable_errors)

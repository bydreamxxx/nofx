"""
AI API 客户端
使用 OpenAI SDK 统一调用所有 AI 提供商
支持: DeepSeek, Qwen, OpenRouter (通过 custom), 和其他 OpenAI 兼容 API
"""

from openai import AsyncOpenAI
from enum import Enum
from typing import Optional
from loguru import logger


class Provider(str, Enum):
    """AI 提供商类型"""
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    CUSTOM = "custom"
    OPENROUTER = "openrouter"


class Client:
    """AI API 客户端（基于 OpenAI SDK）"""

    def __init__(self):
        self.provider: Provider = Provider.DEEPSEEK
        self.client: Optional[AsyncOpenAI] = None
        self.model: str = "deepseek-chat"

    def set_deepseek_api_key(self, api_key: str, custom_url: str = "", custom_model: str = ""):
        """
        设置 DeepSeek API

        Args:
            api_key: DeepSeek API 密钥
            custom_url: 自定义 BaseURL（可选）
            custom_model: 自定义模型名称（可选）
        """
        self.provider = Provider.DEEPSEEK

        # 处理自定义 URL
        if custom_url:
            base_url = custom_url
            logger.info(f"🔧 [MCP] DeepSeek 使用自定义 BaseURL: {base_url}")
        else:
            base_url = "https://api.deepseek.com/v1"
            logger.debug(f"🔧 [MCP] DeepSeek 使用默认 BaseURL: {base_url}")

        # 处理自定义模型
        if custom_model:
            self.model = custom_model
            logger.info(f"🔧 [MCP] DeepSeek 使用自定义 Model: {self.model}")
        else:
            self.model = "deepseek-chat"
            logger.debug(f"🔧 [MCP] DeepSeek 使用默认 Model: {self.model}")

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=120.0
        )

        # 打印 API Key 的前后各4位用于验证
        if len(api_key) > 8:
            logger.debug(f"🔧 [MCP] DeepSeek API Key: {api_key[:4]}...{api_key[-4:]}")

        logger.debug("✓ DeepSeek API 已配置")

    def set_qwen_api_key(self, api_key: str, custom_url: str = "", custom_model: str = ""):
        """
        设置阿里云 Qwen API

        Args:
            api_key: Qwen API 密钥
            custom_url: 自定义 BaseURL（可选）
            custom_model: 自定义模型名称（可选）
        """
        self.provider = Provider.QWEN

        # 处理自定义 URL
        if custom_url:
            base_url = custom_url
            logger.info(f"🔧 [MCP] Qwen 使用自定义 BaseURL: {base_url}")
        else:
            base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            logger.debug(f"🔧 [MCP] Qwen 使用默认 BaseURL: {base_url}")

        # 处理自定义模型
        if custom_model:
            self.model = custom_model
            logger.info(f"🔧 [MCP] Qwen 使用自定义 Model: {self.model}")
        else:
            self.model = "qwen-plus"  # 可选: qwen-turbo, qwen-plus, qwen-max
            logger.debug(f"🔧 [MCP] Qwen 使用默认 Model: {self.model}")

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=120.0
        )

        # 打印 API Key 的前后各4位用于验证
        if len(api_key) > 8:
            logger.debug(f"🔧 [MCP] Qwen API Key: {api_key[:4]}...{api_key[-4:]}")

        logger.debug("✓ Qwen API 已配置")

    def set_openrouter_api_key(self, api_key: str, model: str):
        """
        设置 OpenRouter API

        Args:
            api_key: OpenRouter API 密钥
            secret_key: 保留参数（兼容性）
        """
        self.provider = Provider.OPENROUTER
        self.model = model
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            timeout=120.0
        )
        logger.debug("✓ OpenRouter API 已配置")

    def set_custom_api(self, base_url: str, api_key: str, model: str):
        """
        设置自定义 OpenAI 兼容 API

        支持所有 OpenAI 兼容的 API，包括：
        - OpenRouter: base_url = "https://openrouter.ai/api/v1"
        - 其他自定义 API

        Args:
            base_url: API 基础 URL（无需 /chat/completions 后缀）
            api_key: API 密钥
            model: 模型名称
                   - OpenRouter: "anthropic/claude-3.5-sonnet", "openai/gpt-4-turbo" 等
                   - 其他: 根据提供商文档
        """
        self.provider = Provider.CUSTOM
        self.model = model

        # 移除 URL 末尾的 # 标记（兼容旧配置）
        clean_base_url = base_url.rstrip("#")

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=clean_base_url,
            timeout=120.0,
            max_retries=3  # SDK 自动重试
        )
        logger.debug(f"✓ 自定义 API 已配置: {clean_base_url} (模型: {model})")

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

        Raises:
            ValueError: 如果 API 未初始化
            Exception: API 调用失败
        """
        if not self.client:
            raise ValueError(
                "AI API 未初始化，请先调用 set_deepseek_api_key()、"
                "set_openrouter_api_key()、set_qwen_api_key() 或 set_custom_api()"
            )

        # 构建 messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        try:
            # 调用 OpenAI SDK（自动重试）
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.5,
                max_tokens=2000
            )

            # 提取内容
            content = response.choices[0].message.content

            if not content:
                raise Exception("API 返回空内容")

            return content

        except Exception as e:
            logger.error(f"❌ AI API 调用失败 ({self.provider}): {e}")
            raise

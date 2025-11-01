"""
提示词管理器模块

负责从 prompts/ 目录加载和管理系统提示词模板
"""

import os
import glob
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
import asyncio
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PromptTemplate:
    """系统提示词模板"""
    name: str  # 模板名称（文件名，不含扩展名）
    content: str  # 模板内容


class PromptManager:
    """提示词管理器"""

    def __init__(self, prompts_dir: str = "prompts"):
        """
        初始化提示词管理器

        Args:
            prompts_dir: 提示词文件夹路径
        """
        self.prompts_dir = prompts_dir
        self.templates: Dict[str, PromptTemplate] = {}
        self._lock = asyncio.Lock()

    async def load_templates(self) -> int:
        """
        从指定目录加载所有提示词模板

        Returns:
            加载的模板数量
        """
        async with self._lock:
            # 检查目录是否存在
            if not os.path.exists(self.prompts_dir):
                logger.warning(f"⚠️  提示词目录不存在: {self.prompts_dir}")
                return 0

            # 扫描目录中的所有 .txt 文件
            pattern = os.path.join(self.prompts_dir, "*.txt")
            files = glob.glob(pattern)

            if not files:
                logger.warning(f"⚠️  提示词目录 {self.prompts_dir} 中没有找到 .txt 文件")
                return 0

            # 清空现有模板
            self.templates.clear()

            # 加载每个模板文件
            for file_path in files:
                try:
                    # 读取文件内容
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # 提取文件名（不含扩展名）作为模板名称
                    file_name = os.path.basename(file_path)
                    template_name = os.path.splitext(file_name)[0]

                    # 存储模板
                    self.templates[template_name] = PromptTemplate(
                        name=template_name,
                        content=content
                    )

                    logger.info(f"  📄 加载提示词模板: {template_name} ({file_name})")

                except Exception as e:
                    logger.error(f"⚠️  读取提示词文件失败 {file_path}: {e}")
                    continue

            logger.info(f"✓ 已加载 {len(self.templates)} 个系统提示词模板")
            return len(self.templates)

    def get_template(self, name: str) -> Optional[PromptTemplate]:
        """
        获取指定名称的提示词模板

        Args:
            name: 模板名称

        Returns:
            提示词模板，如果不存在则返回 None
        """
        return self.templates.get(name)

    def get_all_template_names(self) -> List[str]:
        """
        获取所有模板名称列表

        Returns:
            模板名称列表
        """
        return list(self.templates.keys())

    def get_all_templates(self) -> List[PromptTemplate]:
        """
        获取所有模板

        Returns:
            模板列表
        """
        return list(self.templates.values())

    async def reload_templates(self) -> int:
        """
        重新加载所有模板

        Returns:
            加载的模板数量
        """
        return await self.load_templates()


# 全局提示词管理器实例
_global_prompt_manager: Optional[PromptManager] = None


async def init_prompt_manager(prompts_dir: str = "prompts") -> PromptManager:
    """
    初始化全局提示词管理器

    Args:
        prompts_dir: 提示词目录

    Returns:
        提示词管理器实例
    """
    global _global_prompt_manager
    _global_prompt_manager = PromptManager(prompts_dir)
    await _global_prompt_manager.load_templates()
    return _global_prompt_manager


def get_prompt_manager() -> Optional[PromptManager]:
    """
    获取全局提示词管理器实例

    Returns:
        提示词管理器实例，如果未初始化则返回 None
    """
    return _global_prompt_manager


def get_prompt_template(name: str) -> Optional[PromptTemplate]:
    """
    获取指定名称的提示词模板（全局函数）

    Args:
        name: 模板名称

    Returns:
        提示词模板，如果不存在则返回 None
    """
    if _global_prompt_manager:
        return _global_prompt_manager.get_template(name)
    return None


def get_all_prompt_template_names() -> List[str]:
    """
    获取所有模板名称（全局函数）

    Returns:
        模板名称列表
    """
    if _global_prompt_manager:
        return _global_prompt_manager.get_all_template_names()
    return []


def get_all_prompt_templates() -> List[PromptTemplate]:
    """
    获取所有模板（全局函数）

    Returns:
        模板列表
    """
    if _global_prompt_manager:
        return _global_prompt_manager.get_all_templates()
    return []


async def reload_prompt_templates() -> int:
    """
    重新加载所有模板（全局函数）

    Returns:
        加载的模板数量
    """
    if _global_prompt_manager:
        return await _global_prompt_manager.reload_templates()
    return 0

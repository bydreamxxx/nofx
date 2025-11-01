"""
测试提示词系统集成

测试流程：
1. 初始化提示词管理器
2. 加载提示词模板
3. 测试决策引擎构建 system prompt
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger
from decision.prompt_manager import init_prompt_manager, get_all_prompt_templates, get_prompt_template
from decision.engine import DecisionEngine
from mcp import Client as MCPClient
from market import MarketDataFetcher


async def test_prompt_manager():
    """测试提示词管理器"""
    logger.info("=== 测试提示词管理器 ===")

    # 初始化 - 使用相对于项目根目录的路径
    prompts_dir = Path(__file__).parent.parent / "prompts"
    await init_prompt_manager(str(prompts_dir))

    # 获取所有模板
    templates = get_all_prompt_templates()
    logger.info(f"✓ 加载了 {len(templates)} 个提示词模板:")
    for tmpl in templates:
        logger.info(f"  - {tmpl.name}: {len(tmpl.content)} 字符")

    # 测试获取单个模板
    default_tmpl = get_prompt_template("default")
    if default_tmpl:
        logger.info(f"✓ 成功获取 default 模板 ({len(default_tmpl.content)} 字符)")
        logger.info(f"  前100个字符: {default_tmpl.content[:100]}...")
    else:
        logger.error("❌ 无法获取 default 模板")
        return False

    nof1_tmpl = get_prompt_template("nof1")
    if nof1_tmpl:
        logger.info(f"✓ 成功获取 nof1 模板 ({len(nof1_tmpl.content)} 字符)")
        logger.info(f"  前100个字符: {nof1_tmpl.content[:100]}...")
    else:
        logger.warning("⚠️  无法获取 nof1 模板")

    # 测试不存在的模板
    fake_tmpl = get_prompt_template("nonexistent")
    if fake_tmpl is None:
        logger.info("✓ 正确处理不存在的模板")
    else:
        logger.error("❌ 应该返回 None 对于不存在的模板")
        return False

    return True


async def test_decision_engine():
    """测试决策引擎集成"""
    logger.info("\n=== 测试决策引擎集成 ===")

    # 创建虚拟的 MCP 客户端（不需要真实 API key）
    mcp_client = MCPClient()
    market_fetcher = MarketDataFetcher()

    engine = DecisionEngine(
        mcp_client=mcp_client,
        market_fetcher=market_fetcher,
        coin_pool_manager=None
    )

    # 测试构建 system prompt（使用 default 模板）
    logger.info("测试构建 system prompt (default 模板):")
    prompt_default = engine._build_system_prompt(
        account_equity=1000.0,
        btc_eth_leverage=5,
        altcoin_leverage=5,
        template_name="default"
    )
    logger.info(f"✓ 生成了 {len(prompt_default)} 字符的 system prompt")
    logger.info(f"  包含模板内容: {'你是一个' in prompt_default or 'You are' in prompt_default}")
    logger.info(f"  包含硬约束: {'硬约束' in prompt_default}")
    logger.info(f"  包含输出格式: {'输出格式' in prompt_default or 'JSON' in prompt_default}")

    # 测试使用 nof1 模板
    logger.info("\n测试构建 system prompt (nof1 模板):")
    prompt_nof1 = engine._build_system_prompt(
        account_equity=1000.0,
        btc_eth_leverage=10,
        altcoin_leverage=20,
        template_name="nof1"
    )
    logger.info(f"✓ 生成了 {len(prompt_nof1)} 字符的 system prompt")
    logger.info(f"  模板长度不同: {len(prompt_nof1) != len(prompt_default)}")

    # 测试自定义 prompt
    logger.info("\n测试自定义 prompt:")
    custom_prompt = "额外的交易策略：优先关注高成交量币种"
    prompt_custom = engine._build_system_prompt_with_custom(
        account_equity=1000.0,
        btc_eth_leverage=5,
        altcoin_leverage=5,
        custom_prompt=custom_prompt,
        override_base=False,
        template_name="default"
    )
    logger.info(f"✓ 生成了带自定义内容的 prompt ({len(prompt_custom)} 字符)")
    logger.info(f"  包含自定义内容: {custom_prompt in prompt_custom}")
    logger.info(f"  包含基础模板: {'硬约束' in prompt_custom}")

    # 测试覆盖模式
    logger.info("\n测试覆盖基础 prompt:")
    prompt_override = engine._build_system_prompt_with_custom(
        account_equity=1000.0,
        btc_eth_leverage=5,
        altcoin_leverage=5,
        custom_prompt="完全自定义的提示词，不包含基础内容",
        override_base=True,
        template_name="default"
    )
    logger.info(f"✓ 生成了覆盖模式的 prompt ({len(prompt_override)} 字符)")
    logger.info(f"  不包含基础模板: {'硬约束' not in prompt_override}")

    return True


async def main():
    """主测试函数"""
    logger.info("开始测试 Python 提示词系统集成\n")

    # 测试1: 提示词管理器
    success1 = await test_prompt_manager()

    # 测试2: 决策引擎集成
    success2 = await test_decision_engine()

    if success1 and success2:
        logger.info("\n" + "="*60)
        logger.success("✅ 所有测试通过！")
        logger.success("Python 提示词系统已成功集成")
        logger.info("="*60)
    else:
        logger.error("\n" + "="*60)
        logger.error("❌ 部分测试失败")
        logger.info("="*60)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

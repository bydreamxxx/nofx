#!/bin/bash

# NOFX Python 版本启动脚本

echo "================================"
echo "🐍 NOFX Python 自动交易系统"
echo "================================"
echo ""

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "⚠️  未找到虚拟环境，正在创建..."
    python3 -m venv venv
    echo "✅ 虚拟环境创建完成"
fi

# 激活虚拟环境
echo "🔄 激活虚拟环境..."
source venv/bin/activate

# 检查依赖
echo "🔄 检查 Python 依赖..."
pip install -q -r requirements.txt

# 检查数据库
if [ ! -f "../nofx.db" ]; then
    echo "❌ 错误: 未找到数据库文件 ../nofx.db"
    echo "💡 请先运行 Go 版本创建数据库，或手动创建数据库文件"
    exit 1
fi

echo "✅ 数据库文件已找到"
echo ""

# 启动系统
echo "🚀 启动 NOFX Python 系统..."
echo ""
python main.py --db ../nofx.db

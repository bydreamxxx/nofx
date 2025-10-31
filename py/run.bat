@echo off
REM NOFX Python 版本启动脚本 (Windows)

echo ================================
echo 🐍 NOFX Python 自动交易系统
echo ================================
echo.

REM 检查虚拟环境
if not exist "venv" (
    echo ⚠️  未找到虚拟环境，正在创建...
    python -m venv venv
    echo ✅ 虚拟环境创建完成
)

REM 激活虚拟环境
echo 🔄 激活虚拟环境...
call venv\Scripts\activate.bat

REM 检查依赖
echo 🔄 检查 Python 依赖...
pip install -q -r requirements.txt

REM 检查数据库
if not exist "..\nofx.db" (
    echo ❌ 错误: 未找到数据库文件 ..\nofx.db
    echo 💡 请先运行 Go 版本创建数据库，或手动创建数据库文件
    pause
    exit /b 1
)

echo ✅ 数据库文件已找到
echo.

REM 启动系统
echo 🚀 启动 NOFX Python 系统...
echo.
python main.py --db ..\nofx.db

pause

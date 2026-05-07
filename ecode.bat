@echo off
setlocal

:: 保存用户当前目录
set "USER_CWD=%cd%"

:: 你的固定项目目录
set "AGENT_DIR=E:\work\ecode_back"

:: 进入项目加载模块
cd /d "%AGENT_DIR%" 2>nul

:: 切回真实工作目录（核心！）
cd /d "%USER_CWD%"

:: 🔥 关键：用 conda 环境的 Python 直接运行（彻底无弹窗）
"D:\Anaconda\envs\clawclaw\python.exe" -m cli.chat

:: 直接退出，不等待！
exit /b
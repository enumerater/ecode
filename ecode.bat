@echo off
REM 记住你当前打开终端的位置
set "OPEN_DIR=%cd%"

REM 强制进入你的 Python 项目根目录！关键！
cd /d "E:\work\ecode_back"

REM 激活 conda 环境
call D:\Anaconda\Scripts\activate.bat D:\Anaconda\envs\clawclaw

REM 运行助手（现在目录正确，一定能找到 cli）
python -m cli.chat

REM 结束后回到你原来的目录
cd /d "%OPEN_DIR%"

pause
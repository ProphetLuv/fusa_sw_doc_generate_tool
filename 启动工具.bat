@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title 功能安全文档生成器
color 0A

echo.
echo  ============================================
echo     功能安全文档生成器 v1.0
echo     ISO 26262 / ASPICE 文档自动生成工具
echo  ============================================
echo.

:: 自动检测可用端口（从 8501 开始，最多尝试到 8510）
set PORT=8501
:find_port
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo  [提示] 端口 %PORT% 已被占用，尝试 %PORT%+1 ...
    set /a PORT+=1
    if %PORT% GTR 8510 (
        echo  [错误] 8501~8510 端口均被占用，请手动关闭占用程序后重试。
        pause
        exit /b 1
    )
    goto find_port
)

:: 自动检测虚拟环境（遍历当前目录下所有包含 Scripts\python.exe 的文件夹）
set "PYTHON="
set "VENV_NAME="
for /d %%D in ("%~dp0*") do (
    if exist "%%D\Scripts\python.exe" (
        if "!PYTHON!"=="" (
            set "PYTHON=%%D\Scripts\python.exe"
            set "VENV_NAME=%%~nxD"
        )
    )
)

if "!PYTHON!"=="" (
    echo  [错误] 未检测到 Python 虚拟环境。
    echo  请在程序目录下创建虚拟环境，例如：
    echo.
    echo      python -m venv .venv
    echo.
    pause
    exit /b 1
)

echo  [信息] 检测到虚拟环境: !VENV_NAME!

echo  正在启动服务（端口: %PORT%）...
echo  启动后请在浏览器中访问:
echo.
echo     http://localhost:%PORT%
echo.
echo  关闭此窗口即可停止程序
echo  ============================================
echo.

cd /d "%~dp0"
"!PYTHON!" -m streamlit run src\app.py --server.headless true --browser.gatherUsageStats false --server.port %PORT%

pause

@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title 功能安全文档生成器
color 0A

echo.
echo  ============================================
echo     功能安全文档生成器 v3.0
echo     ISO 26262 / ASPICE 文档自动生成工具
echo  ============================================
echo.

cd /d "%~dp0"

:: ============================================================
:: 1. 检测虚拟环境（遍历当前目录下所有包含 Scripts\python.exe 的文件夹）
:: ============================================================
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

if not "!PYTHON!"=="" (
    echo  [信息] 检测到虚拟环境: !VENV_NAME!
    goto check_deps
)

:: ============================================================
:: 2. 一键安装：检测系统 Python 并自动创建虚拟环境
:: ============================================================
echo  [提示] 未检测到 Python 虚拟环境，即将自动完成安装（首次约需 3~5 分钟）。
echo.

:: 通过实际执行来检测（可排除 Microsoft Store 的假 python.exe）
set "SYS_PYTHON="
python -c "import sys" >nul 2>&1
if not errorlevel 1 set "SYS_PYTHON=python"
if "!SYS_PYTHON!"=="" (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 set "SYS_PYTHON=py -3"
)
if "!SYS_PYTHON!"=="" (
    echo  [错误] 未检测到 Python，请先安装 Python 3.10 或更高版本：
    echo.
    echo      1. 打开 https://www.python.org/downloads/ 下载安装包
    echo      2. 安装时务必勾选 "Add python.exe to PATH"
    echo      3. 安装完成后重新双击本脚本
    echo.
    pause
    exit /b 1
)

:: 检查 Python 版本（要求 3.10 及以上）
for /f "tokens=2 delims= " %%V in ('!SYS_PYTHON! --version 2^>^&1') do set "PY_VER=%%V"
for /f "tokens=1,2 delims=." %%A in ("!PY_VER!") do (
    set /a PY_MAJOR=%%A
    set /a PY_MINOR=%%B
)
if !PY_MAJOR! LSS 3 goto version_too_old
if !PY_MAJOR! EQU 3 if !PY_MINOR! LSS 10 goto version_too_old
echo  [信息] 检测到 Python !PY_VER!
goto create_venv

:version_too_old
echo  [错误] Python 版本过低（当前 !PY_VER!），本工具需要 Python 3.10 或更高版本。
echo         请前往 https://www.python.org/downloads/ 升级后重新运行本脚本。
pause
exit /b 1

:create_venv
echo  [信息] 正在创建虚拟环境 .venv ...
!SYS_PYTHON! -m venv "%~dp0.venv"
if errorlevel 1 (
    echo  [错误] 虚拟环境创建失败，请检查 Python 安装是否完整后重试。
    pause
    exit /b 1
)
set "PYTHON=%~dp0.venv\Scripts\python.exe"
set "VENV_NAME=.venv"
echo  [信息] 虚拟环境创建成功。

:: ============================================================
:: 3. 依赖完整性自检（缺失时自动安装，失败自动切换国内镜像源）
:: ============================================================
:check_deps
"!PYTHON!" -c "import fastapi, uvicorn, multipart, openai, anthropic, docx, lxml, openpyxl, tree_sitter" >nul 2>&1
if not errorlevel 1 (
    echo  [信息] 依赖包已就绪。
    goto find_port
)

echo  [信息] 正在安装依赖包（requirements.txt），请耐心等待...
"!PYTHON!" -m pip install --upgrade pip >nul 2>&1
"!PYTHON!" -m pip install -r "%~dp0requirements.txt"
if not errorlevel 1 goto deps_ok

echo.
echo  [提示] 默认源安装失败，自动切换清华镜像源重试...
"!PYTHON!" -m pip install -r "%~dp0requirements.txt" -i https://pypi.tuna.tsinghua.edu.cn/simple
if not errorlevel 1 goto deps_ok

echo  [错误] 依赖安装失败，请检查网络连接后重新运行本脚本。
pause
exit /b 1

:deps_ok
echo  [信息] 依赖安装完成。

:: ============================================================
:: 4. 自动检测可用端口（从 8000 开始，最多尝试到 8010）
:: ============================================================
:find_port
set PORT=8000
:port_loop
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
    echo  [提示] 端口 %PORT% 已被占用，尝试下一个...
    set /a PORT+=1
    if !PORT! GTR 8010 (
        echo  [错误] 8000~8010 端口均被占用，请手动关闭占用程序后重试。
        pause
        exit /b 1
    )
    goto port_loop
)

:: ============================================================
:: 5. 清理 src 下的字节码缓存（__pycache__，启动后会自动重建）
:: ============================================================
for /d /r "%~dp0src" %%P in (__pycache__) do (
    if exist "%%P" rd /s /q "%%P" >nul 2>&1
)
echo  [信息] 已清理 __pycache__ 缓存。

:: ============================================================
:: 6. 启动服务
:: ============================================================
echo.
echo  正在启动服务（端口: %PORT%）...
echo  启动后请在浏览器中访问:
echo.
echo     http://localhost:%PORT%
echo.
echo  关闭此窗口即可停止程序
echo  ============================================
echo.

:: 确保 src 目录存在
if not exist "%~dp0src" (
    echo  [错误] 未找到 src 目录，请确认项目文件完整性。
    pause
    exit /b 1
)

:: 延迟 3 秒后自动打开浏览器（预留 uvicorn 启动时间）
start "" /min cmd /c "timeout /t 3 >nul & start http://localhost:%PORT%"

cd /d "%~dp0src"
"!PYTHON!" -m uvicorn server.main:app --host 127.0.0.1 --port %PORT%

pause

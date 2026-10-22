@echo off
chcp 936 >nul
title 内网聊天 一键部署
rem ============================================
rem  内网聊天 - 一键部署到 Armbian / Debian (arm64)
rem  用法1: 双击本文件，按提示输入
rem  用法2: 命令行: 一键部署.bat 服务器IP 用户名 密码
rem ============================================
setlocal enabledelayedexpansion
cd /d %~dp0

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 本机没有安装 Python，请先安装 Python 3 并勾选 Add to PATH
    pause
    exit /b 1
)

python --version 2>nul | findstr /C:"Python" >nul
if errorlevel 1 (
    echo [错误] python 无法运行，可能是 Microsoft Store 占位程序，
    echo        请安装真正的 Python 3 并勾选 Add to PATH
    pause
    exit /b 1
)

python -c "import paramiko" >nul 2>nul
if errorlevel 1 (
    echo 首次使用，正在安装部署依赖 paramiko ...
    python -m pip install paramiko -q
    python -c "import paramiko" >nul 2>nul
    if errorlevel 1 (
        echo [错误] paramiko 安装失败，请手动执行: python -m pip install paramiko
        pause
        exit /b 1
    )
)

if "%~1"=="" (
    echo.
    set /p DHOST=请输入服务器IP，例如 192.168.9.99 :
    set /p DUSER=请输入SSH用户名，直接回车默认 root :
    set /p DPASS=请输入SSH密码 :
) else (
    set DHOST=%~1
    set DUSER=%~2
    set DPASS=%~3
)

if not defined DUSER set DUSER=root
if not defined DHOST (
    echo [错误] 未输入服务器IP
    pause
    exit /b 1
)
if not defined DPASS (
    echo [错误] 未输入密码
    pause
    exit /b 1
)

echo.
echo 开始部署到 !DHOST! ，预计 1-2 分钟 ...
echo.

python deploy.py --host !DHOST! --user !DUSER! --password !DPASS!
if errorlevel 1 (
    echo.
    echo [失败] 部署未成功，请检查上方错误信息
)
echo.
echo 流程结束。
pause

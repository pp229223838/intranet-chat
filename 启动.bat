@echo off
chcp 936 >nul
title 内网聊天 服务
rem ============================================
rem  内网聊天 - 启动本地/服务器端聊天服务
rem  双击本文件即可启动；关闭窗口即停止服务
rem  端口如需修改，改下面两行（页面 / 实时通信）
rem ============================================
set CHAT_HTTP_PORT=8090
set CHAT_WS_PORT=8091
cd /d %~dp0

if exist "内网聊天.exe" (
    echo 正在启动内网聊天服务（免安装模式）...
    echo 内网浏览器访问: http://本机IP:8090
    echo 关闭本窗口即停止服务，聊天记录不会丢失
    echo.
    "内网聊天.exe"
) else (
    echo 正在启动内网聊天服务（Python 模式）...
    echo 内网浏览器访问: http://本机IP:8090
    echo 关闭本窗口即停止服务，聊天记录不会丢失
    echo.
    python server.py
)

echo.
echo 服务已退出。
echo 若刚启动就退出，一般是 8090/8091 端口被占用，
echo 可结束占用程序，或修改本文件顶部的端口设置。
pause

---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'acc3f6bb-ee3c-445b-9b8d-4fd7952eee8c'
  PropagateID: 'acc3f6bb-ee3c-445b-9b8d-4fd7952eee8c'
  ReservedCode1: '0034a837-a252-416a-88ae-a9690551d2bb'
  ReservedCode2: '0034a837-a252-416a-88ae-a9690551d2bb'
---

# 内网聊天（Intranet Chat）

纯本地、零外部依赖的内网即时通讯系统。一个文件跑起来，全公司浏览器直接用。

## 功能特性

- **登录即注册**：用户名 + 密码，第一次输入自动注册
- **公共频道群聊** + **1对1 私聊**
- **实时在线状态**：同事上线/下线即时显示
- **截图发送**：`Win+Shift+S` 截图后回到输入框 `Ctrl+V` 粘贴即发
- **图片/文件发送**：单文件最大 50MB，双击图片可放大预览（滚轮缩放、拖动、双击复位）
- **消息持久化**：聊天记录、账号、文件全部存本地文件，重启不丢
- **崩溃自动拉起 + 开机自启**（Linux systemd 部署时）

## 快速开始

### 方式一：Windows 直接跑（推荐内网无服务器时）

1. 下载本仓库，双击 `启动.bat`（或直接运行 `内网聊天.exe`）
2. 首次运行 Windows 防火墙弹窗请点"允许"
3. 内网任何电脑浏览器打开 `http://本机IP:8090`

> exe 模式无需安装 Python；聊天记录存在 exe 旁边的 `data/`、`uploads/` 目录，拷贝 exe 到别处不会丢数据。

### 方式二：部署到 Armbian / Debian（arm64）服务器（推荐长期使用）

在任意 Windows 电脑（需装 Python 3）：

1. 双击 `一键部署\一键部署.bat`
2. 按提示输入服务器 IP、SSH 用户名（默认 root）、密码
3. 约 1~2 分钟自动完成：环境检查 → 上传 → 装依赖 → systemd 配置 → 全链路验证

同事访问 `http://服务器IP:8090` 即可。

> 依赖安装三重保障：在线 pip（清华镜像）→ 内置离线 wheel → zipfile 直接解压，服务器没外网也能装好。

命令行方式（免交互，适合脚本化）：

```
python 一键部署/deploy.py --host 192.168.x.x --user root --password 你的密码
```

可选参数：`--http-port 8090 --ws-port 8091 --path /opt/chat`

## 日常运维（Linux 服务器）

```
systemctl status intranet-chat      # 查看状态
systemctl restart intranet-chat     # 重启
journalctl -u intranet-chat -f      # 实时日志
```

数据位置（注意备份、不要删除）：

| 路径 | 内容 |
|---|---|
| `/opt/chat/data/` | 账号 + 聊天记录 |
| `/opt/chat/uploads/` | 图片与文件 |

卸载：

```
systemctl disable --now intranet-chat
rm -rf /opt/chat /etc/systemd/system/intranet-chat.service
systemctl daemon-reload
```

## 升级新版本

改完代码后：重新跑一次 `一键部署.bat` 即可。幂等更新，自动停旧服务、传新文件、重启，**聊天记录与上传文件不丢**。

已登录网页的同事升级后按 `Ctrl+F5` 强刷加载新前端。

## 修改端口

- Windows：编辑 `启动.bat` 顶部的 `CHAT_HTTP_PORT` / `CHAT_WS_PORT`
- Linux：`systemctl edit intranet-chat` 修改两个 Environment 端口，或部署时用 `--http-port` 参数

## 技术说明

- 后端：Python 3 标准库 + websockets（HTTP 静态/上传 + WebSocket 实时通信，双端口）
- 前端：原生 HTML/CSS/JS 单页应用，无任何框架与构建步骤
- 打包：PyInstaller 单文件 exe（静态资源内嵌，用户数据外置）

## 安全提示

账号密码明文存储于服务器 `data/users.json`，通信走明文 http，适用于**可信内网**环境。如需公网或高安全场景，请自行加 HTTPS 反向代理并加强密码策略。

> AI生成
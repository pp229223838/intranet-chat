# -*- coding: utf-8 -*-
"""
内网聊天软件 后端服务
包含两个服务：
  - HTTP  服务  (0.0.0.0:8080)  提供静态页面 + 登录接口 + 图片/文件上传
  - WebSocket 服务 (0.0.0.0:8081) 实时聊天、在线状态、消息历史
仅依赖标准库 + websockets 库。
"""

import base64
import json
import mimetypes
import os
import re
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

from websockets.sync.server import serve as ws_serve
from websockets.exceptions import ConnectionClosed

# PyInstaller 单文件 exe 环境：静态页面在临时解包目录（只读），
# 用户数据/上传文件放在 exe 同级目录，便于持久化。
if getattr(sys, "frozen", False):
    BASE = Path(sys.executable).resolve().parent
    STATIC = Path(getattr(sys, "_MEIPASS", BASE)) / "static"
else:
    BASE = Path(__file__).resolve().parent
    STATIC = BASE / "static"
UPLOADS = BASE / "uploads"
DATA = BASE / "data"
UPLOADS.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)

USERS_FILE = DATA / "users.json"
MSGS_FILE = DATA / "messages.jsonl"

HTTP_PORT = int(os.environ.get("CHAT_HTTP_PORT", 8090))
WS_PORT = int(os.environ.get("CHAT_WS_PORT", 8091))
MAX_UPLOAD = 50 * 1024 * 1024  # 单文件最大 50MB

# ---------------- 用户 ----------------
users_lock = threading.Lock()


def load_users():
    if USERS_FILE.exists():
        try:
            return json.loads(USERS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_users(u):
    USERS_FILE.write_text(json.dumps(u, ensure_ascii=False, indent=2), encoding="utf-8")


users = load_users()

# ---------------- 消息记录 ----------------
msgs = []  # 所有历史消息


def load_history():
    if MSGS_FILE.exists():
        with open(MSGS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        msgs.append(json.loads(line))
                    except Exception:
                        pass


load_history()


def append_msg(m):
    msgs.append(m)
    with open(MSGS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")


# ---------------- WebSocket 连接表 ----------------
conns = {}  # username -> ServerConnection
conns_lock = threading.Lock()


def online_users():
    with conns_lock:
        return list(conns.keys())


def send_json(conn, obj):
    try:
        conn.send(json.dumps(obj, ensure_ascii=False))
        return True
    except Exception:
        return False


def broadcast_to(user, obj):
    with conns_lock:
        c = conns.get(user)
    if c is not None:
        return send_json(c, obj)
    return False


def broadcast_to_many(users_, obj):
    for u in users_:
        broadcast_to(u, obj)


# ---------------- WebSocket 业务 ----------------
def handle_chat(msg, from_user):
    to = msg.get("to")
    payload = msg.get("payload") or {}
    rec = {
        "type": "message",
        "from": from_user,
        "to": to,
        "payload": payload,
        "ts": time.time(),
    }
    append_msg(rec)
    if to == "group":
        targets = [u for u in online_users() if u != from_user]
    else:
        targets = [to] if to else []
    broadcast_to_many(targets, rec)
    broadcast_to(from_user, rec)  # 回显给自己，保证本地时间戳一致


def ws_handler(conn):
    user = None
    try:
        first = json.loads(conn.recv())
    except Exception:
        return
    if first.get("type") != "hello" or not first.get("username"):
        return
    user = str(first["username"]).strip()
    with users_lock:
        if user not in users:
            conn.send(json.dumps({"type": "error", "msg": "用户不存在，请先登录"}, ensure_ascii=False))
            return

    with conns_lock:
        conns[user] = conn

    # 初始化：历史 + 在线列表
    send_json(conn, {"type": "init", "online": online_users(), "history": msgs[-200:]})
    broadcast_to_many([u for u in online_users() if u != user],
                      {"type": "presence", "user": user, "online": True})

    try:
        while True:
            raw = conn.recv()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("type") == "chat":
                handle_chat(msg, user)
    except (ConnectionClosed, Exception):
        pass
    finally:
        with conns_lock:
            conns.pop(user, None)
        broadcast_to_many([u for u in online_users() if u != user],
                          {"type": "presence", "user": user, "online": False})


# ---------------- HTTP 处理 ----------------
class Handler(BaseHTTPRequestHandler):
    server_version = "ChatServer/1.0"

    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, base, rel):
        """安全地提供文件：处理 URL 解码 + 防目录穿越"""
        rel = unquote(rel)
        target = (Path(base) / rel).resolve()
        try:
            target.relative_to(Path(base).resolve())
        except ValueError:
            self._send(403, "Forbidden")
            return
        if not target.is_file():
            self._send(404, "Not Found")
            return
        raw = target.read_bytes()
        ctype, _ = mimetypes.guess_type(str(target))
        self._send(200, raw, ctype or "application/octet-stream")

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            return json.loads(raw)
        except Exception:
            return None

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/index.html"):
            self._serve_file(STATIC, "index.html")
        elif p.startswith("/static/"):
            self._serve_file(STATIC, p[len("/static/"):])
        elif p.startswith("/uploads/"):
            self._serve_file(UPLOADS, p[len("/uploads/"):])
        elif p == "/api/users":
            online = set(online_users())
            lst = [{"name": n, "online": n in online} for n in sorted(users.keys())]
            self._send(200, json.dumps({"ok": True, "users": lst}))
        else:
            self._send(404, "Not Found")

    def do_POST(self):
        p = urlparse(self.path).path
        if p == "/api/login":
            data = self._read_json()
            if not data:
                self._send(400, json.dumps({"ok": False, "msg": "请求格式错误"}))
                return
            name = (data.get("username") or "").strip()
            pwd = data.get("password") or ""
            if not name:
                self._send(400, json.dumps({"ok": False, "msg": "请输入用户名"}))
                return
            if not re.match(r"^[\w\u4e00-\u9fa5\-]{1,24}$", name):
                self._send(400, json.dumps({"ok": False, "msg": "用户名只能为中文、字母、数字、下划线，最长24个字符"}))
                return
            with users_lock:
                if name in users:
                    if users[name] != pwd:
                        self._send(401, json.dumps({"ok": False, "msg": "密码错误"}))
                        return
                    reg = False
                else:
                    users[name] = pwd
                    save_users(users)
                    reg = True
            self._send(200, json.dumps({"ok": True, "reg": reg, "username": name}))

        elif p == "/api/upload":
            data = self._read_json()
            if not data:
                self._send(400, json.dumps({"ok": False, "msg": "请求格式错误"}))
                return
            name = (data.get("name") or "file").strip()
            b64 = data.get("data") or ""
            if not name or not b64:
                self._send(400, json.dumps({"ok": False, "msg": "缺少文件内容"}))
                return
            if len(b64) > MAX_UPLOAD * 4 // 3:
                self._send(413, json.dumps({"ok": False, "msg": "文件超过 50MB 限制"}))
                return
            try:
                raw = base64.b64decode(b64)
            except Exception:
                self._send(400, json.dumps({"ok": False, "msg": "文件内容非法"}))
                return
            safe_name = os.path.basename(name).replace(" ", "_")
            safe_name = re.sub(r"[\\/:*?\"<>|]", "_", safe_name)
            fname = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}_{safe_name}"
            (UPLOADS / fname).write_bytes(raw)
            ctype, _ = mimetypes.guess_type(safe_name)
            self._send(200, json.dumps({
                "ok": True,
                "url": "/uploads/" + fname,
                "name": safe_name,
                "size": len(raw),
                "type": ctype or "application/octet-stream",
            }))

        else:
            self._send(404, json.dumps({"ok": False, "msg": "Not Found"}))


def main():
    http = ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), Handler)
    http_thread = threading.Thread(target=http.serve_forever, daemon=True)
    http_thread.start()
    print(f"[内网聊天] HTTP 服务已启动:   http://0.0.0.0:{HTTP_PORT}")
    print(f"[内网聊天] WebSocket 服务启动: ws://0.0.0.0:{WS_PORT}")
    print(f"[内网聊天] 数据目录:           {DATA}")

    with ws_serve(ws_handler, "0.0.0.0", WS_PORT) as srv:
        srv.serve_forever()


if __name__ == "__main__":
    main()
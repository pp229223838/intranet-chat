# -*- coding: utf-8 -*-
"""
内网聊天 一键部署脚本（Windows 端运行，目标：Armbian / Debian 11 arm64）

用法：
    python deploy.py --host 192.168.x.x --user root --password 你的SSH密码
可选参数：
    --http-port 8090   页面端口
    --ws-port   8091   WebSocket 端口
    --path /opt/chat   服务器安装目录

依赖安装策略（依次尝试）：
    1. 服务器在线 pip（清华镜像）装到独立目录，不污染系统
    2. 使用本包 wheels/ 里的离线 wheel + pip --no-index
    3. 用 python3 zipfile 直接解压 wheel（零工具依赖兜底）

更新部署：重复运行即可，账号/消息/上传文件全部保留。
"""

import argparse
import os
import shlex
import sys
import time

try:
    import paramiko
except ImportError:
    print("[错误] 缺少 paramiko，请先执行: pip install paramiko")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)          # 项目根目录：内网聊天/
WHEELS = os.path.join(HERE, "wheels")    # 离线依赖包

FILES = [
    ("server.py", "server.py"),
    ("static/index.html", "static/index.html"),
    ("static/app.js", "static/app.js"),
    ("static/style.css", "static/style.css"),
]

SERVICE_FILE = "/etc/systemd/system/intranet-chat.service"


def is_root():
    return args.user == "root"


class Deployer:
    def __init__(self, a):
        self.a = a
        self.cli = paramiko.SSHClient()
        self.cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # 先以输出版本号方式确认 paramiko 正常
        print(f"paramiko {paramiko.__version__}")

    # ---------- 基础 ----------
    def connect(self):
        print(f"[1/7] 连接服务器 {self.a.host} (用户: {self.a.user}) ...")
        self.cli.connect(self.a.host, username=self.a.user, password=self.a.password,
                         timeout=15, look_for_keys=False, allow_agent=False)
        self.verify_identity()
        print("      连接成功")

    def run(self, cmd, timeout=300, check=False, quiet=True):
        """在服务器执行命令；非 root 自动加 sudo"""
        if not is_root():
            cmd = "echo %s | sudo -S bash -c %s" % (
                shlex.quote(self.a.password), shlex.quote(cmd))
        stdin, stdout, stderr = self.cli.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        if not quiet or rc != 0:
            tail = (out + "\n" + err).strip()
            if tail:
                print("      " + tail[:400].replace("\n", "\n      "))
        if check and rc != 0:
            raise RuntimeError(f"命令失败(rc={rc}): {cmd[:80]}")
        return rc, out

    def verify_identity(self):
        rc, out = self.run("id -un")
        real = out.strip().splitlines()[-1] if out.strip() else ""
        if real != "root" and is_root():
            raise RuntimeError(f"预期 root 实际为 {real}，请检查用户名")

    # ---------- 步骤 ----------
    def check_env(self):
        print("[2/7] 检查服务器环境 ...")
        rc, out = self.run("cat /etc/os-release 2>/dev/null | head -1")
        print(f"      系统: {(out.strip() or '未知').split('=')[-1]}")
        rc, out = self.run("uname -m")
        print(f"      架构: {out.strip()}")
        self.run("command -v python3 >/dev/null || { echo NO_PY; }")
        rc, out = self.run("python3 --version 2>&1")
        if "Python 3" not in out:
            raise RuntimeError("服务器没有 python3，请先安装: apt-get install -y python3")
        print(f"      {out.strip()}")
        rc, out = self.run("command -v systemctl >/dev/null && echo OK || echo NO")
        if "OK" not in out:
            raise RuntimeError("服务器没有 systemd，无法自动开机自启")
        rc, out = self.run(f"ss -tlnp 2>/dev/null | grep ':{self.a.http_port} ' | head -1")
        if out.strip():
            # 端口被占：是旧版聊天服务则停掉再部署（更新场景）；别的进程才报错
            if "intranet-chat" in out or "python3" in out:
                print("      检测到旧版聊天服务，先停止以便更新 ...")
                self.run("systemctl stop intranet-chat 2>/dev/null")
                time.sleep(1)
                rc, out2 = self.run(f"ss -tln | grep -c ':{self.a.http_port} ' || true")
                if out2.strip() != "0":
                    raise RuntimeError(f"端口 {self.a.http_port} 仍被占用: {out.strip()[:120]}")
            else:
                raise RuntimeError(f"端口 {self.a.http_port} 已被其他程序占用: {out.strip()[:120]}")
        print("      环境检查通过")

    def upload(self):
        print("[3/7] 上传项目文件 ...")
        base = self.a.path
        self.run(f"mkdir -p {base}/static {base}/data {base}/uploads {base}/lib")
        sftp = self.cli.open_sftp()
        for local, remote in FILES:
            lp = os.path.join(PROJECT, local)
            if not os.path.exists(lp):
                raise RuntimeError(f"找不到文件: {lp}")
            sftp.put(lp, f"{base}/{remote}")
            print(f"      {local} ({os.path.getsize(lp)} B)")
        sftp.close()

    def install_deps(self):
        print("[4/7] 安装依赖 websockets ...")
        base = self.a.path
        # 已装则跳过
        rc, out = self.run(f"PYTHONPATH={base}/lib python3 -c 'import websockets' 2>/dev/null && echo YES || echo NO")
        if "YES" in out:
            print("      已存在，跳过")
            return
        if not os.path.isdir(WHEELS) or not os.listdir(WHEELS):
            print("      [提示] 本包无离线 wheel，将只尝试在线安装")
        # 策略1：在线
        rc, _ = self.run(
            f"pip3 install --target={base}/lib websockets -q "
            f"-i https://pypi.tuna.tsinghua.edu.cn/simple 2>/dev/null")
        rc, out = self.run(f"PYTHONPATH={base}/lib python3 -c 'import websockets' 2>/dev/null && echo YES || echo NO")
        if "YES" in out:
            print("      在线安装成功")
            return
        # 策略2：离线 wheel + pip
        if os.path.isdir(WHEELS) and os.listdir(WHEELS):
            print("      在线失败，尝试离线 wheel ...")
            sftp = self.cli.open_sftp()
            self.run("mkdir -p /tmp/chat-wheels")
            for f in os.listdir(WHEELS):
                sftp.put(os.path.join(WHEELS, f), f"/tmp/chat-wheels/{f}")
                print(f"      上传 {f}")
            sftp.close()
            self.run(f"pip3 install --no-index --find-links=/tmp/chat-wheels --target={base}/lib websockets h11 -q 2>/dev/null")
            rc, out = self.run(f"PYTHONPATH={base}/lib python3 -c 'import websockets' 2>/dev/null && echo YES || echo NO")
            if "YES" in out:
                print("      离线 pip 安装成功")
                self.run("rm -rf /tmp/chat-wheels")
                return
            # 策略3：直接解压 wheel（zipfile 兜底）
            print("      pip 不可用，用 zipfile 解压 wheel 兜底 ...")
            for f in os.listdir(WHEELS):
                if f.endswith(".whl"):
                    self.run(f"cd {base}/lib && python3 -m zipfile -e /tmp/chat-wheels/{f} .")
            rc, out = self.run(f"PYTHONPATH={base}/lib python3 -c 'import websockets' 2>/dev/null && echo YES || echo NO")
            self.run("rm -rf /tmp/chat-wheels")
            if "YES" in out:
                print("      zipfile 解压成功")
                return
        raise RuntimeError("websockets 安装失败，请手动检查服务器 pip 或网络")

    def systemd(self):
        print("[5/7] 配置 systemd 开机自启 ...")
        unit = f"""[Unit]
Description=Intranet Chat Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={self.a.path}
Environment=PYTHONPATH={self.a.path}/lib
Environment=CHAT_HTTP_PORT={self.a.http_port}
Environment=CHAT_WS_PORT={self.a.ws_port}
ExecStart=/usr/bin/python3 {self.a.path}/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""
        if is_root():
            sftp = self.cli.open_sftp()
            with sftp.open(SERVICE_FILE, "w") as f:
                f.write(unit)
            sftp.close()
        else:
            # 非 root：先写 /tmp 再 sudo mv
            sftp = self.cli.open_sftp()
            with sftp.open("/tmp/intranet-chat.service", "w") as f:
                f.write(unit)
            sftp.close()
            self.run(f"mv /tmp/intranet-chat.service {SERVICE_FILE}")
        self.run("systemctl daemon-reload")
        rc, _ = self.run("systemctl is-active intranet-chat >/dev/null 2>&1 && echo RUN || echo STOP")
        if "RUN" in _:
            print("      服务已存在，重启加载新版本 ...")
            self.run("systemctl restart intranet-chat")
        else:
            self.run("systemctl enable --now intranet-chat")

    def verify(self):
        print("[6/7] 启动并验证 ...")
        # 等服务到 active（Type=simple 启动很快，但保险起见等几秒）
        for i in range(10):
            rc, out = self.run("systemctl is-active intranet-chat")
            if "active" in out:
                break
            time.sleep(1)
        if "active" not in out:
            self.run("journalctl -u intranet-chat -n 10 --no-pager", quiet=False)
            raise RuntimeError("服务未能启动，请看上方日志")
        # 等端口就绪（刚启动时端口绑定可能慢半拍，加重试）
        for i in range(15):
            rc, _ = self.run(
                f"ss -tln | grep -cE ':{self.a.http_port} |:{self.a.ws_port} ' || true")
            if _.strip() == "2":
                break
            time.sleep(1)
        if _.strip() != "2":
            self.run("journalctl -u intranet-chat -n 10 --no-pager", quiet=False)
            raise RuntimeError("端口未正常监听")
        # 等页面可访问（多试几次）
        code = ""
        for i in range(10):
            rc, code = self.run(f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{self.a.http_port}/", timeout=15)
            if code.strip() == "200":
                break
            time.sleep(1)
        if code.strip() != "200":
            raise RuntimeError(f"服务器本机访问页面失败，状态码: {code.strip()}")
        rc, enabled = self.run("systemctl is-enabled intranet-chat")
        print(f"      服务运行中，开机自启: {enabled.strip() or '未知'}")

        # 从本机（内网另一台电脑视角）访问
        try:
            import urllib.request
            url = f"http://{self.a.host}:{self.a.http_port}/"
            with urllib.request.urlopen(url, timeout=8) as r:
                ok = (r.status == 200)
            print("      本机访问页面: " + ("200 OK" if ok else str(r.status)))
        except Exception as e:
            print(f"      [提示] 本机访问失败（可能是防火墙/网段）: {e}")

    def finish(self):
        port_note = "" if self.a.http_port == 8090 else f"(自定义端口)"
        print("=" * 52)
        print(f"[7/7] 部署完成！")
        print(f"  访问地址:  http://{self.a.host}:{self.a.http_port}/  {port_note}")
        print(f"  安装位置:  {self.a.path}   (data/ 与 uploads/ 内为聊天记录和文件，请勿删除)")
        print(f"  开机自启:  已启用；崩溃会自动拉起")
        print(f"  运维命令:  systemctl status|restart intranet-chat")
        print(f"             journalctl -u intranet-chat -f  (看日志)")
        print("=" * 52)
        self.cli.close()


def main():
    global args
    ap = argparse.ArgumentParser(description="内网聊天一键部署")
    ap.add_argument("--host", required=True, help="服务器 IP")
    ap.add_argument("--user", default="root", help="SSH 用户名，默认 root")
    ap.add_argument("--password", required=True, help="SSH 密码")
    ap.add_argument("--http-port", default=8090, type=int)
    ap.add_argument("--ws-port", default=8091, type=int)
    ap.add_argument("--path", default="/opt/chat")
    args = ap.parse_args()

    d = Deployer(args)
    try:
        d.connect()
        d.check_env()
        d.upload()
        d.install_deps()
        d.systemd()
        d.verify()
        d.finish()
    except Exception as e:
        print(f"\n[失败] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
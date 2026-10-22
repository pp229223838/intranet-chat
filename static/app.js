/* 内网聊天前端逻辑 */
(function () {
  "use strict";

  const GROUP_KEY = "group";
  const GROUP_NAME = "公共频道";

  let me = "";
  let ws = null;
  let wsRetry = 0;
  let allUsers = []; // [{name, online}]
  let allMsgs = []; // 历史 + 实时消息
  let current = null; // 当前会话 key

  const $ = (id) => document.getElementById(id);

  /* ---------- 工具 ---------- */
  function toast(msg) {
    const el = $("toast");
    el.textContent = msg;
    el.classList.remove("hidden");
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.add("hidden"), 2600);
  }

  function fmtTime(ts) {
    const d = new Date(ts * 1000);
    const now = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    if (d.toDateString() === now.toDateString()) {
      return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }
    return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function fmtSize(n) {
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
    return (n / 1024 / 1024).toFixed(1) + " MB";
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  /* ---------- WebSocket ---------- */
  function connectWS() {
    const proto = location.protocol === "https:" ? "wss://" : "ws://";
    ws = new WebSocket(proto + location.hostname + ":8091");
    ws.onopen = () => {
      reconnectRetry = 0;
      ws.send(JSON.stringify({ type: "hello", username: me }));
    };
    ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch (err) { return; }
      handleServer(msg);
    };
    ws.onclose = () => {
      if (!me) return;
      const t = Math.min(8000, 1000 * Math.pow(2, reconnectRetry));
      reconnectRetry++;
      setTimeout(connectWS, t);
    };
    ws.onerror = () => {};
  }

  let reconnectRetry = 0;

  function handleServer(msg) {
    if (msg.type === "init") {
      onlineUsers = new Set(msg.online || []);
      allMsgs = msg.history || [];
      refreshSidebar();
      if (!current) selectConv(GROUP_KEY);
      renderMessages();
      return;
    }
    if (msg.type === "presence") {
      if (msg.online) onlineUsers.add(msg.user); else onlineUsers.delete(msg.user);
      refreshSidebar();
      return;
    }
    if (msg.type === "message") {
      allMsgs.push(msg);
      refreshSidebar();
      if (inConv(msg)) renderMessages();
      return;
    }
    if (msg.type === "error") {
      toast(msg.msg || "连接异常");
      return;
    }
  }

  let onlineUsers = new Set();

  /* ---------- 渲染 ---------- */
  function avatarChar(name) {
    return Array.from(name)[0] || "?";
  }

  function refreshSidebar() {
    fetch("/api/users")
      .then((r) => r.json())
      .then((d) => { if (d.ok) { onlineUsers = new Set(d.users.filter(u => u.online).map(u => u.name)); renderSidebar(); } })
      .catch(() => {});
  }

  function renderSidebar() {
    const list = $("convList");
    const html = [];
    html.push(convItemHTML(GROUP_KEY, GROUP_NAME, "group", true));
    for (const u of onlineUsers) {
      if (u === me) continue;
      html.push(convItemHTML(u, u, onlineUsers.has(u), true));
    }
    list.innerHTML = html.join("");
  }

  function convItemHTML(key, name, kind, selected) {
    const dotClass = kind === "group" ? "dot group" : (onlineUsers.has(key) ? "dot" : "dot off");
    const cls = "conv-item" + (key === current ? " active" : "");
    return `<div class="${cls}" data-key="${esc(key)}">
      <div class="conv-avatar">${esc(avatarChar(name))}</div>
      <span class="conv">${esc(name)}</span>
      <span class="${dotClass}"></span>
    </div>`;
  }


  function renderMessages() {
    const box = $("msgList");
    const head = $("chatHead");
    head.textContent = current === GROUP_KEY ? GROUP_NAME + " · 公共频道" : "与 " + current + " 聊天";
    const items = allMsgs.filter((m) => inConv(m));
    if (!items.length) {
      box.innerHTML = `<div style="text-align:center;color:#9ca3af;margin-top:40px;font-size:13px">暂无消息，打个招呼吧</div>`;
      return;
    }
    box.innerHTML = items.map(msgHTML).join("");
    $("msgList").scrollTop = $("msgList").scrollHeight;
  }

  function inConv(m) {
    if (current === GROUP_KEY) return m.to === GROUP_KEY;
    return (m.to === current && m.from === me) || (m.from === current && m.to === me);
  }

  function msgHTML(m) {
    const mine = m.from === me;
    const meta = mine
      ? `${fmtTime(m.ts)}`
      : `${esc(m.from)} ${fmtTime(m.ts)}`;
    const bubble = payloadHTML(m.payload);
    return `<div class="msg-row ${mine ? "mine" : "theirs"}">
      <div class="msg-meta">${meta}</div>
      ${bubble}
    </div>`;
  }

  function payloadHTML(p) {
    if (!p) return "";
    if (p.kind === "text") {
      return `<div class="bubble">${esc(p.text)}</div>`;
    }
    if (p.kind === "file") {
      const isImg = /^image\//.test(p.type || "");
      if (isImg) {
        return `<img class="msg-img" src="${esc(p.url)}" alt="${esc(p.name)}">`;
      }
      return `<a class="file-chip" href="${esc(p.url)}" download="${esc(p.name)}">
        <div><div class="fname">${esc(p.name)}</div><div class="fsmeta">${fmtSize(p.size)}</div></div>
      </a>`;
    }
    return "";
  }

  /* ---------- 会话切换 ---------- */
  function selectConv(key) {
    current = key;
    document.querySelectorAll(".conv-item").forEach((el) => {
      el.classList.toggle("active", el.dataset.key === key);
    });
    renderMessages();
  }

  /* ---------- 发送 ---------- */
  function sendText(text) {
    if (!current) { toast("请先选择会话"); return; }
    const payload = { kind: "text", text: text.slice(0, 2000) };
    ws.send(JSON.stringify({ type: "chat", to: current, payload }));
  }

  function sendFile(file) {
    if (!current) { toast("请先选择会话"); return; }
    const to = current;
    if (file.size > 50 * 1024 * 1024) { toast("文件超过 50MB 限制"); return; }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result;
      const b64 = String(dataUrl).split(",")[1] || "";
      toast("上传中…");
      fetch("/api/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: file.name, data: b64 }),
      })
        .then((r) => r.json())
        .then((d) => {
          if (!d.ok) { toast(d.msg || "上传失败"); return; }
          ws.send(JSON.stringify({
            type: "chat",
            to: to,
            payload: { kind: "file", url: d.url, name: d.name, size: d.size, type: d.type },
          }));
          toast("发送成功");
        })
        .catch(() => toast("上传失败，请重试"));
    };
    reader.readAsDataURL(file);
  }

  /* ---------- 截图 / 粘贴 ---------- */
  function tsName() {
    const d = new Date();
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
  }

  function onPaste(e) {
    const items = e.clipboardData && e.clipboardData.items;
    if (!items) return;
    let file = null;
    for (const it of items) {
      if (it.kind === "file") {
        const f = it.getAsFile();
        if (f) { file = f; break; }
      }
    }
    if (!file) return; // 纯文本粘贴走默认行为
    e.preventDefault();
    if (/^image\//.test(file.type)) {
      const name = file.name && file.name !== "image.png" ? file.name : "截图_" + tsName() + ".png";
      sendFile(new File([file], name, { type: file.type }));
    } else {
      sendFile(file);
    }
  }

  async function screenCapture() {
    if (!current) { toast("请先选择会话"); return; }
    const md = navigator.mediaDevices;
    if (md && md.getDisplayMedia) {
      let stream = null;
      try {
        stream = await md.getDisplayMedia({ video: true });
        const video = document.createElement("video");
        video.srcObject = stream;
        video.muted = true;
        await video.play();
        await new Promise((r) => setTimeout(r, 300));
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext("2d").drawImage(video, 0, 0);
        const blob = await new Promise((r) => canvas.toBlob(r, "image/png"));
        stream.getTracks().forEach((t) => t.stop());
        stream = null;
        if (blob) {
          sendFile(new File([blob], "截图_" + tsName() + ".png", { type: "image/png" }));
          return;
        }
      } catch (err) {
        if (stream) stream.getTracks().forEach((t) => t.stop());
      }
    }
    toast("当前环境无法直接截屏：请按 Win+Shift+S 截图，再回到输入框 Ctrl+V 粘贴发送");
  }

  /* ---------- 图片预览灯箱（滚轮缩放 + 拖动） ---------- */
  const lb = {
    scale: 1, x: 0, y: 0,
    minScale: 0.2, maxScale: 12,
    dragging: false, dragStartX: 0, dragStartY: 0, dragFromX: 0, dragFromY: 0,
  };

  function lbApply(animate) {
    const img = $("lightboxImg");
    img.style.transition = animate ? "transform .15s ease-out" : "none";
    img.style.transform = `translate(${lb.x}px, ${lb.y}px) scale(${lb.scale})`;
    img.style.cursor = lb.scale > 1 ? "grab" : "default";
  }

  function lbReset(animate) {
    lb.scale = 1; lb.x = 0; lb.y = 0;
    lbApply(animate);
  }

  function lbZoomAt(clientX, clientY, factor) {
    const newScale = Math.min(lb.maxScale, Math.max(lb.minScale, lb.scale * factor));
    if (newScale === lb.scale) return;
    // 以鼠标位置为缩放中心：保持鼠标下的图像点不动
    const img = $("lightboxImg");
    const rect = img.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const k = newScale / lb.scale;
    lb.x = clientX - (clientX - (cx + lb.x)) * k - cx;
    lb.y = clientY - (clientY - (cy + lb.y)) * k - cy;
    lb.scale = newScale;
    lbApply(false);
  }

  function openLightbox(url, alt) {
    $("lightboxImg").src = url;
    $("lightboxImg").alt = alt || "";
    $("lightbox").classList.remove("hidden");
    document.body.style.overflow = "hidden";
    lbReset(false);
  }

  function closeLightbox() {
    $("lightbox").classList.add("hidden");
    $("lightboxImg").src = "";
    document.body.style.overflow = "";
  }

  /* ---------- 事件绑定 ---------- */
  function bindEvents() {
    $("loginBtn").addEventListener("click", doLogin);
    $("loginName").addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
    $("loginPwd").addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });

    $("convList").addEventListener("click", (e) => {
      const item = e.target.closest(".conv-item");
      if (item) selectConv(item.dataset.key);
    });

    $("sendBtn").addEventListener("click", () => doSend());
    $("msgInput").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); doSend(); }
    });

    $("fileInput").addEventListener("change", (e) => {
      const f = e.target.files && e.target.files[0];
      if (f) sendFile(f);
      e.target.value = "";
    });

    $("shotBtn").addEventListener("click", () => screenCapture());
    $("msgInput").addEventListener("paste", onPaste);

    $("msgList").addEventListener("click", (e) => {
      const img = e.target.closest(".msg-img");
      if (img) openLightbox(img.src, img.alt);
    });

    const lbEl = $("lightbox");
    const lbImg = $("lightboxImg");

    lbEl.addEventListener("click", (e) => {
      // 点击空白处关闭；图片本身不冒泡关闭（拖动/双击另行处理）
      if (e.target !== lbImg) closeLightbox();
    });

    // 滚轮缩放（以鼠标为中心）
    lbEl.addEventListener("wheel", (e) => {
      e.preventDefault();
      lbZoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.2 : 1 / 1.2);
    }, { passive: false });

    // 按住拖动（仅放大后）
    lbImg.addEventListener("mousedown", (e) => {
      if (lb.scale <= 1) return;
      e.preventDefault();
      lb.dragging = true;
      lb.dragStartX = e.clientX; lb.dragStartY = e.clientY;
      lb.dragFromX = lb.x; lb.dragFromY = lb.y;
      lbImg.style.cursor = "grabbing";
    });
    document.addEventListener("mousemove", (e) => {
      if (!lb.dragging) return;
      lb.x = lb.dragFromX + (e.clientX - lb.dragStartX);
      lb.y = lb.dragFromY + (e.clientY - lb.dragStartY);
      lbApply(false);
    });
    document.addEventListener("mouseup", () => {
      if (!lb.dragging) return;
      lb.dragging = false;
      lbImg.style.cursor = lb.scale > 1 ? "grab" : "default";
    });

    // 双击图片：复位 / 放大到 2 倍
    lbImg.addEventListener("dblclick", (e) => {
      if (lb.scale === 1) {
        lb.scale = 2;
        lb.x = 0; lb.y = 0;
        lbApply(true);
      } else {
        lbReset(true);
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !lbEl.classList.contains("hidden")) closeLightbox();
    });

    $("logoutBtn").addEventListener("click", () => {
      if (ws) { ws.onclose = null; ws.close(); }
      me = ""; ws = null; current = null;
      $("loginPage").classList.remove("hidden");
      $("chatPage").classList.add("hidden");
    });
  }

  function doSend() {
    const text = $("msgInput").value.trim();
    if (!text) return;
    sendText(text);
    $("msgInput").value = "";
  }

  function doLogin() {
    const name = $("loginName").value.trim();
    const pwd = $("loginPwd").value;
    if (!name) { $("loginMsg").textContent = "请输入用户名"; return; }
    fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: name, password: pwd }),
    })
      .then((r) => r.json())
      .then((d) => {
        if (!d.ok) { $("loginMsg").textContent = d.msg || "登录失败"; return; }
        me = d.username;
        $("loginPage").classList.add("hidden");
        $("chatPage").classList.remove("hidden");
        $("myName").textContent = me;
        current = null;
        allMsgs = [];
        refreshSidebar();
        connectWS();
      })
      .catch(() => { $("loginMsg").textContent = "无法连接服务器"; });
  }

  bindEvents();
})();
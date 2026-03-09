const state = {
  session: null,
  socket: null,
  requestId: 0,
  pending: new Map(),
  sessionKey: "main",
};

const el = {
  landing: document.getElementById("landing"),
  summary: document.getElementById("summary"),
  status: document.getElementById("status"),
  deployButton: document.getElementById("deploy-button"),
  chatShell: document.getElementById("chat-shell"),
  messages: document.getElementById("messages"),
  prompt: document.getElementById("prompt"),
  composer: document.getElementById("composer"),
  sendButton: document.getElementById("send-button"),
  resumeButton: document.getElementById("resume-button"),
  connection: document.getElementById("connection"),
  tenantName: document.getElementById("tenant-name"),
  tenantMeta: document.getElementById("tenant-meta"),
};

function toSameOriginPath(path) {
  if (typeof path !== "string" || !path.startsWith("/")) {
    throw new Error("Expected a same-origin absolute path");
  }
  const url = new URL(path, window.location.origin);
  if (url.origin !== window.location.origin) {
    throw new Error("Cross-origin requests are not allowed");
  }
  return `${url.pathname}${url.search}`;
}

async function fetchJson(path, init) {
  const response = await fetch(toSameOriginPath(path), {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

function setStatus(message) {
  el.status.textContent = message;
}

function addMessage(role, text) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.textContent = text;
  el.messages.appendChild(node);
  el.messages.scrollTop = el.messages.scrollHeight;
}

function normalizeText(entry) {
  if (!entry || typeof entry !== "object") return "";
  if (typeof entry.text === "string") return entry.text;
  if (Array.isArray(entry.content)) {
    return entry.content
      .map((part) => (part && typeof part.text === "string" ? part.text : ""))
      .filter(Boolean)
      .join("\n\n");
  }
  return "";
}

function renderHistory(messages) {
  el.messages.innerHTML = "";
  for (const message of messages || []) {
    addMessage(message.role === "user" ? "user" : "assistant", normalizeText(message));
  }
}

function nextRequestId() {
  state.requestId += 1;
  return `octw-${state.requestId}`;
}

function sendRpc(method, params = {}) {
  if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
    throw new Error("WebSocket not connected");
  }
  const id = nextRequestId();
  const payload = { type: "req", id, method, params };
  state.socket.send(JSON.stringify(payload));
  return new Promise((resolve, reject) => {
    state.pending.set(id, { resolve, reject });
    window.setTimeout(() => {
      if (state.pending.has(id)) {
        state.pending.delete(id);
        reject(new Error(`Timed out waiting for ${method}`));
      }
    }, 15000);
  });
}

async function loadHistory() {
  const response = await sendRpc("chat.history", { sessionKey: state.sessionKey, limit: 100 });
  renderHistory(response.messages || []);
}

async function connectChat() {
  if (!state.session?.tenant) return;
  if (state.socket && (state.socket.readyState === WebSocket.OPEN || state.socket.readyState === WebSocket.CONNECTING)) {
    return;
  }
  const url = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/t/${state.session.tenant.slug}/ws`;
  const socket = new WebSocket(url);
  state.socket = socket;
  el.connection.textContent = "Connecting";
  let connectSent = false;

  const sendConnect = () => {
    if (connectSent || socket.readyState !== WebSocket.OPEN) return;
    connectSent = true;
    socket.send(JSON.stringify({
      type: "req",
      id: nextRequestId(),
      method: "connect",
      params: {
        minProtocol: 3,
        maxProtocol: 3,
        client: { id: "control-ui", version: "octw-web", platform: "web", mode: "webchat" },
        role: "operator",
        scopes: ["operator.read", "operator.write", "operator.admin"],
        caps: [],
        commands: [],
        permissions: {},
        locale: navigator.language,
        userAgent: navigator.userAgent,
      },
    }));
  };

  socket.addEventListener("open", () => {
    el.connection.textContent = "Authorizing";
    window.setTimeout(sendConnect, 700);
  });

  socket.addEventListener("message", async (event) => {
    const frame = JSON.parse(event.data);
    if (frame.type === "event" && frame.event === "connect.challenge") {
      sendConnect();
      return;
    }
    if (frame.type === "res") {
      const pending = state.pending.get(frame.id);
      if (pending) {
        state.pending.delete(frame.id);
        if (frame.ok) pending.resolve(frame.payload || {});
        else pending.reject(new Error(frame.error?.message || "Gateway error"));
      }
      if (frame.ok && frame.payload?.type === "hello-ok") {
        el.connection.textContent = "Connected";
        await loadHistory();
      }
      return;
    }
    if (frame.type === "event" && frame.event === "chat") {
      await loadHistory();
    }
  });

  socket.addEventListener("close", () => {
    el.connection.textContent = "Disconnected";
    state.socket = null;
  });
}

async function bootstrap() {
  try {
    state.session = await fetchJson("/api/v1/app/session");
  } catch (error) {
    setStatus(`Authentication failed: ${error.message}`);
    return;
  }

  if (!state.session.tenant) {
    el.summary.textContent = `Signed in as ${state.session.email}. Create your dedicated OpenClaw workspace.`;
    el.deployButton.hidden = false;
    return;
  }

  el.landing.hidden = true;
  el.chatShell.hidden = false;
  el.tenantName.textContent = state.session.tenant.slug;
  el.tenantMeta.textContent = `${state.session.email} · ${state.session.tenant.status} · ${state.session.tenant.verification_status}`;
  await connectChat();
}

el.deployButton.addEventListener("click", async () => {
  el.deployButton.disabled = true;
  setStatus("Provisioning your workspace. This can take a minute or two.");
  try {
    const response = await fetchJson("/api/v1/app/deploy-or-resume", { method: "POST", body: "{}" });
    state.session = { ...state.session, tenant: response.tenant };
    await bootstrap();
    setStatus(response.created ? "Workspace ready." : "Workspace resumed.");
  } catch (error) {
    setStatus(`Provisioning failed: ${error.message}`);
  } finally {
    el.deployButton.disabled = false;
  }
});

el.resumeButton.addEventListener("click", async () => {
  setStatus("Resuming workspace.");
  try {
    const response = await fetchJson("/api/v1/app/deploy-or-resume", { method: "POST", body: "{}" });
    state.session = { ...state.session, tenant: response.tenant };
    await connectChat();
    await loadHistory();
    setStatus("Workspace connected.");
  } catch (error) {
    setStatus(`Resume failed: ${error.message}`);
  }
});

el.composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = el.prompt.value.trim();
  if (!message) return;
  el.prompt.value = "";
  addMessage("user", message);
  addMessage("system", "Running...");
  try {
    await sendRpc("chat.send", {
      sessionKey: state.sessionKey,
      message,
      deliver: false,
      idempotencyKey: nextRequestId(),
    });
  } catch (error) {
    addMessage("system", `Send failed: ${error.message}`);
  }
});

bootstrap();

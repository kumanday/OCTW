const state = {
  session: null,
  socket: null,
  requestId: 0,
  pending: new Map(),
  sessionKey: "main",
  locale: "en",
};

const el = {
  heroEyebrow: document.getElementById("hero-eyebrow"),
  heroTitle: document.getElementById("hero-title"),
  landing: document.getElementById("landing"),
  summary: document.getElementById("summary"),
  status: document.getElementById("status"),
  deployButton: document.getElementById("deploy-button"),
  activity: document.getElementById("activity"),
  activityLabel: document.getElementById("activity-label"),
  chatShell: document.getElementById("chat-shell"),
  workspaceEyebrow: document.getElementById("workspace-eyebrow"),
  messages: document.getElementById("messages"),
  prompt: document.getElementById("prompt"),
  composer: document.getElementById("composer"),
  sendButton: document.getElementById("send-button"),
  resumeButton: document.getElementById("resume-button"),
  connection: document.getElementById("connection"),
  tenantName: document.getElementById("tenant-name"),
  tenantMeta: document.getElementById("tenant-meta"),
};

const STRINGS = {
  en: {
    appTitle: "OCTW Chat",
    heroEyebrow: "OpenClaw Tenant Wrapper",
    heroTitle: "Deploy once. Resume straight into chat.",
    checkingWorkspace: "Checking your workspace.",
    deployWorkspace: "Deploy Workspace",
    working: "Working",
    workspace: "Workspace",
    chat: "Chat",
    resumeWake: "Resume / Wake",
    promptPlaceholder: "Ask OpenClaw to do something useful.",
    disconnected: "Disconnected",
    connecting: "Connecting",
    authorizing: "Authorizing",
    connected: "Connected",
    send: "Send",
    signedInSummary: "Signed in as {email}. Create your dedicated OpenClaw workspace.",
    tenantMeta: "{status} · {verification}",
    status_running: "running",
    status_paused: "paused",
    status_stopped: "stopped",
    status_error: "error",
    status_provisioning: "provisioning",
    verification_verified: "verified",
    verification_pending: "pending",
    verification_failed: "failed",
    authFailed: "Authentication failed: {message}",
    provisioningActivity: "Provisioning your workspace. This can take a minute or two.",
    workspaceReady: "Workspace ready.",
    workspaceResumed: "Workspace resumed.",
    provisioningFailed: "Provisioning failed: {message}",
    wakingWorkspace: "Waking your workspace.",
    workspaceConnected: "Workspace connected.",
    resumeFailed: "Resume failed: {message}",
    running: "Running...",
    sendFailed: "Send failed: {message}",
    timedOutWaiting: "Timed out waiting for {method}",
    websocketNotConnected: "WebSocket not connected",
    gatewayError: "Gateway error",
  },
  es: {
    appTitle: "Chat de OCTW",
    heroEyebrow: "OpenClaw Tenant Wrapper",
    heroTitle: "Despliega una vez. Retoma directo en el chat.",
    checkingWorkspace: "Revisando tu espacio de trabajo.",
    deployWorkspace: "Desplegar espacio",
    working: "Procesando",
    workspace: "Espacio de trabajo",
    chat: "Chat",
    resumeWake: "Reanudar / Activar",
    promptPlaceholder: "Pídele a OpenClaw que haga algo útil.",
    disconnected: "Desconectado",
    connecting: "Conectando",
    authorizing: "Autorizando",
    connected: "Conectado",
    send: "Enviar",
    signedInSummary: "Sesión iniciada como {email}. Crea tu espacio dedicado de OpenClaw.",
    tenantMeta: "{status} · {verification}",
    status_running: "activo",
    status_paused: "pausado",
    status_stopped: "detenido",
    status_error: "error",
    status_provisioning: "provisionando",
    verification_verified: "verificado",
    verification_pending: "pendiente",
    verification_failed: "fallido",
    authFailed: "Error de autenticación: {message}",
    provisioningActivity: "Provisionando tu espacio. Esto puede tardar uno o dos minutos.",
    workspaceReady: "Espacio listo.",
    workspaceResumed: "Espacio reanudado.",
    provisioningFailed: "Falló el provisionamiento: {message}",
    wakingWorkspace: "Activando tu espacio.",
    workspaceConnected: "Espacio conectado.",
    resumeFailed: "Falló la reanudación: {message}",
    running: "Ejecutando...",
    sendFailed: "Falló el envío: {message}",
    timedOutWaiting: "Tiempo de espera agotado para {method}",
    websocketNotConnected: "WebSocket no conectado",
    gatewayError: "Error del gateway",
  },
};

function resolveLocale() {
  const query = new URLSearchParams(window.location.search).get("lang");
  if (query) {
    const normalized = query.toLowerCase();
    if (normalized.startsWith("es")) return "es";
    if (normalized.startsWith("en")) return "en";
  }
  const raw = (navigator.language || "en").toLowerCase();
  if (raw.startsWith("es")) return "es";
  return "en";
}

function t(key, vars = {}) {
  const strings = STRINGS[state.locale] || STRINGS.en;
  const template = strings[key] || STRINGS.en[key] || key;
  return template.replace(/\{(\w+)\}/g, (_, name) => `${vars[name] ?? ""}`);
}

function applyLocale() {
  state.locale = resolveLocale();
  document.documentElement.lang = state.locale;
  document.title = t("appTitle");
  el.heroEyebrow.textContent = t("heroEyebrow");
  el.heroTitle.textContent = t("heroTitle");
  el.summary.textContent = t("checkingWorkspace");
  el.deployButton.textContent = t("deployWorkspace");
  el.activityLabel.textContent = t("working");
  el.workspaceEyebrow.textContent = t("workspace");
  el.tenantName.textContent = t("chat");
  el.resumeButton.textContent = t("resumeWake");
  el.prompt.placeholder = t("promptPlaceholder");
  el.connection.textContent = t("disconnected");
  el.sendButton.textContent = t("send");
}

function localizeTenantState(value, prefix) {
  const key = `${prefix}_${String(value || "").toLowerCase()}`;
  return STRINGS[state.locale][key] || STRINGS.en[key] || value;
}

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
  const visible = Boolean(message);
  el.status.hidden = !visible;
  el.status.textContent = message;
}

function setActivity(message = "") {
  const active = Boolean(message);
  el.activity.hidden = !active;
  el.activityLabel.textContent = message || t("working");
  el.deployButton.disabled = active;
  el.resumeButton.disabled = active;
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
    throw new Error(t("websocketNotConnected"));
  }
  const id = nextRequestId();
  const payload = { type: "req", id, method, params };
  state.socket.send(JSON.stringify(payload));
  return new Promise((resolve, reject) => {
    state.pending.set(id, { resolve, reject });
    window.setTimeout(() => {
      if (state.pending.has(id)) {
        state.pending.delete(id);
        reject(new Error(t("timedOutWaiting", { method })));
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
  el.connection.textContent = t("connecting");
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
        client: {
          id: "openclaw-control-ui",
          version: "control-ui",
          platform: navigator.platform || "web",
          mode: "webchat",
        },
        role: "operator",
        scopes: ["operator.admin", "operator.approvals", "operator.pairing"],
        caps: ["tool-events"],
        locale: navigator.language,
        userAgent: navigator.userAgent,
      },
    }));
  };

  socket.addEventListener("open", () => {
    el.connection.textContent = t("authorizing");
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
        else pending.reject(new Error(frame.error?.message || t("gatewayError")));
      }
      if (frame.ok && frame.payload?.type === "hello-ok") {
        el.connection.textContent = t("connected");
        await loadHistory();
      }
      return;
    }
    if (frame.type === "event" && frame.event === "chat") {
      await loadHistory();
    }
  });

  socket.addEventListener("close", () => {
    el.connection.textContent = t("disconnected");
    state.socket = null;
  });
}

async function bootstrap() {
  try {
    state.session = await fetchJson("/api/v1/app/session");
  } catch (error) {
    setStatus(t("authFailed", { message: error.message }));
    return;
  }

  if (!state.session.tenant) {
    el.summary.textContent = t("signedInSummary", { email: state.session.email });
    el.deployButton.hidden = false;
    setActivity("");
    return;
  }

  el.landing.hidden = true;
  el.chatShell.hidden = false;
  el.tenantName.textContent = state.session.email;
  el.tenantMeta.textContent = t("tenantMeta", {
    status: localizeTenantState(state.session.tenant.status, "status"),
    verification: localizeTenantState(state.session.tenant.verification_status, "verification"),
  });
  setActivity("");
  await connectChat();
}

el.deployButton.addEventListener("click", async () => {
  setActivity(t("provisioningActivity"));
  setStatus("");
  try {
    const response = await fetchJson("/api/v1/app/deploy-or-resume", { method: "POST", body: "{}" });
    state.session = { ...state.session, tenant: response.tenant };
    await bootstrap();
    setStatus(response.created ? t("workspaceReady") : t("workspaceResumed"));
  } catch (error) {
    setStatus(t("provisioningFailed", { message: error.message }));
  } finally {
    setActivity("");
  }
});

el.resumeButton.addEventListener("click", async () => {
  setActivity(t("wakingWorkspace"));
  setStatus("");
  try {
    const response = await fetchJson("/api/v1/app/deploy-or-resume", { method: "POST", body: "{}" });
    state.session = { ...state.session, tenant: response.tenant };
    await connectChat();
    await loadHistory();
    setStatus(t("workspaceConnected"));
  } catch (error) {
    setStatus(t("resumeFailed", { message: error.message }));
  } finally {
    setActivity("");
  }
});

el.composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = el.prompt.value.trim();
  if (!message) return;
  el.prompt.value = "";
  addMessage("user", message);
  addMessage("system", t("running"));
  try {
    await sendRpc("chat.send", {
      sessionKey: state.sessionKey,
      message,
      deliver: false,
      idempotencyKey: nextRequestId(),
    });
  } catch (error) {
    addMessage("system", t("sendFailed", { message: error.message }));
  }
});

applyLocale();
bootstrap();

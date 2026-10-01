import { ERROR_CODE, SmartFlowBridgeError, serialiseError } from "./errors.js";

export class LocalWebSocketTransport {
  constructor({
    url,
    pairingTokenProvider,
    onJob,
    logger = null,
    heartbeatMs = 15000,
    maxBackoffMs = 30000
  } = {}) {
    const parsed = new URL(String(url || ""));
    if (parsed.protocol !== "ws:" || !["127.0.0.1", "localhost", "[::1]"].includes(parsed.hostname)) {
      throw new SmartFlowBridgeError(ERROR_CODE.SECURITY_REJECTED, "WebSocket bridge must use localhost");
    }
    this.url = parsed.href;
    this.pairingTokenProvider = pairingTokenProvider;
    this.onJob = onJob;
    this.logger = logger;
    this.heartbeatMs = Math.max(5000, Number(heartbeatMs));
    this.maxBackoffMs = Math.max(2000, Number(maxBackoffMs));
    this.socket = null;
    this.reconnectTimer = null;
    this.heartbeatTimer = null;
    this.attempt = 0;
    this.running = false;
    this.completed = new Map();
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.connect();
  }

  stop() {
    this.running = false;
    clearTimeout(this.reconnectTimer);
    clearInterval(this.heartbeatTimer);
    this.reconnectTimer = null;
    this.heartbeatTimer = null;
    this.socket?.close();
    this.socket = null;
  }

  scheduleReconnect() {
    if (!this.running || this.reconnectTimer) return;
    const base = Math.min(this.maxBackoffMs, 1000 * (2 ** Math.min(this.attempt, 5)));
    const jitter = Math.floor(Math.random() * Math.max(200, base * 0.2));
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, base + jitter);
  }

  async connect() {
    if (!this.running || this.socket?.readyState === WebSocket.OPEN || this.socket?.readyState === WebSocket.CONNECTING) return;
    this.attempt += 1;
    const socket = new WebSocket(this.url);
    this.socket = socket;
    socket.addEventListener("open", async () => {
      this.attempt = 0;
      const pairingToken = await this.pairingTokenProvider?.();
      if (!pairingToken) {
        socket.close(1008, "pairing required");
        return;
      }
      this.send({
        type: "pair",
        nonce: crypto.randomUUID(),
        pairingToken,
        extensionVersion: chrome.runtime.getManifest().version
      });
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = setInterval(() => this.send({ type: "ping", at: Date.now() }), this.heartbeatMs);
      this.logger?.info("bridge_connected");
    });
    socket.addEventListener("message", (event) => this.handleMessage(event.data));
    socket.addEventListener("close", () => {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
      if (this.socket === socket) this.socket = null;
      this.scheduleReconnect();
    });
    socket.addEventListener("error", () => socket.close());
  }

  send(message) {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify(message));
    return true;
  }

  async handleMessage(raw) {
    let message = null;
    try { message = JSON.parse(String(raw || "")); } catch { return; }
    if (!message || message.type !== "job" || typeof message.id !== "string" || typeof message.action !== "string") return;
    if (this.completed.has(message.id)) {
      this.send(this.completed.get(message.id));
      return;
    }
    let result = null;
    try {
      const data = await this.onJob?.(message);
      result = { type: "result", id: message.id, ok: true, data: data || {} };
    } catch (error) {
      result = { type: "result", id: message.id, ok: false, error: serialiseError(error) };
    }
    this.completed.set(message.id, result);
    if (this.completed.size > 200) this.completed.delete(this.completed.keys().next().value);
    this.send(result);
  }
}

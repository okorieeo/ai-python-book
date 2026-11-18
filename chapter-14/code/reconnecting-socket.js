// A WebSocket wrapper that reconnects with exponential backoff, queues messages while offline,
// and sends heartbeats. Works in browsers and React Native (pass a different createSocket if needed).

const FATAL_CLOSE_CODES = new Set([4401, 4403]); // unauthorized / forbidden: retrying will not help

export class ReconnectingSocket {
  constructor({
    url, // string, or a function returning a string (or a Promise of one) so tickets can be refreshed
    onMessage = () => {},
    onStatus = () => {},
    createSocket = (u) => new WebSocket(u),
    baseDelayMs = 500,
    maxDelayMs = 15000,
    heartbeatMs = 25000,
    pongTimeoutMs = 10000,
    maxQueue = 50,
    random = Math.random,
    timers = { setTimeout, clearTimeout, setInterval, clearInterval },
  }) {
    Object.assign(this, { url, onMessage, onStatus, createSocket, baseDelayMs, maxDelayMs, heartbeatMs,
      pongTimeoutMs, maxQueue, random, timers });
    this.socket = null;
    this.attempt = 0;
    this.queue = [];
    this.status = "idle";
    this.wantOpen = false;
    this.retryTimer = null;
    this.heartbeatTimer = null;
    this.pongTimer = null;
  }

  connect() {
    this.wantOpen = true;
    this._open();
  }

  close() {
    this.wantOpen = false;
    this.timers.clearTimeout(this.retryTimer);
    this._stopHeartbeat();
    if (this.socket) this.socket.close(1000);
    this._setStatus("closed");
  }

  /** Send an object. If the socket is not open yet, keep it (up to maxQueue) and send after reconnecting. */
  send(message) {
    if (this.socket && this.socket.readyState === 1) {
      this.socket.send(JSON.stringify(message));
      return true;
    }
    if (this.queue.length >= this.maxQueue) return false;
    this.queue.push(message);
    return true;
  }

  async _open() {
    this._setStatus(this.attempt === 0 ? "connecting" : "reconnecting");
    let url;
    try {
      url = typeof this.url === "function" ? await this.url() : this.url;
    } catch {
      return this._scheduleRetry();
    }
    if (!this.wantOpen) return;
    const socket = this.createSocket(url);
    this.socket = socket;
    socket.onopen = () => {
      this.attempt = 0;
      this._setStatus("open");
      this._startHeartbeat();
      const pending = this.queue.splice(0);
      pending.forEach((m) => this.send(m));
    };
    socket.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      if (message.type === "pong") {
        this.timers.clearTimeout(this.pongTimer);
        return;
      }
      this.onMessage(message);
    };
    socket.onclose = (event) => {
      this._stopHeartbeat();
      if (!this.wantOpen) return;
      if (FATAL_CLOSE_CODES.has(event.code)) {
        this.wantOpen = false;
        this._setStatus("unauthorized");
        return;
      }
      this._scheduleRetry();
    };
    socket.onerror = () => {}; // an error is always followed by a close event
  }

  _scheduleRetry() {
    const ceiling = Math.min(this.maxDelayMs, this.baseDelayMs * 2 ** this.attempt);
    const delay = Math.round(this.random() * ceiling); // "full jitter": spreads reconnects over time
    this.attempt += 1;
    this._setStatus("reconnecting");
    this.retryTimer = this.timers.setTimeout(() => this._open(), delay);
  }

  _startHeartbeat() {
    this._stopHeartbeat();
    this.heartbeatTimer = this.timers.setInterval(() => {
      this.send({ type: "ping" });
      this.timers.clearTimeout(this.pongTimer);
      this.pongTimer = this.timers.setTimeout(() => this.socket && this.socket.close(4000), this.pongTimeoutMs);
    }, this.heartbeatMs);
  }

  _stopHeartbeat() {
    this.timers.clearInterval(this.heartbeatTimer);
    this.timers.clearTimeout(this.pongTimer);
  }

  _setStatus(status) {
    if (status !== this.status) {
      this.status = status;
      this.onStatus(status);
    }
  }
}

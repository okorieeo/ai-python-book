// Needs: npm i -D ws @types/ws   (and Node 22+, which has a global WebSocket)
import { afterEach, describe, expect, it } from "vitest";
import { WebSocketServer, type WebSocket as ServerSocket } from "ws";
import { FatalSocketError, ReconnectingSocket, type ConnectionStatus } from "./socket";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
async function waitFor(check: () => boolean, ms = 3000) {
  const end = Date.now() + ms;
  while (!check()) {
    if (Date.now() > end) throw new Error("timed out waiting for condition");
    await sleep(10);
  }
}

let servers: WebSocketServer[] = [];
let sockets: ReconnectingSocket[] = [];
afterEach(async () => {
  sockets.forEach((s) => s.disconnect());
  await Promise.all(servers.map((s) => new Promise((r) => { s.clients.forEach((c) => c.terminate()); s.close(r); })));
  servers = []; sockets = [];
});

function startServer(port = 0) {
  const tickets: string[] = [];
  const clients: ServerSocket[] = [];
  const wss = new WebSocketServer({ port });
  servers.push(wss);
  wss.on("connection", (client, request) => {
    tickets.push(new URL(request.url ?? "", "ws://x").searchParams.get("ticket") ?? "");
    clients.push(client);
    client.on("message", (raw: unknown) => {
      if (JSON.parse(String(raw)).type === "ping") client.send('{"type":"pong"}');
    });
  });
  return new Promise<{ port: number; tickets: string[]; clients: ServerSocket[]; wss: WebSocketServer }>((resolve) =>
    wss.on("listening", () => resolve({ port: (wss.address() as { port: number }).port, tickets, clients, wss })),
  );
}

function makeClient(port: number, extra: Partial<ConstructorParameters<typeof ReconnectingSocket>[0]> = {}) {
  const statuses: ConnectionStatus[] = [];
  const messages: unknown[] = [];
  let n = 0;
  const socket = new ReconnectingSocket({
    url: `ws://127.0.0.1:${port}/ws/chat/`,
    getTicket: async () => `t${++n}`,
    onMessage: (d) => messages.push(d),
    onStatus: (s) => statuses.push(s),
    baseDelayMs: 20, maxDelayMs: 80, stableMs: 100,
    ...extra,
  });
  sockets.push(socket);
  return { socket, statuses, messages };
}

describe("ReconnectingSocket against a real WebSocket server", () => {
  it("connects with a ticket and exchanges messages", async () => {
    const server = await startServer();
    const { socket, messages } = makeClient(server.port);
    socket.connect();
    await waitFor(() => socket.currentStatus === "open");
    expect(server.tickets).toEqual(["t1"]);
    socket.send('{"type":"ping"}');
    await waitFor(() => messages.length === 1);
    expect(messages).toEqual(['{"type":"pong"}']);
  });

  it("reconnects with a fresh ticket after the server drops the connection", async () => {
    const server = await startServer();
    const { socket, statuses } = makeClient(server.port);
    socket.connect();
    await waitFor(() => socket.currentStatus === "open");
    server.clients[0]!.terminate(); // abrupt drop, like a network failure
    await waitFor(() => server.tickets.length === 2);
    await waitFor(() => socket.currentStatus === "open");
    expect(server.tickets).toEqual(["t1", "t2"]);
    expect(statuses).toEqual(["connecting", "open", "reconnecting", "open"]);
  });

  it("keeps retrying while the server is down and connects when it returns", async () => {
    const first = await startServer();
    const port = first.port;
    const { socket } = makeClient(port);
    socket.connect();
    await waitFor(() => socket.currentStatus === "open");
    first.clients.forEach((c) => c.terminate());
    await new Promise((r) => first.wss.close(r)); // the server goes away entirely
    await sleep(250);                              // several failed attempts
    expect(socket.currentStatus).toBe("reconnecting");
    const second = await startServer(port);        // and comes back on the same port
    await waitFor(() => socket.currentStatus === "open");
    expect(second.tickets.length).toBe(1);
  });

  it("stops for good when the server closes with a fatal code", async () => {
    const server = await startServer();
    const { socket } = makeClient(server.port);
    socket.connect();
    await waitFor(() => socket.currentStatus === "open");
    server.clients[0]!.close(4403, "forbidden");
    await waitFor(() => socket.currentStatus === "closed");
    await sleep(200);
    expect(server.tickets).toHaveLength(1); // no reconnect attempts
  });

  it("stops when the ticket endpoint says the user is logged out", async () => {
    const server = await startServer();
    const { socket } = makeClient(server.port, {
      getTicket: async () => { throw new FatalSocketError("401"); },
    });
    socket.connect();
    await waitFor(() => socket.currentStatus === "closed");
    expect(server.tickets).toHaveLength(0);
  });

  it("heartbeat pings reach the server and the pongs keep the link alive", async () => {
    const server = await startServer();
    const { socket, messages } = makeClient(server.port, { heartbeatMs: 40, pongTimeoutMs: 200 });
    socket.connect();
    await waitFor(() => messages.length >= 2);
    expect(socket.currentStatus).toBe("open");
    expect(server.tickets).toHaveLength(1); // never needed to reconnect
  });

  it("detects a server that stops answering and reconnects", async () => {
    const server = await startServer();
    server.wss.on("connection", (client) => {
      client.removeAllListeners("message"); // goes silent: accepts but never replies
    });
    const { socket } = makeClient(server.port, { heartbeatMs: 40, pongTimeoutMs: 80 });
    socket.connect();
    await waitFor(() => server.tickets.length >= 2, 4000);
    expect(server.tickets.slice(0, 2)).toEqual(["t1", "t2"]);
  });
});

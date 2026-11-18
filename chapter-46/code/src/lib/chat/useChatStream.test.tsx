import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { backoffDelay, useChatStream, type SocketLike } from "./useChatStream";

class FakeSocket implements SocketLike {
  static instances: FakeSocket[] = [];
  readyState = 0;
  sent: string[] = [];
  closed = false;
  onopen: SocketLike["onopen"] = null;
  onmessage: SocketLike["onmessage"] = null;
  onclose: SocketLike["onclose"] = null;
  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.closed = true;
    this.readyState = 3;
  }
  // helpers the tests call, standing in for the network
  open() {
    this.readyState = 1;
    this.onopen?.({});
  }
  receive(frame: object | string) {
    this.onmessage?.({ data: typeof frame === "string" ? frame : JSON.stringify(frame) });
  }
  drop() {
    this.readyState = 3;
    this.onclose?.({});
  }
}

const setup = (resolveUrl = vi.fn(async () => "ws://test/ws?ticket=t1")) =>
  renderHook(() => useChatStream({ resolveUrl, socketFactory: (url) => new FakeSocket(url), newId: () => "u1" }));

beforeEach(() => {
  FakeSocket.instances = [];
  vi.useFakeTimers();
});
afterEach(() => vi.useRealTimers());

async function connected() {
  const hook = setup();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
  const socket = FakeSocket.instances[0]!;
  act(() => socket.open());
  return { hook, socket };
}

describe("useChatStream", () => {
  it("connects, sends a message and streams the reply", async () => {
    const { hook, socket } = await connected();
    expect(hook.result.current.connection).toBe("open");

    let accepted = false;
    act(() => {
      accepted = hook.result.current.send("  Hello  ");
    });
    expect(accepted).toBe(true);
    expect(JSON.parse(socket.sent[0]!)).toEqual({ type: "user_message", content: "Hello" });

    act(() => socket.receive({ type: "token", delta: "Hi" }));
    act(() => socket.receive({ type: "token", delta: "!" }));
    act(() => socket.receive({ type: "done", message_id: "m1" }));
    expect(hook.result.current.state.messages.map((m) => m.content)).toEqual(["Hello", "Hi!"]);
    expect(hook.result.current.state.status).toBe("idle");
  });

  it("refuses to send while a reply is streaming, and when the text is empty", async () => {
    const { hook, socket } = await connected();
    act(() => void hook.result.current.send("one"));
    let second = true;
    let empty = true;
    act(() => {
      second = hook.result.current.send("two");
    });
    expect(second).toBe(false);
    act(() => socket.receive({ type: "done", message_id: "m1" }));
    act(() => {
      empty = hook.result.current.send("   ");
    });
    expect(empty).toBe(false);
    expect(socket.sent).toHaveLength(1);
  });

  it("ignores malformed frames instead of crashing", async () => {
    const { hook, socket } = await connected();
    act(() => void hook.result.current.send("hi"));
    act(() => socket.receive("{broken"));
    act(() => socket.receive({ type: "surprise" }));
    act(() => socket.receive({ type: "token", delta: "ok" }));
    expect(hook.result.current.state.messages.at(-1)?.content).toBe("ok");
  });

  it("reconnects with a NEW ticket after the socket drops", async () => {
    const resolveUrl = vi.fn().mockResolvedValueOnce("ws://t/?ticket=1").mockResolvedValueOnce("ws://t/?ticket=2");
    const hook = setup(resolveUrl);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    act(() => FakeSocket.instances[0]!.open());

    act(() => FakeSocket.instances[0]!.drop());
    expect(hook.result.current.connection).toBe("reconnecting");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000); // first backoff is 500 to 1000 ms
    });
    expect(resolveUrl).toHaveBeenCalledTimes(2);
    expect(FakeSocket.instances[1]!.url).toBe("ws://t/?ticket=2");
    act(() => FakeSocket.instances[1]!.open());
    expect(hook.result.current.connection).toBe("open");
  });

  it("reports connection_lost if the socket drops mid-reply, and does not resend", async () => {
    const { hook, socket } = await connected();
    act(() => void hook.result.current.send("hi"));
    act(() => socket.receive({ type: "token", delta: "Par" }));
    act(() => socket.drop());
    expect(hook.result.current.state.error?.code).toBe("connection_lost");
    expect(hook.result.current.state.messages.at(-1)).toMatchObject({ content: "Par", pending: false });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(socket.sent).toHaveLength(1); // the paid request was not repeated
  });

  it("retries when fetching the ticket fails", async () => {
    const resolveUrl = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce("ws://t/?ticket=ok");
    const hook = setup(resolveUrl);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(hook.result.current.connection).toBe("reconnecting");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(FakeSocket.instances).toHaveLength(1);
    expect(FakeSocket.instances[0]!.url).toBe("ws://t/?ticket=ok");
  });

  it("closes the socket on unmount without scheduling a reconnect", async () => {
    const { hook, socket } = await connected();
    hook.unmount();
    expect(socket.closed).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(FakeSocket.instances).toHaveLength(1);
  });
});

describe("backoffDelay", () => {
  it("doubles, caps, and applies jitter between 50% and 100%", () => {
    expect(backoffDelay(0, {}, () => 1)).toBe(1000);
    expect(backoffDelay(0, {}, () => 0)).toBe(500);
    expect(backoffDelay(3, {}, () => 1)).toBe(8000);
    expect(backoffDelay(20, {}, () => 1)).toBe(30000);
  });
});

import type { FetchLike, ResponseLike } from "../src/apiClient";

export interface Scripted {
  status?: number;
  body?: unknown;
  text?: string;
  headers?: Record<string, string>;
  throws?: Error;
  /** Never answers: used to test timeouts. */
  hang?: boolean;
}

export interface Call {
  url: string;
  method: string;
  headers: Record<string, string>;
  body?: string;
  signal?: AbortSignal;
}

/** A fake fetch that plays back a script and records every request it receives. */
export class FakeFetch {
  calls: Call[] = [];
  constructor(private script: Array<Scripted | ((c: Call) => Scripted)>) {}

  fetch: FetchLike = (url, init) => {
    const call: Call = { url, method: init.method, headers: init.headers, body: init.body, signal: init.signal };
    this.calls.push(call);
    const next = this.script.shift();
    if (next === undefined) throw new Error(`Unexpected request #${this.calls.length}: ${init.method} ${url}`);
    const s = typeof next === "function" ? next(call) : next;
    if (s.throws) return Promise.reject(s.throws);
    if (s.hang) {
      return new Promise((_, reject) => {
        const abort = () => reject(Object.assign(new Error("aborted"), { name: "AbortError" }));
        if (init.signal?.aborted) return abort(); // the real fetch rejects at once for an already-aborted signal
        init.signal?.addEventListener("abort", abort);
      });
    }
    const text = s.text ?? (s.body === undefined ? "" : JSON.stringify(s.body));
    const headers = s.headers ?? {};
    const response: ResponseLike = {
      status: s.status ?? 200,
      headers: { get: (name: string) => headers[name] ?? headers[name.toLowerCase()] ?? null },
      text: async () => text,
    };
    return Promise.resolve(response);
  };
}

export async function flushPromises(times = 5): Promise<void> {
  for (let i = 0; i < times; i++) await Promise.resolve();
}

/** Wait for a promise that must reject, and return the error. Fails the test if it resolves. */
export async function rejection(promise: Promise<unknown>): Promise<any> {
  try {
    await promise;
  } catch (error) {
    return error;
  }
  throw new Error("Expected the promise to reject, but it resolved");
}

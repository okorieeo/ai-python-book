import { loadConfig } from "../src/config";
import { routeForNotification } from "../src/push";

describe("loadConfig", () => {
  const env = { EXPO_PUBLIC_API_URL: "https://api.example.com/", EXPO_PUBLIC_WS_URL: "wss://api.example.com" };

  test("reads both addresses and removes trailing slashes", () => {
    expect(loadConfig(env, "production")).toEqual({ apiUrl: "https://api.example.com", wsUrl: "wss://api.example.com" });
  });
  test("missing values are reported by name", () => {
    expect(() => loadConfig({ EXPO_PUBLIC_WS_URL: "wss://x" }, "development")).toThrow("EXPO_PUBLIC_API_URL");
    expect(() => loadConfig({ EXPO_PUBLIC_API_URL: "https://x" }, "development")).toThrow("EXPO_PUBLIC_WS_URL");
  });
  test("addresses must have the right scheme", () => {
    expect(() => loadConfig({ ...env, EXPO_PUBLIC_API_URL: "api.example.com" }, "development")).toThrow("http");
    expect(() => loadConfig({ ...env, EXPO_PUBLIC_WS_URL: "https://x" }, "development")).toThrow("ws");
  });
  test("development may use plain http and ws, production may not", () => {
    const dev = { EXPO_PUBLIC_API_URL: "http://192.168.1.20:8000", EXPO_PUBLIC_WS_URL: "ws://192.168.1.20:8000" };
    expect(loadConfig(dev, "development").apiUrl).toBe("http://192.168.1.20:8000");
    expect(() => loadConfig(dev, "production")).toThrow("https");
    expect(() => loadConfig({ ...dev, EXPO_PUBLIC_API_URL: "https://x" }, "production")).toThrow("wss");
  });
});

describe("routeForNotification", () => {
  test("known types become known routes", () => {
    expect(routeForNotification({ type: "chat_message", conversation_id: 42 })).toBe("/chat/42");
    expect(routeForNotification({ type: "chat_message", conversation_id: "42" })).toBe("/chat/42");
    expect(routeForNotification({ type: "invoice_paid", invoice_id: "7" })).toBe("/settings/billing/invoices/7");
    expect(routeForNotification({ type: "usage_limit" })).toBe("/settings/billing");
  });
  test("ids that are not plain digits are refused", () => {
    for (const bad of ["../../admin", "1/2", "12a", "", " 5", "-1", "1e3", 1.5, null, {}, "9".repeat(13)]) {
      expect(routeForNotification({ type: "chat_message", conversation_id: bad })).toBeNull();
    }
  });
  test("unknown types, missing fields and non-objects open nothing", () => {
    for (const bad of [{ type: "other" }, { conversation_id: 1 }, {}, null, undefined, "chat", 5, []]) {
      expect(routeForNotification(bad)).toBeNull();
    }
  });
  test("a url or path in the payload is ignored, never followed", () => {
    expect(routeForNotification({ type: "usage_limit", url: "https://evil.example", path: "/admin" })).toBe("/settings/billing");
    expect(routeForNotification({ type: "chat_message", conversation_id: 3, route: "/anything" })).toBe("/chat/3");
  });
});

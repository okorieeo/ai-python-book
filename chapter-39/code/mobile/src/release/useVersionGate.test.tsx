import { renderHook, waitFor } from "@testing-library/react-native";

import { useVersionGate } from "./useVersionGate";

jest.mock("expo-application", () => ({ nativeApplicationVersion: "1.2.0" }));
jest.mock("expo-constants", () => ({ __esModule: true, default: { expoConfig: { version: "1.2.0" } } }));

const policy = (over = {}) => ({ min_version: "1.0.0", recommended_version: "1.0.0", store_url: "https://store.example/app", maintenance: false, message: "", ...over });
const respond = (body: unknown, ok = true) => jest.fn().mockResolvedValue({ ok, status: ok ? 200 : 500, json: async () => body });

afterEach(() => { jest.restoreAllMocks(); });

describe("useVersionGate", () => {
  it("blocks an installed version that is below the server's minimum", async () => {
    global.fetch = respond(policy({ min_version: "1.3.0" })) as unknown as typeof fetch;
    const { result } = await renderHook(() => useVersionGate());        // awaiting is harmless where renderHook is synchronous
    await waitFor(() => expect(result.current.checked).toBe(true));
    expect(result.current.state.kind).toBe("blocked");
  });

  it("lets people in when the policy request fails: the gate fails OPEN", async () => {
    global.fetch = jest.fn().mockRejectedValue(new Error("offline")) as unknown as typeof fetch;
    const { result } = await renderHook(() => useVersionGate());
    await waitFor(() => expect(result.current.checked).toBe(true));
    expect(result.current.state.kind).toBe("ok");
  });

  it("lets people in on a server error too", async () => {
    global.fetch = respond({}, false) as unknown as typeof fetch;
    const { result } = await renderHook(() => useVersionGate());
    await waitFor(() => expect(result.current.checked).toBe(true));
    expect(result.current.state.kind).toBe("ok");
  });
});

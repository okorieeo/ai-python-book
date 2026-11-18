import { renderHook, act } from "@testing-library/react-native";
import { Share } from "react-native";
import { useShareLink } from "./useShareLink";

const created = { id: "l1", state: "active", created_at: "x", expires_at: null, view_count: 0, url: "https://app.example.com/s/abc" } as const;

describe("useShareLink", () => {
  beforeEach(() => jest.restoreAllMocks());

  it("AC-1 and AC-11: creates a 7 day link and opens the native share sheet", async () => {
    const shareSpy = jest.spyOn(Share, "share").mockResolvedValue({ action: "sharedAction" } as never);
    const api = { createShareLink: jest.fn().mockResolvedValue(created) };
    const { result } = renderHook(() => useShareLink(api, "c1"));
    await act(async () => { await result.current.share(); });
    expect(api.createShareLink).toHaveBeenCalledWith("c1", "7d");
    expect(shareSpy).toHaveBeenCalledWith({ message: created.url });
    expect(result.current.error).toBeNull();
  });

  it("AC-8: shows the server's message when the daily limit is hit and does not open the sheet", async () => {
    const shareSpy = jest.spyOn(Share, "share");
    const api = { createShareLink: jest.fn().mockRejectedValue(new Error("Too many links today. Try again tomorrow.")) };
    const { result } = renderHook(() => useShareLink(api, "c1"));
    await act(async () => { await result.current.share(); });
    expect(shareSpy).not.toHaveBeenCalled();
    expect(result.current.error).toBe("Too many links today. Try again tomorrow.");
  });
});

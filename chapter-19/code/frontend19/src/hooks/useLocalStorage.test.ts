import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useLocalStorage } from "./useLocalStorage";

describe("useLocalStorage", () => {
  it("returns the initial value when nothing is stored", () => {
    const { result } = renderHook(() => useLocalStorage("k", "start"));
    expect(result.current[0]).toBe("start");
  });

  it("reads an existing value", () => {
    window.localStorage.setItem("k", "saved");
    const { result } = renderHook(() => useLocalStorage("k", "start"));
    expect(result.current[0]).toBe("saved");
  });

  it("writes through to storage and re-renders", () => {
    const { result } = renderHook(() => useLocalStorage("k", ""));
    act(() => result.current[1]("hello"));
    expect(result.current[0]).toBe("hello");
    expect(window.localStorage.getItem("k")).toBe("hello");
  });

  it("keeps two hooks with the same key in sync", () => {
    const a = renderHook(() => useLocalStorage("shared", ""));
    const b = renderHook(() => useLocalStorage("shared", ""));
    act(() => a.result.current[1]("from a"));
    expect(b.result.current[0]).toBe("from a");
  });
});

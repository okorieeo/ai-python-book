import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("joins class names and skips falsy values", () => {
    expect(cn("a", false && "b", undefined, null, "c")).toBe("a c");
    expect(cn("a", { b: true, c: false })).toBe("a b");
  });

  it("lets the last conflicting Tailwind class win", () => {
    expect(cn("px-2 py-1", "px-4")).toBe("py-1 px-4");
    expect(cn("bg-primary text-sm", "bg-destructive")).toBe(
      "text-sm bg-destructive",
    );
  });

  it("keeps non-conflicting classes", () => {
    expect(cn("text-sm", "text-primary")).toBe("text-sm text-primary");
  });
});

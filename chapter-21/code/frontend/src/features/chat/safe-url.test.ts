import { describe, expect, it } from "vitest";
import { safeUrl } from "./safe-url";

describe("safeUrl", () => {
  it("allows normal links", () => {
    for (const url of ["https://example.com/a?b=1#c", "http://example.com", "mailto:a@b.co", "/docs/page", "#section", "page.html"]) {
      expect(safeUrl(url)).toBe(url);
    }
  });
  it("blocks script-running and data URLs", () => {
    for (const url of ["javascript:alert(1)", "JavaScript:alert(1)", "data:text/html,<script>alert(1)</script>", "vbscript:msgbox(1)", "file:///etc/passwd"]) {
      expect(safeUrl(url)).toBe("");
    }
  });
  it("blocks disguised javascript: URLs", () => {
    for (const url of ["java\tscript:alert(1)", "java\nscript:alert(1)", "  javascript:alert(1)", "\u0000javascript:alert(1)"]) {
      expect(safeUrl(url)).toBe("");
    }
  });
  it("treats an empty or nonsense URL safely", () => {
    expect(safeUrl("")).toBe("");
    expect(safeUrl("http://")).toBe("");
  });
});

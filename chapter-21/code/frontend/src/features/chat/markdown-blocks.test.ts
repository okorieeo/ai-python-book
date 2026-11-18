import { describe, expect, it } from "vitest";
import { closeOpenFence, splitMarkdownBlocks } from "./markdown-blocks";

describe("splitMarkdownBlocks", () => {
  it("splits paragraphs on blank lines", () => {
    expect(splitMarkdownBlocks("one\n\ntwo\n\n\n\nthree")).toEqual(["one", "two", "three"]);
  });
  it("keeps multi-line paragraphs and lists together", () => {
    expect(splitMarkdownBlocks("a\nb\n\n- x\n- y")).toEqual(["a\nb", "- x\n- y"]);
  });
  it("does not split inside a fenced code block, even at blank lines", () => {
    const text = "Intro\n\n```python\ndef f():\n\n    return 1\n```\n\nOutro";
    expect(splitMarkdownBlocks(text)).toEqual(["Intro", "```python\ndef f():\n\n    return 1\n```", "Outro"]);
  });
  it("supports tilde fences and longer fences that contain shorter ones", () => {
    expect(splitMarkdownBlocks("~~~\na\n\nb\n~~~")).toHaveLength(1);
    const nested = "````md\n```js\nx\n\n```\n````\n\nafter";
    expect(splitMarkdownBlocks(nested)).toEqual(["````md\n```js\nx\n\n```\n````", "after"]);
  });
  it("keeps an unfinished fence as one block while it streams", () => {
    expect(splitMarkdownBlocks("Text\n\n```js\nlet a = 1;\n\nlet b")).toEqual(["Text", "```js\nlet a = 1;\n\nlet b"]);
  });
  it("does not mistake inline triple backticks for a fence", () => {
    expect(splitMarkdownBlocks("use ```x``` here\n\nnext")).toEqual(["use ```x``` here", "next"]);
    expect(splitMarkdownBlocks("```x``` is inline\n\nnext")).toEqual(["```x``` is inline", "next"]);
  });
  it("handles empty input and trailing newlines", () => {
    expect(splitMarkdownBlocks("")).toEqual([]);
    expect(splitMarkdownBlocks("\n\n")).toEqual([]);
    expect(splitMarkdownBlocks("a\n")).toEqual(["a"]);
  });
  it("earlier blocks stay identical as text grows, so memoizing them works", () => {
    const before = splitMarkdownBlocks("First paragraph.\n\nSecond par");
    const after = splitMarkdownBlocks("First paragraph.\n\nSecond paragraph.\n\nThi");
    expect(after[0]).toBe(before[0]);
  });
});

describe("closeOpenFence", () => {
  it("closes a fence that is still open", () => {
    expect(closeOpenFence("```js\nlet a")).toBe("```js\nlet a\n```");
    expect(closeOpenFence("~~~~\nx")).toBe("~~~~\nx\n~~~~");
  });
  it("leaves finished or fence-free blocks alone", () => {
    expect(closeOpenFence("```js\nlet a\n```")).toBe("```js\nlet a\n```");
    expect(closeOpenFence("plain **text**")).toBe("plain **text**");
  });
});

// Renders components to HTML on the server with react-dom (no browser, no jsdom).
// This checks markup and accessibility attributes, not click behaviour.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Attachment } from "../attachments";
import type { ChatMessage } from "../chat-state";
import { Composer } from "./composer";
import { MessageBubble } from "./message-bubble";
import { MessageList } from "./message-list";
import { MessageListSkeleton } from "./skeletons";
import { AttachmentTray, ConnectionBanner, ErrorNotice, TypingIndicator } from "./small-ui";

const html = (node: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(node);
const noop = () => undefined;
const msg = (over: Partial<ChatMessage>): ChatMessage =>
  ({ id: "m1", role: "user", content: "Hello", createdAt: "", ...over });

describe("MessageBubble (user)", () => {
  it("shows a sent message plainly", () => {
    const out = html(<MessageBubble message={msg({ status: "sent" })} onRetry={noop} />);
    expect(out).toContain("Hello");
    expect(out).not.toContain("Sending...");
    expect(out).not.toContain("Retry");
  });
  it("dims a message that is still sending and says so", () => {
    const out = html(<MessageBubble message={msg({ status: "sending" })} onRetry={noop} />);
    expect(out).toContain("Sending...");
    expect(out).toContain("opacity-70");
  });
  it("shows the error and a Retry button when sending failed", () => {
    const out = html(<MessageBubble message={msg({ status: "failed", error: "You are offline." })} onRetry={noop} />);
    expect(out).toContain('role="alert"');
    expect(out).toContain("You are offline.");
    expect(out).toContain("Retry");
  });
  it("escapes HTML in what the user typed", () => {
    const out = html(<MessageBubble message={msg({ content: "<script>alert(1)</script>" })} onRetry={noop} />);
    expect(out).not.toContain("<script>");
    expect(out).toContain("&lt;script&gt;");
  });
  it("mentions attachments", () => {
    const out = html(<MessageBubble message={msg({ attachmentIds: ["a", "b"] })} onRetry={noop} />);
    expect(out).toContain("2 attached files");
  });
});

describe("MessageBubble (assistant)", () => {
  const reply = (over: Partial<ChatMessage>) => msg({ role: "assistant", id: "a1", ...over });
  it("shows the typing indicator before the first token", () => {
    const out = html(<MessageBubble message={reply({ content: "", streaming: true })} onRetry={noop} />);
    expect(out).toContain("The assistant is thinking");
    expect(out).toContain('aria-busy="true"');
  });
  it("shows text and a cursor while streaming", () => {
    const out = html(<MessageBubble message={reply({ content: "Partial answer", streaming: true })} onRetry={noop} />);
    expect(out).toContain("Partial answer");
    expect(out).toContain('aria-busy="true"');
    expect(out).toContain("inline-block");
  });
  it("is not busy and has no cursor when finished", () => {
    const out = html(<MessageBubble message={reply({ content: "Done", streaming: false, finishReason: "stop" })} onRetry={noop} />);
    expect(out).toContain('aria-busy="false"');
    expect(out).not.toContain("inline-block");
  });
  it("explains why a reply ended early", () => {
    const cases: [ChatMessage["finishReason"], string][] = [
      ["length", "length limit"], ["stopped", "You stopped this reply"],
      ["interrupted", "connection dropped"], ["error", "Something went wrong"],
    ];
    for (const [finishReason, text] of cases) {
      expect(html(<MessageBubble message={reply({ content: "x", finishReason })} onRetry={noop} />)).toContain(text);
    }
  });
});

describe("Composer", () => {
  const render = (over: Partial<Parameters<typeof Composer>[0]> = {}) =>
    html(<Composer connected generating={false} onSend={noop} onStop={noop} {...over} />);
  it("has a real label for the text box", () => {
    const out = render();
    expect(out).toContain('<label for="chat-input" class="sr-only">Message</label>');
    expect(out).toContain('id="chat-input"');
  });
  it("cannot send an empty message", () => {
    expect(render()).toMatch(/<button[^>]*disabled[^>]*>Send<\/button>/);
  });
  it("cannot send while disconnected", () => {
    expect(render({ connected: false })).toMatch(/<button[^>]*disabled[^>]*>Send<\/button>/);
  });
  it("offers Stop (and no Send) while a reply is generating", () => {
    const out = render({ generating: true });
    expect(out).toContain('aria-label="Stop generating"');
    expect(out).not.toContain(">Send<");
  });
  it("has an attach button and a hidden multi-file input", () => {
    const out = render();
    expect(out).toContain("Attach");
    expect(out).toMatch(/<input[^>]*type="file"[^>]*multiple/);
  });
});

describe("ConnectionBanner", () => {
  it("is silent while connecting or open", () => {
    expect(html(<ConnectionBanner status="open" onRetry={noop} />)).toBe("");
    expect(html(<ConnectionBanner status="connecting" onRetry={noop} />)).toBe("");
  });
  it("tells the user when it is reconnecting and when it gave up", () => {
    const reconnecting = html(<ConnectionBanner status="reconnecting" onRetry={noop} />);
    expect(reconnecting).toContain('role="status"');
    expect(reconnecting).toContain("Reconnecting");
    expect(reconnecting).toContain("Retry now");
    expect(html(<ConnectionBanner status="closed" onRetry={noop} />)).toContain("Reconnect");
  });
});

describe("AttachmentTray", () => {
  const item = (over: Partial<Attachment>): Attachment =>
    ({ localId: "l1", name: "a.png", size: 2048, type: "image/png", status: "done", progress: 100, ...over });
  it("renders nothing when empty", () => expect(html(<AttachmentTray items={[]} onRemove={noop} onRetry={noop} />)).toBe(""));
  it("shows progress while uploading", () => {
    const out = html(<AttachmentTray items={[item({ status: "uploading", progress: 40 })]} onRemove={noop} onRetry={noop} />);
    expect(out).toContain('<progress value="40"');
    expect(out).toContain("Uploading a.png");
  });
  it("shows the error with a Retry button", () => {
    const out = html(<AttachmentTray items={[item({ status: "error", error: "Too large" })]} onRemove={noop} onRetry={noop} />);
    expect(out).toContain("Too large");
    expect(out).toContain("Retry");
  });
  it("shows size when done, and has an accessible remove button", () => {
    const out = html(<AttachmentTray items={[item({})]} onRemove={noop} onRetry={noop} />);
    expect(out).toContain("2 KB");
    expect(out).toContain('aria-label="Remove a.png"');
  });
  it("escapes hostile file names", () => {
    const name = '<img src=x onerror="alert(1)">.png';
    const out = html(<AttachmentTray items={[item({ name })]} onRemove={noop} onRetry={noop} />);
    expect(out).not.toContain("<img src=x");
    expect(out).toContain("&lt;img src=x");
  });
});

describe("ErrorNotice and TypingIndicator", () => {
  it("rounds the retry time up and is announced", () => {
    const out = html(<ErrorNotice error={{ code: "rate_limited", message: "Slow down.", retryAfter: 50.2 }} onDismiss={noop} />);
    expect(out).toContain('role="alert"');
    expect(out).toContain("Try again in 51 seconds.");
  });
  it("omits the retry sentence when there is no retry time", () => {
    expect(html(<ErrorNotice error={{ code: "x", message: "Oops." }} onDismiss={noop} />)).not.toContain("Try again");
  });
  it("hides the dots from screen readers and gives them text", () => {
    const out = html(<TypingIndicator />);
    expect(out).toContain("The assistant is thinking");
    expect(out).toContain('aria-hidden="true"');
  });
});

describe("MessageList", () => {
  const list = (over: Partial<Parameters<typeof MessageList>[0]> = {}) =>
    html(<MessageList messages={[]} loading={false} awaitingReply={false} generating={false} onRetry={noop} {...over} />);
  it("shows the skeleton while history loads", () => {
    const out = list({ loading: true });
    expect(out).toContain('aria-hidden="true"');
    expect(out).not.toContain('role="log"');
  });
  it("is a quiet log region: tokens must not be read out one by one", () => {
    const out = list({ messages: [msg({ id: "a" }), msg({ id: "b", role: "assistant", content: "Hi" })] });
    expect(out).toContain('role="log"');
    expect(out).toContain('aria-live="off"');
    expect(out).toContain('aria-label="Conversation"');
  });
  it("marks the log busy while generating", () => {
    expect(list({ generating: true })).toContain('aria-busy="true"');
  });
  it("invites the first message when empty", () => {
    expect(list()).toContain("Send a message to start.");
  });
  it("shows the typing indicator while waiting for the first token", () => {
    expect(list({ awaitingReply: true })).toContain("The assistant is thinking");
  });
  it("has a status region for announcements", () => {
    expect(list()).toContain('<div role="status" class="sr-only">');
  });
});

describe("MessageListSkeleton", () => {
  it("is hidden from assistive technology", () => {
    expect(html(<MessageListSkeleton />)).toContain('aria-hidden="true"');
  });
});
